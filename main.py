from datetime import datetime
from io import BytesIO
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import database
import models
import schemas
from services.timetable_generator import build_time_slots, generate_timetable

database.ensure_schema(models.Base.metadata)

app = FastAPI(
    title="PriorityPlanners - Intelligent Timetable Management System",
    version="3.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")


# -------------------------
# Shared helpers
# -------------------------

VALID_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _parse_time(value: str) -> int:
    try:
        h, m = value.split(":", 1)
        h, m = int(h), int(m[:2])
        if h < 0 or h > 23 or m < 0 or m > 59:
            raise ValueError
        return h * 60 + m
    except Exception as exc:
        raise HTTPException(400, f"Invalid time '{value}'. Use HH:MM.") from exc


def _safe_commit(db: Session, message: str):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, message) from exc


def _clear_generated_rows(db: Session):
    entry_ids = [row[0] for row in db.query(models.TimetableEntry.id).all()]
    if entry_ids:
        db.query(models.CalendarEvent).filter(
            models.CalendarEvent.timetable_entry_id.in_(entry_ids)
        ).delete(synchronize_session=False)
        db.query(models.SubstitutionRequest).filter(
            models.SubstitutionRequest.timetable_entry_id.in_(entry_ids)
        ).delete(synchronize_session=False)
    deleted_entries = db.query(models.TimetableEntry).delete(synchronize_session=False)
    deleted_requirements = db.query(models.TimetableRequirement).delete(synchronize_session=False)
    deleted_configurations = db.query(models.TimetableConfiguration).delete(synchronize_session=False)
    deleted_time_slots = db.query(models.TimeSlot).delete(synchronize_session=False)
    return {
        "deleted_entries": deleted_entries,
        "deleted_requirements": deleted_requirements,
        "deleted_configurations": deleted_configurations,
        "deleted_time_slots": deleted_time_slots,
    }


def _find_or_create_user(db: Session, role: str):
    if role == "admin":
        email = "admin@priorityplanners.com"
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            user = models.User(name="Administrator", email=email, role="admin")
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    if role == "faculty":
        faculty = db.query(models.Faculty).order_by(models.Faculty.id).first()
        if not faculty:
            return None
        email = "faculty@priorityplanners.com"
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            user = models.User(
                name=faculty.name,
                email=email,
                role="faculty",
                faculty_id=faculty.id,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    batch = db.query(models.Batch).order_by(models.Batch.id).first()
    if not batch:
        return None
    email = "student@priorityplanners.com"
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        user = models.User(
            name="Demo Student",
            email=email,
            role="student",
            batch_id=batch.id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


# -------------------------
# Pages / health
# -------------------------

@app.get("/", include_in_schema=False)
def root():
    return FileResponse("frontend/index.html")


@app.get("/timetable-builder", include_in_schema=False)
def timetable_builder_page():
    return FileResponse("frontend/timetable_builder.html")


@app.get("/health")
def health():
    return {"status": "healthy", "service": "PriorityPlanners", "version": app.version}


@app.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    """Single reliable data endpoint used by the live admin dashboard."""
    try:
        faculty = db.query(models.Faculty).order_by(models.Faculty.id).all()
        subjects = db.query(models.Subject).order_by(models.Subject.id).all()
        batches = db.query(models.Batch).order_by(models.Batch.id).all()
        rooms = db.query(models.Room).order_by(models.Room.id).all()
        slots = db.query(models.TimeSlot).order_by(models.TimeSlot.id).all()
        mappings = db.query(models.FacultySubject).order_by(models.FacultySubject.id).all()
        entries = db.query(models.TimetableEntry).order_by(models.TimetableEntry.id).all()

        f_map = {item.id: item for item in faculty}
        s_map = {item.id: item for item in subjects}
        r_map = {item.id: item for item in rooms}
        t_map = {item.id: item for item in slots}
        mapped_pairs = {(item.faculty_id, item.subject_id) for item in mappings}

        issues = []
        seen = {}
        for entry in entries:
            slot = t_map.get(entry.time_slot_id)
            slot_key = f"{slot.day}|{slot.start_time}" if slot else str(entry.time_slot_id)
            for prefix, value in (("Faculty", entry.faculty_id), ("Room", entry.room_id), ("Batch", entry.batch_id)):
                key = (prefix, value, slot_key)
                if key in seen:
                    issues.append(f"{prefix} conflict in {slot_key}")
                else:
                    seen[key] = entry.id

            f = f_map.get(entry.faculty_id)
            sub = s_map.get(entry.subject_id)
            room = r_map.get(entry.room_id)
            if not f:
                issues.append(f"Missing faculty for entry #{entry.id}")
            if sub and sub.is_practical and room and not room.is_lab:
                issues.append(f"Lab subject {sub.name} is in room {room.room_number}")
            if f and not (entry.faculty_id, entry.subject_id) in mapped_pairs:
                issues.append(f"{f.name} is not mapped to {(sub.name if sub else 'subject')}")

        daily = {}
        for entry in entries:
            f = f_map.get(entry.faculty_id)
            slot = t_map.get(entry.time_slot_id)
            if not f or not slot:
                continue
            key = (entry.faculty_id, slot.day)
            daily[key] = daily.get(key, 0) + 1
            if daily[key] > f.max_daily_lectures:
                issues.append(f"{f.name} exceeds daily limit on {slot.day}")

        occupancy = round(len(entries) / (len(rooms) * len(slots)) * 100) if rooms and slots else 0
        max_load = 0
        max_faculty = ""
        for f in faculty:
            load = sum(1 for entry in entries if entry.faculty_id == f.id)
            if load > max_load:
                max_load = load
                max_faculty = f.name

        return {
            "faculty": [schemas.FacultyRead.model_validate(x).model_dump() for x in faculty],
            "subjects": [schemas.SubjectRead.model_validate(x).model_dump() for x in subjects],
            "batches": [schemas.BatchRead.model_validate(x).model_dump() for x in batches],
            "rooms": [schemas.RoomRead.model_validate(x).model_dump() for x in rooms],
            "slots": [schemas.TimeSlotRead.model_validate(x).model_dump() for x in slots],
            "mappings": [schemas.FacultySubjectRead.model_validate(x).model_dump() for x in mappings],
            "entries": [schemas.TimetableEntryRead.model_validate(x).model_dump() for x in entries],
            "issues": sorted(set(issues)),
            "occupancy": occupancy,
            "maxLoad": max_load,
            "maxFaculty": max_faculty,
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, f"Dashboard data could not be loaded: {exc}") from exc


# -------------------------
# Demo data / auth
# -------------------------

@app.post("/demo/seed")
def seed_demo_data(db: Session = Depends(get_db)):
    faculty_names = [
        "Dr. Rajesh Kumar",
        "Dr. Priya Sharma",
        "Dr. Amit Singh",
        "Dr. Neha Verma",
        "Dr. Rahul Gupta",
        "Dr. Anjali Mehta",
        "Dr. Vivek Jain",
        "Dr. Pooja Agarwal",
    ]
    for name in faculty_names:
        if not db.query(models.Faculty).filter(models.Faculty.name == name).first():
            db.add(models.Faculty(name=name, max_daily_lectures=4))

    for room_number, is_lab in [
        ("R101", False),
        ("R102", False),
        ("R103", False),
        ("R104", False),
        ("R105", False),
        ("R106", False),
        ("LAB1", True),
        ("LAB2", True),
        ("LAB3", True),
    ]:
        if not db.query(models.Room).filter(models.Room.room_number == room_number).first():
            db.add(models.Room(room_number=room_number, is_lab=is_lab))

    subjects = [
        ("Mathematics", False),
        ("Data Structures", False),
        ("Database Management", False),
        ("Operating Systems", False),
        ("Computer Networks", False),
        ("Web Development", False),
        ("Data Structures Lab", True),
        ("Web Development Lab", True),
    ]
    for name, practical in subjects:
        if not db.query(models.Subject).filter(models.Subject.name == name).first():
            db.add(models.Subject(name=name, is_practical=practical))

    for batch_name in ["CSE-3A", "CSE-3B", "CSE-3C", "CSE-3D"]:
        if not db.query(models.Batch).filter(models.Batch.name == batch_name).first():
            db.add(models.Batch(name=batch_name))

    db.commit()

    faculties = db.query(models.Faculty).order_by(models.Faculty.id).all()
    subjects_rows = db.query(models.Subject).order_by(models.Subject.id).all()
    existing_mappings = {
        (row.faculty_id, row.subject_id)
        for row in db.query(models.FacultySubject).all()
    }
    for subject in subjects_rows:
        for faculty in faculties:
            if (faculty.id, subject.id) not in existing_mappings:
                db.add(
                    models.FacultySubject(
                        faculty_id=faculty.id,
                        subject_id=subject.id,
                    )
                )
    db.commit()

    _find_or_create_user(db, "admin")
    _find_or_create_user(db, "faculty")
    _find_or_create_user(db, "student")

    return {
        "success": True,
        "message": "Demo data loaded successfully.",
        "faculty": db.query(models.Faculty).count(),
        "rooms": db.query(models.Room).count(),
        "subjects": db.query(models.Subject).count(),
        "batches": db.query(models.Batch).count(),
        "faculty_subjects": db.query(models.FacultySubject).count(),
    }


@app.post("/auth/login")
def login(request: schemas.LoginRequest, db: Session = Depends(get_db)):
    credentials = {
        "admin": "admin123",
        "faculty": "faculty123",
        "student": "student123",
    }
    if request.role not in credentials or request.password != credentials[request.role]:
        raise HTTPException(401, "Invalid credentials.")

    user = _find_or_create_user(db, request.role)
    user_data = None
    if user:
        user_data = {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "faculty_id": user.faculty_id,
            "batch_id": user.batch_id,
        }

    return {
        "success": True,
        "message": "Login successful.",
        "role": request.role,
        "username": request.username,
        "user": user_data,
    }


# -------------------------
# Master-data CRUD
# -------------------------

@app.post("/faculty/", response_model=schemas.FacultyRead)
def create_faculty(item: schemas.FacultyCreate, db: Session = Depends(get_db)):
    obj = models.Faculty(**item.model_dump())
    db.add(obj)
    _safe_commit(db, "Faculty could not be created. Check the entered data.")
    db.refresh(obj)
    return obj


@app.get("/faculty/", response_model=list[schemas.FacultyRead])
def get_faculty(skip: int = 0, limit: int = 500, db: Session = Depends(get_db)):
    return db.query(models.Faculty).order_by(models.Faculty.id).offset(skip).limit(limit).all()


@app.put("/faculty/{faculty_id}", response_model=schemas.FacultyRead)
def update_faculty(faculty_id: int, item: schemas.FacultyCreate, db: Session = Depends(get_db)):
    obj = db.query(models.Faculty).filter(models.Faculty.id == faculty_id).first()
    if not obj:
        raise HTTPException(404, "Faculty not found.")
    for key, value in item.model_dump().items():
        setattr(obj, key, value)
    _safe_commit(db, "Faculty could not be updated.")
    db.refresh(obj)
    return obj


@app.delete("/faculty/{faculty_id}")
def delete_faculty(faculty_id: int, db: Session = Depends(get_db)):
    obj = db.query(models.Faculty).filter(models.Faculty.id == faculty_id).first()
    if not obj:
        raise HTTPException(404, "Faculty not found.")
    if db.query(models.User).filter(models.User.faculty_id == faculty_id).first():
        raise HTTPException(409, "Faculty is linked to a user account. Edit it instead or reassign that user first.")
    if db.query(models.TimetableEntry).filter(models.TimetableEntry.faculty_id == faculty_id).first():
        raise HTTPException(409, "Faculty is used by the current timetable. Clear the generated timetable first.")
    db.query(models.TimetableRequirement).filter(models.TimetableRequirement.faculty_id == faculty_id).delete(synchronize_session=False)
    db.query(models.FacultySubject).filter(models.FacultySubject.faculty_id == faculty_id).delete(synchronize_session=False)
    db.delete(obj)
    _safe_commit(db, "Faculty cannot be deleted because related records still exist.")
    return {"success": True, "message": "Faculty deleted successfully."}


@app.post("/rooms/", response_model=schemas.RoomRead)
def create_room(item: schemas.RoomCreate, db: Session = Depends(get_db)):
    obj = models.Room(**item.model_dump())
    db.add(obj)
    _safe_commit(db, "Room could not be created. Room name may already exist.")
    db.refresh(obj)
    return obj


@app.get("/rooms/", response_model=list[schemas.RoomRead])
def get_rooms(skip: int = 0, limit: int = 500, db: Session = Depends(get_db)):
    return db.query(models.Room).order_by(models.Room.id).offset(skip).limit(limit).all()


@app.put("/rooms/{room_id}", response_model=schemas.RoomRead)
def update_room(room_id: int, item: schemas.RoomCreate, db: Session = Depends(get_db)):
    obj = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not obj:
        raise HTTPException(404, "Room not found.")
    for key, value in item.model_dump().items():
        setattr(obj, key, value)
    _safe_commit(db, "Room could not be updated. Room name may already exist.")
    db.refresh(obj)
    return obj


@app.delete("/rooms/{room_id}")
def delete_room(room_id: int, db: Session = Depends(get_db)):
    obj = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not obj:
        raise HTTPException(404, "Room not found.")
    if db.query(models.TimetableEntry).filter(models.TimetableEntry.room_id == room_id).first():
        raise HTTPException(409, "Room is used by the current timetable. Clear the generated timetable first.")
    db.delete(obj)
    _safe_commit(db, "Room cannot be deleted because related records still exist.")
    return {"success": True, "message": "Room deleted successfully."}


@app.post("/subjects/", response_model=schemas.SubjectRead)
def create_subject(item: schemas.SubjectCreate, db: Session = Depends(get_db)):
    obj = models.Subject(**item.model_dump())
    db.add(obj)
    _safe_commit(db, "Subject could not be created.")
    db.refresh(obj)
    return obj


@app.get("/subjects/", response_model=list[schemas.SubjectRead])
def get_subjects(skip: int = 0, limit: int = 500, db: Session = Depends(get_db)):
    return db.query(models.Subject).order_by(models.Subject.id).offset(skip).limit(limit).all()


@app.put("/subjects/{subject_id}", response_model=schemas.SubjectRead)
def update_subject(subject_id: int, item: schemas.SubjectCreate, db: Session = Depends(get_db)):
    obj = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not obj:
        raise HTTPException(404, "Subject not found.")
    for key, value in item.model_dump().items():
        setattr(obj, key, value)
    _safe_commit(db, "Subject could not be updated.")
    db.refresh(obj)
    return obj


@app.delete("/subjects/{subject_id}")
def delete_subject(subject_id: int, db: Session = Depends(get_db)):
    obj = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not obj:
        raise HTTPException(404, "Subject not found.")
    if db.query(models.TimetableEntry).filter(models.TimetableEntry.subject_id == subject_id).first():
        raise HTTPException(409, "Subject is used by the current timetable. Clear the generated timetable first.")
    db.query(models.TimetableRequirement).filter(models.TimetableRequirement.subject_id == subject_id).delete(synchronize_session=False)
    db.query(models.FacultySubject).filter(models.FacultySubject.subject_id == subject_id).delete(synchronize_session=False)
    db.delete(obj)
    _safe_commit(db, "Subject cannot be deleted because related records still exist.")
    return {"success": True, "message": "Subject deleted successfully."}


@app.post("/batches/", response_model=schemas.BatchRead)
def create_batch(item: schemas.BatchCreate, db: Session = Depends(get_db)):
    obj = models.Batch(**item.model_dump())
    db.add(obj)
    _safe_commit(db, "Batch could not be created. Batch name may already exist.")
    db.refresh(obj)
    return obj


@app.get("/batches/", response_model=list[schemas.BatchRead])
def get_batches(skip: int = 0, limit: int = 500, db: Session = Depends(get_db)):
    return db.query(models.Batch).order_by(models.Batch.id).offset(skip).limit(limit).all()


@app.put("/batches/{batch_id}", response_model=schemas.BatchRead)
def update_batch(batch_id: int, item: schemas.BatchCreate, db: Session = Depends(get_db)):
    obj = db.query(models.Batch).filter(models.Batch.id == batch_id).first()
    if not obj:
        raise HTTPException(404, "Batch not found.")
    for key, value in item.model_dump().items():
        setattr(obj, key, value)
    _safe_commit(db, "Batch could not be updated. Batch name may already exist.")
    db.refresh(obj)
    return obj


@app.delete("/batches/{batch_id}")
def delete_batch(batch_id: int, db: Session = Depends(get_db)):
    obj = db.query(models.Batch).filter(models.Batch.id == batch_id).first()
    if not obj:
        raise HTTPException(404, "Batch not found.")
    if db.query(models.User).filter(models.User.batch_id == batch_id).first():
        raise HTTPException(409, "Batch is linked to a user account. Edit it instead or reassign that user first.")
    if db.query(models.TimetableEntry).filter(models.TimetableEntry.batch_id == batch_id).first():
        raise HTTPException(409, "Batch is used by the current timetable. Clear the generated timetable first.")
    db.query(models.TimetableRequirement).filter(models.TimetableRequirement.batch_id == batch_id).delete(synchronize_session=False)
    db.delete(obj)
    _safe_commit(db, "Batch cannot be deleted because related records still exist.")
    return {"success": True, "message": "Batch deleted successfully."}


@app.post("/faculty-subjects/", response_model=schemas.FacultySubjectRead)
def create_faculty_subject(item: schemas.FacultySubjectCreate, db: Session = Depends(get_db)):
    if not db.query(models.Faculty).filter(models.Faculty.id == item.faculty_id).first():
        raise HTTPException(400, "Faculty does not exist.")
    if not db.query(models.Subject).filter(models.Subject.id == item.subject_id).first():
        raise HTTPException(400, "Subject does not exist.")
    if db.query(models.FacultySubject).filter(
        models.FacultySubject.faculty_id == item.faculty_id,
        models.FacultySubject.subject_id == item.subject_id,
    ).first():
        raise HTTPException(409, "This faculty-subject mapping already exists.")
    obj = models.FacultySubject(**item.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@app.get("/faculty-subjects/", response_model=list[schemas.FacultySubjectRead])
def get_faculty_subjects(db: Session = Depends(get_db)):
    return db.query(models.FacultySubject).order_by(models.FacultySubject.id).all()


@app.delete("/faculty-subjects/{mapping_id}")
def delete_faculty_subject(mapping_id: int, db: Session = Depends(get_db)):
    obj = db.query(models.FacultySubject).filter(models.FacultySubject.id == mapping_id).first()
    if not obj:
        raise HTTPException(404, "Faculty-subject mapping not found.")
    db.delete(obj)
    db.commit()
    return {"success": True, "message": "Faculty-subject mapping deleted successfully."}


# -------------------------
# Time slots / timetable
# -------------------------

@app.post("/time-slots/", response_model=schemas.TimeSlotRead)
def create_time_slot(item: schemas.TimeSlotCreate, db: Session = Depends(get_db)):
    obj = models.TimeSlot(**item.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@app.get("/time-slots/", response_model=list[schemas.TimeSlotRead])
def get_time_slots(db: Session = Depends(get_db)):
    return db.query(models.TimeSlot).order_by(models.TimeSlot.id).all()


@app.post("/timetable/", response_model=schemas.TimetableEntryRead)
def create_timetable_entry(item: schemas.TimetableEntryCreate, db: Session = Depends(get_db)):
    obj = models.TimetableEntry(**item.model_dump())
    db.add(obj)
    _safe_commit(db, "Timetable entry could not be created. A linked record may be invalid.")
    db.refresh(obj)
    return obj


@app.get("/timetable/", response_model=list[schemas.TimetableEntryRead])
def get_timetable(db: Session = Depends(get_db)):
    return db.query(models.TimetableEntry).order_by(models.TimetableEntry.id).all()


@app.get("/timetable/requirements", response_model=list[schemas.TimetableRequirementRead])
def get_requirements(db: Session = Depends(get_db)):
    return db.query(models.TimetableRequirement).order_by(models.TimetableRequirement.id).all()


@app.get("/timetable/configuration")
def get_timetable_configuration(db: Session = Depends(get_db)):
    config = db.query(models.TimetableConfiguration).order_by(models.TimetableConfiguration.id.desc()).first()
    if not config:
        return None
    return {
        "id": config.id,
        "working_days": [x for x in config.working_days.split(",") if x],
        "college_start": config.college_start,
        "college_end": config.college_end,
        "recess_start": config.recess_start,
        "recess_end": config.recess_end,
        "slot_minutes": config.slot_minutes,
    }


@app.delete("/timetable/clear")
def clear_generated_timetable(db: Session = Depends(get_db)):
    try:
        result = _clear_generated_rows(db)
        db.commit()
        return {
            "success": True,
            "message": "Generated timetable, saved requirements and generated time slots were cleared. Faculty, rooms, subjects and batches were kept.",
            **result,
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, f"Could not clear generated timetable: {exc}") from exc


@app.post("/timetable/generate-configured")
def generate_configured(config: schemas.TimetableConfigurationInput, db: Session = Depends(get_db)):
    working_days = list(dict.fromkeys(config.working_days))
    if any(day not in VALID_DAYS for day in working_days):
        raise HTTPException(400, "Working days must use Monday, Tuesday, Wednesday, Thursday, Friday, Saturday or Sunday.")

    start = _parse_time(config.college_start)
    end = _parse_time(config.college_end)
    if start >= end:
        raise HTTPException(400, "College start must be before college end.")

    recess_start = recess_end = None
    if config.recess_start or config.recess_end:
        if not config.recess_start or not config.recess_end:
            raise HTTPException(400, "Provide both recess start and recess end.")
        recess_start = _parse_time(config.recess_start)
        recess_end = _parse_time(config.recess_end)
        if recess_start >= recess_end:
            raise HTTPException(400, "Recess start must be before recess end.")
        if recess_start < start or recess_end > end:
            raise HTTPException(400, "Recess must be inside college working hours.")

    if (end - start) < config.slot_minutes:
        raise HTTPException(400, "College timing is shorter than the selected slot length.")

    batches = {x.id: x for x in db.query(models.Batch).all()}
    subjects = {x.id: x for x in db.query(models.Subject).all()}
    faculty = {x.id: x for x in db.query(models.Faculty).all()}
    rooms = db.query(models.Room).all()
    if not batches:
        raise HTTPException(400, "No batches found. Add or load batches first.")
    if not subjects:
        raise HTTPException(400, "No subjects found. Add or load subjects first.")
    if not faculty:
        raise HTTPException(400, "No faculty found. Add or load faculty first.")
    if not rooms:
        raise HTTPException(400, "No rooms found. Add or load rooms first.")

    seen_pairs = set()
    for requirement in config.requirements:
        if requirement.batch_id not in batches:
            raise HTTPException(400, f"Batch ID {requirement.batch_id} does not exist.")
        if requirement.subject_id not in subjects:
            raise HTTPException(400, f"Subject ID {requirement.subject_id} does not exist.")
        if requirement.faculty_id not in faculty:
            raise HTTPException(400, f"Faculty ID {requirement.faculty_id} does not exist.")
        pair = (requirement.batch_id, requirement.subject_id)
        if pair in seen_pairs:
            raise HTTPException(400, "Each batch + subject should appear only once in the requirements list.")
        seen_pairs.add(pair)
        if requirement.duration_minutes % config.slot_minutes != 0:
            subject_name = subjects[requirement.subject_id].name
            raise HTTPException(400, f"{subject_name}: duration must be a multiple of the selected slot length ({config.slot_minutes} minutes).")
        if requirement.duration_minutes > (end - start):
            raise HTTPException(400, f"{subjects[requirement.subject_id].name}: duration is longer than the college working period.")

    practical_needs_lab = any(subjects[r.subject_id].is_practical for r in config.requirements)
    if practical_needs_lab and not any(room.is_lab for room in rooms):
        raise HTTPException(400, "At least one laboratory room is required for practical subjects.")

    try:
        # One transaction for the complete replacement. If scheduling fails, the old timetable stays intact.
        _clear_generated_rows(db)

        for requirement in config.requirements:
            db.add(models.TimetableRequirement(**requirement.model_dump()))

        for fid, limit in config.faculty_daily_limits.items():
            try:
                faculty_id = int(fid)
                daily_limit = int(limit)
            except (TypeError, ValueError) as exc:
                raise HTTPException(400, "Faculty daily limits contain an invalid value.") from exc
            if faculty_id in faculty:
                faculty[faculty_id].max_daily_lectures = max(1, min(daily_limit, 12))

        db.add(
            models.TimetableConfiguration(
                working_days=",".join(working_days),
                college_start=config.college_start,
                college_end=config.college_end,
                recess_start=config.recess_start,
                recess_end=config.recess_end,
                slot_minutes=config.slot_minutes,
            )
        )
        db.flush()

        saved_config = db.query(models.TimetableConfiguration).order_by(models.TimetableConfiguration.id.desc()).first()
        if not saved_config:
            raise HTTPException(500, "Could not save timetable configuration.")
        build_time_slots(db, saved_config)

        ok, message = generate_timetable(db)
        if not ok:
            db.rollback()
            raise HTTPException(400, message)

        db.commit()
        entry_count = db.query(models.TimetableEntry).count()
        return {
            "success": True,
            "message": message,
            "requirements": len(config.requirements),
            "entries": entry_count,
            "working_days": working_days,
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, f"Timetable generation failed: {exc}") from exc


@app.post("/timetable/generate")
def generate_full_timetable(db: Session = Depends(get_db)):
    # Kept as a compatibility route for older frontend code.
    # New generation always goes through the dedicated requirements builder.
    if not db.query(models.TimetableRequirement).count():
        raise HTTPException(400, "No timetable requirements configured. Use the Generate timetable button to open the requirements builder.")
    raise HTTPException(400, "Please use the Generate timetable button to open the requirements builder. This is the safe generation path.")


@app.get("/timetable/batch/{batch_id}")
def get_batch_timetable(batch_id: int, db: Session = Depends(get_db)):
    return db.query(models.TimetableEntry).filter(models.TimetableEntry.batch_id == batch_id).all()


@app.get("/timetable/faculty/{faculty_id}")
def get_faculty_timetable(faculty_id: int, db: Session = Depends(get_db)):
    return db.query(models.TimetableEntry).filter(models.TimetableEntry.faculty_id == faculty_id).all()


@app.get("/timetable/conflicts")
def timetable_conflicts(db: Session = Depends(get_db)):
    entries = db.query(models.TimetableEntry).all()
    conflicts = []
    for field, label in (("faculty_id", "faculty"), ("room_id", "room"), ("batch_id", "batch")):
        groups = {}
        for entry in entries:
            key = (getattr(entry, field), entry.time_slot_id)
            groups.setdefault(key, []).append(entry.id)
        for key, ids in groups.items():
            if len(ids) > 1:
                conflicts.append({"type": label, "id": key[0], "time_slot_id": key[1], "entries": ids})
    return {"has_conflicts": bool(conflicts), "count": len(conflicts), "conflicts": conflicts}


@app.post("/timetable/publish")
def publish_timetable(db: Session = Depends(get_db)):
    count = db.query(models.TimetableEntry).count()
    if not count:
        raise HTTPException(400, "Generate a timetable before publishing.")
    return {
        "success": True,
        "message": "Timetable published successfully.",
        "classes": count,
        "published_at": datetime.utcnow().isoformat(),
    }


# -------------------------
# Users / substitutions / notifications / calendar
# -------------------------

@app.post("/users/", response_model=schemas.UserRead)
def create_user(item: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == item.email).first():
        raise HTTPException(409, "Email already exists.")
    obj = models.User(**item.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@app.get("/users/", response_model=list[schemas.UserRead])
def get_users(db: Session = Depends(get_db)):
    return db.query(models.User).order_by(models.User.id).all()


@app.post("/substitution-requests/", response_model=schemas.SubstitutionRequestRead)
def create_substitution_request(item: schemas.SubstitutionRequestCreate, db: Session = Depends(get_db)):
    obj = models.SubstitutionRequest(**item.model_dump())
    db.add(obj)
    _safe_commit(db, "Substitution request could not be created.")
    db.refresh(obj)
    return obj


@app.get("/substitution-requests/", response_model=list[schemas.SubstitutionRequestRead])
def get_substitution_requests(db: Session = Depends(get_db)):
    return db.query(models.SubstitutionRequest).order_by(models.SubstitutionRequest.id).all()


@app.post("/substitution-requests/{request_id}/respond")
def respond_to_substitution(
    request_id: int,
    accepted: bool,
    reason: Optional[str] = None,
    db: Session = Depends(get_db),
):
    obj = db.query(models.SubstitutionRequest).filter(models.SubstitutionRequest.id == request_id).first()
    if not obj:
        raise HTTPException(404, "Substitution request not found.")
    obj.status = "ACCEPTED" if accepted else "DECLINED"
    if reason:
        obj.reason = reason
    db.commit()
    return {"success": True, "request_id": obj.id, "status": obj.status, "reason": obj.reason}


@app.post("/notifications/", response_model=schemas.NotificationRead)
def create_notification(item: schemas.NotificationCreate, db: Session = Depends(get_db)):
    obj = models.Notification(**item.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@app.get("/notifications/{user_id}", response_model=list[schemas.NotificationRead])
def get_notifications(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.Notification).filter(models.Notification.user_id == user_id).order_by(models.Notification.id.desc()).all()


@app.get("/notifications/user/{user_id}", response_model=list[schemas.NotificationRead])
def get_notifications_compat(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.Notification).filter(models.Notification.user_id == user_id).order_by(models.Notification.id.desc()).all()


@app.post("/calendar-events/", response_model=schemas.CalendarEventRead)
def create_calendar_event(item: schemas.CalendarEventCreate, db: Session = Depends(get_db)):
    obj = models.CalendarEvent(**item.model_dump())
    db.add(obj)
    _safe_commit(db, "Calendar event could not be created.")
    db.refresh(obj)
    return obj


@app.get("/calendar/{user_id}.ics")
def download_calendar(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found.")

    query = (
        db.query(
            models.TimetableEntry,
            models.Subject.name.label("subject_name"),
            models.Room.room_number.label("room_number"),
            models.Batch.name.label("batch_name"),
            models.TimeSlot.day.label("day"),
            models.TimeSlot.start_time.label("start_time"),
            models.TimeSlot.end_time.label("end_time"),
        )
        .join(models.Subject, models.TimetableEntry.subject_id == models.Subject.id)
        .join(models.Room, models.TimetableEntry.room_id == models.Room.id)
        .join(models.Batch, models.TimetableEntry.batch_id == models.Batch.id)
        .join(models.TimeSlot, models.TimetableEntry.time_slot_id == models.TimeSlot.id)
    )
    if user.role == "student" and user.batch_id:
        query = query.filter(models.TimetableEntry.batch_id == user.batch_id)
    if user.role == "faculty" and user.faculty_id:
        query = query.filter(models.TimetableEntry.faculty_id == user.faculty_id)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//PriorityPlanners//Timetable//EN",
        "CALSCALE:GREGORIAN",
    ]
    for row in query.all():
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:pp-{row.TimetableEntry.id}-{user_id}@priorityplanners",
                f"SUMMARY:{row.subject_name}",
                f"LOCATION:{row.room_number}",
                f"DESCRIPTION:Batch {row.batch_name} · {row.day} {row.start_time}-{row.end_time}",
                f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    payload = "\r\n".join(lines).encode("utf-8")
    return StreamingResponse(
        BytesIO(payload),
        media_type="text/calendar",
        headers={
            "Content-Disposition": f"attachment; filename=PriorityPlanners_{user_id}.ics"
        },
    )


# -------------------------
# PDF export
# -------------------------

@app.get("/timetable/pdf")
def download_timetable_pdf(batch_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = (
        db.query(
            models.TimetableEntry,
            models.Subject.name.label("subject_name"),
            models.Faculty.name.label("faculty_name"),
            models.Batch.name.label("batch_name"),
            models.Room.room_number.label("room_number"),
            models.TimeSlot.day.label("day"),
            models.TimeSlot.start_time.label("start_time"),
            models.TimeSlot.end_time.label("end_time"),
        )
        .join(models.Subject, models.TimetableEntry.subject_id == models.Subject.id)
        .join(models.Faculty, models.TimetableEntry.faculty_id == models.Faculty.id)
        .join(models.Batch, models.TimetableEntry.batch_id == models.Batch.id)
        .join(models.Room, models.TimetableEntry.room_id == models.Room.id)
        .join(models.TimeSlot, models.TimetableEntry.time_slot_id == models.TimeSlot.id)
    )
    if batch_id is not None:
        query = query.filter(models.TimetableEntry.batch_id == batch_id)

    entries = query.all()
    if not entries:
        raise HTTPException(404, "No timetable entries found. Generate the timetable first.")

    day_order = {day: index for index, day in enumerate(VALID_DAYS)}
    entries = sorted(
        entries,
        key=lambda row: (
            day_order.get(str(row.day), 99),
            str(row.start_time),
            str(row.batch_name),
        ),
    )

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=8 * mm,
        leftMargin=8 * mm,
        topMargin=8 * mm,
        bottomMargin=8 * mm,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("PriorityPlanners - Generated Timetable", styles["Title"]),
        Spacer(1, 6),
        Paragraph(f"Total scheduled blocks: {len(entries)}", styles["Normal"]),
        Spacer(1, 10),
    ]

    data = [["Day", "Time", "Batch", "Subject", "Faculty", "Room", "Type"]]
    for row in entries:
        data.append(
            [
                row.day,
                f"{row.start_time} - {row.end_time}",
                row.batch_name,
                row.subject_name,
                row.faculty_name,
                row.room_number,
                "Practical" if row.TimetableEntry.is_practical else "Theory",
            ]
        )

    table = Table(
        data,
        repeatRows=1,
        colWidths=[24 * mm, 34 * mm, 27 * mm, 45 * mm, 45 * mm, 25 * mm, 25 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)
    document.build(story)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=PriorityPlanners_Timetable.pdf"},
    )
