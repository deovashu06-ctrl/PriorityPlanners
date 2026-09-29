from sqlalchemy.orm import Session
from sqlalchemy import func

import models


# ==========================================
# 1. FACULTY DOUBLE-BOOKING CHECK
# ==========================================

def check_faculty_conflict(
    db: Session,
    faculty_id: int,
    time_slot_id: int
):
    existing_entry = db.query(
        models.TimetableEntry
    ).filter(
        models.TimetableEntry.faculty_id == faculty_id,
        models.TimetableEntry.time_slot_id == time_slot_id
    ).first()

    if existing_entry:
        return False, "Faculty is already scheduled in this time slot."

    return True, "Faculty is available."


# ==========================================
# 2. ROOM DOUBLE-BOOKING CHECK
# ==========================================

def check_room_conflict(
    db: Session,
    room_id: int,
    time_slot_id: int
):
    existing_entry = db.query(
        models.TimetableEntry
    ).filter(
        models.TimetableEntry.room_id == room_id,
        models.TimetableEntry.time_slot_id == time_slot_id
    ).first()

    if existing_entry:
        return False, "Room is already occupied in this time slot."

    return True, "Room is available."


# ==========================================
# 3. FACULTY DAILY LECTURE LIMIT
# ==========================================

def check_faculty_daily_limit(
    db: Session,
    faculty_id: int,
    time_slot_id: int
):
    # Find the selected time slot
    selected_slot = db.query(
        models.TimeSlot
    ).filter(
        models.TimeSlot.id == time_slot_id
    ).first()

    if not selected_slot:
        return False, "Time slot does not exist."

    # Find faculty
    faculty = db.query(
        models.Faculty
    ).filter(
        models.Faculty.id == faculty_id
    ).first()

    if not faculty:
        return False, "Faculty does not exist."

    # Count lectures already assigned on the same day
    daily_lectures = (
        db.query(func.count(models.TimetableEntry.id))
        .join(
            models.TimeSlot,
            models.TimetableEntry.time_slot_id
            == models.TimeSlot.id
        )
        .filter(
            models.TimetableEntry.faculty_id == faculty_id,
            models.TimeSlot.day == selected_slot.day
        )
        .scalar()
    )

    if daily_lectures >= faculty.max_daily_lectures:
        return (
            False,
            f"Faculty has reached the maximum "
            f"daily limit of {faculty.max_daily_lectures} lectures."
        )

    return True, "Faculty daily limit is not exceeded."


# ==========================================
# CHECK ALL HARD CONSTRAINTS
# ==========================================

def check_all_constraints(
    db: Session,
    faculty_id: int,
    room_id: int,
    time_slot_id: int
):
    # Faculty conflict
    valid, message = check_faculty_conflict(
        db,
        faculty_id,
        time_slot_id
    )

    if not valid:
        return False, message

    # Room conflict
    valid, message = check_room_conflict(
        db,
        room_id,
        time_slot_id
    )

    if not valid:
        return False, message

    # Faculty daily limit
    valid, message = check_faculty_daily_limit(
        db,
        faculty_id,
        time_slot_id
    )

    if not valid:
        return False, message

    return True, "All hard constraints passed."