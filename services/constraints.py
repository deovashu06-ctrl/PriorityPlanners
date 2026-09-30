from sqlalchemy import func
from sqlalchemy.orm import Session

import models


def check_faculty_conflict(db: Session, faculty_id: int, time_slot_id: int):
    exists = db.query(models.TimetableEntry).filter(
        models.TimetableEntry.faculty_id == faculty_id,
        models.TimetableEntry.time_slot_id == time_slot_id,
    ).first()
    return (False, "Faculty is already scheduled in this time slot.") if exists else (True, "Faculty is available.")


def check_room_conflict(db: Session, room_id: int, time_slot_id: int):
    exists = db.query(models.TimetableEntry).filter(
        models.TimetableEntry.room_id == room_id,
        models.TimetableEntry.time_slot_id == time_slot_id,
    ).first()
    return (False, "Room is already occupied in this time slot.") if exists else (True, "Room is available.")


def check_batch_conflict(db: Session, batch_id: int, time_slot_id: int):
    exists = db.query(models.TimetableEntry).filter(
        models.TimetableEntry.batch_id == batch_id,
        models.TimetableEntry.time_slot_id == time_slot_id,
    ).first()
    return (False, "Batch is already scheduled in this time slot.") if exists else (True, "Batch is available.")


def check_faculty_daily_limit(db: Session, faculty_id: int, time_slot_id: int):
    slot = db.query(models.TimeSlot).filter(models.TimeSlot.id == time_slot_id).first()
    faculty = db.query(models.Faculty).filter(models.Faculty.id == faculty_id).first()
    if not slot:
        return False, "Time slot does not exist."
    if not faculty:
        return False, "Faculty does not exist."
    count = (
        db.query(func.count(models.TimetableEntry.id))
        .join(models.TimeSlot, models.TimetableEntry.time_slot_id == models.TimeSlot.id)
        .filter(
            models.TimetableEntry.faculty_id == faculty_id,
            models.TimeSlot.day == slot.day,
        )
        .scalar()
        or 0
    )
    if count >= faculty.max_daily_lectures:
        return False, f"Faculty has reached the maximum daily limit of {faculty.max_daily_lectures} lectures."
    return True, "Faculty daily limit is not exceeded."


def check_all_constraints(db: Session, faculty_id: int, room_id: int, batch_id: int, time_slot_id: int):
    checks = (
        (check_faculty_conflict, (faculty_id, time_slot_id)),
        (check_room_conflict, (room_id, time_slot_id)),
        (check_batch_conflict, (batch_id, time_slot_id)),
        (check_faculty_daily_limit, (faculty_id, time_slot_id)),
    )
    for fn, args in checks:
        ok, message = fn(db, *args)
        if not ok:
            return False, message
    return True, "All hard constraints passed."
