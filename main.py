from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

import database
import models
import schemas


# ==========================================
# CREATE DATABASE TABLES
# ==========================================

models.Base.metadata.create_all(bind=database.engine)


# ==========================================
# FASTAPI APPLICATION
# ==========================================

app = FastAPI(
    title="Intelligent Timetable Management System",
    description="Backend API for intelligent timetable generation and management.",
    version="1.0.0"
)


# ==========================================
# DATABASE SESSION
# ==========================================

def get_db():
    db = database.SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ==========================================
# ROOT ENDPOINT
# ==========================================

@app.get("/")
def root():
    return {
        "message": "Intelligent Timetable Management System API is running"
    }


# ==========================================
# FACULTY
# ==========================================

@app.post("/faculty/", response_model=schemas.FacultyRead)
def create_faculty(
    faculty: schemas.FacultyCreate,
    db: Session = Depends(get_db)
):
    db_faculty = models.Faculty(
        **faculty.model_dump()
    )

    db.add(db_faculty)
    db.commit()
    db.refresh(db_faculty)

    return db_faculty


@app.get("/faculty/", response_model=list[schemas.FacultyRead])
def get_faculty(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    return (
        db.query(models.Faculty)
        .offset(skip)
        .limit(limit)
        .all()
    )


# ==========================================
# ROOMS
# ==========================================

@app.post("/rooms/", response_model=schemas.RoomRead)
def create_room(
    room: schemas.RoomCreate,
    db: Session = Depends(get_db)
):
    db_room = models.Room(
        **room.model_dump()
    )

    db.add(db_room)
    db.commit()
    db.refresh(db_room)

    return db_room


@app.get("/rooms/", response_model=list[schemas.RoomRead])
def get_rooms(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    return (
        db.query(models.Room)
        .offset(skip)
        .limit(limit)
        .all()
    )


# ==========================================
# SUBJECTS
# ==========================================

@app.post("/subjects/", response_model=schemas.SubjectRead)
def create_subject(
    subject: schemas.SubjectCreate,
    db: Session = Depends(get_db)
):
    db_subject = models.Subject(
        **subject.model_dump()
    )

    db.add(db_subject)
    db.commit()
    db.refresh(db_subject)

    return db_subject


@app.get("/subjects/", response_model=list[schemas.SubjectRead])
def get_subjects(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    return (
        db.query(models.Subject)
        .offset(skip)
        .limit(limit)
        .all()
    )


# ==========================================
# BATCHES
# ==========================================

@app.post("/batches/", response_model=schemas.BatchRead)
def create_batch(
    batch: schemas.BatchCreate,
    db: Session = Depends(get_db)
):
    db_batch = models.Batch(
        **batch.model_dump()
    )

    db.add(db_batch)
    db.commit()
    db.refresh(db_batch)

    return db_batch


@app.get("/batches/", response_model=list[schemas.BatchRead])
def get_batches(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    return (
        db.query(models.Batch)
        .offset(skip)
        .limit(limit)
        .all()
    )


# ==========================================
# FACULTY - SUBJECT ASSIGNMENT
# ==========================================

@app.post(
    "/faculty-subjects/",
    response_model=schemas.FacultySubjectRead
)
def create_faculty_subject(
    assignment: schemas.FacultySubjectCreate,
    db: Session = Depends(get_db)
):
    db_assignment = models.FacultySubject(
        **assignment.model_dump()
    )

    db.add(db_assignment)
    db.commit()
    db.refresh(db_assignment)

    return db_assignment


@app.get(
    "/faculty-subjects/",
    response_model=list[schemas.FacultySubjectRead]
)
def get_faculty_subjects(
    db: Session = Depends(get_db)
):
    return db.query(
        models.FacultySubject
    ).all()


# ==========================================
# TIME SLOTS
# ==========================================

@app.post(
    "/time-slots/",
    response_model=schemas.TimeSlotRead
)
def create_time_slot(
    time_slot: schemas.TimeSlotCreate,
    db: Session = Depends(get_db)
):
    db_time_slot = models.TimeSlot(
        **time_slot.model_dump()
    )

    db.add(db_time_slot)
    db.commit()
    db.refresh(db_time_slot)

    return db_time_slot


@app.get(
    "/time-slots/",
    response_model=list[schemas.TimeSlotRead]
)
def get_time_slots(
    db: Session = Depends(get_db)
):
    return db.query(
        models.TimeSlot
    ).all()


# ==========================================
# TIMETABLE ENTRIES
# ==========================================

@app.post(
    "/timetable/",
    response_model=schemas.TimetableEntryRead
)
def create_timetable_entry(
    entry: schemas.TimetableEntryCreate,
    db: Session = Depends(get_db)
):
    db_entry = models.TimetableEntry(
        **entry.model_dump()
    )

    db.add(db_entry)
    db.commit()
    db.refresh(db_entry)

    return db_entry


@app.get(
    "/timetable/",
    response_model=list[schemas.TimetableEntryRead]
)
def get_timetable(
    db: Session = Depends(get_db)
):
    return db.query(
        models.TimetableEntry
    ).all()