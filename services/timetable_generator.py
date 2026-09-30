from typing import Iterable

from sqlalchemy.orm import Session

import models

DAY_ORDER = {d: i for i, d in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])}


def _minutes(value: str) -> int:
    try:
        hours, minutes = value.split(":", 1)
        return int(hours) * 60 + int(minutes[:2])
    except Exception as exc:
        raise ValueError(f"Invalid time '{value}'. Use HH:MM.") from exc


def _hhmm(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def _inside_recess(start: int, end: int, recess_start: int | None, recess_end: int | None) -> bool:
    if recess_start is None or recess_end is None:
        return False
    return start < recess_end and end > recess_start


def _sorted_slots(slots: Iterable[models.TimeSlot], slot_minutes: int):
    return sorted(
        slots,
        key=lambda s: (DAY_ORDER.get(s.day, 99), _minutes(s.start_time), _minutes(s.end_time)),
    )


def build_time_slots(db: Session, config: models.TimetableConfiguration):
    start = _minutes(config.college_start)
    end = _minutes(config.college_end)
    recess_start = _minutes(config.recess_start) if config.recess_start else None
    recess_end = _minutes(config.recess_end) if config.recess_end else None
    days = [x.strip() for x in config.working_days.split(",") if x.strip()]

    db.query(models.TimeSlot).delete(synchronize_session=False)

    slots: list[models.TimeSlot] = []
    for day in days:
        cursor = start
        while cursor + config.slot_minutes <= end:
            slot_end = cursor + config.slot_minutes
            if not _inside_recess(cursor, slot_end, recess_start, recess_end):
                slot = models.TimeSlot(
                    day=day,
                    start_time=_hhmm(cursor),
                    end_time=_hhmm(slot_end),
                )
                db.add(slot)
                slots.append(slot)
            cursor += config.slot_minutes

    db.flush()
    return _sorted_slots(slots, config.slot_minutes)


def generate_timetable(db: Session):
    requirements = db.query(models.TimetableRequirement).all()
    if not requirements:
        return False, "No timetable requirements configured."

    faculties = {x.id: x for x in db.query(models.Faculty).all()}
    subjects = {x.id: x for x in db.query(models.Subject).all()}
    batches = {x.id: x for x in db.query(models.Batch).all()}
    rooms = db.query(models.Room).all()
    slots = db.query(models.TimeSlot).all()
    config = db.query(models.TimetableConfiguration).order_by(models.TimetableConfiguration.id.desc()).first()

    if not config:
        return False, "No timetable configuration found."
    if not faculties:
        return False, "No faculty found."
    if not subjects:
        return False, "No subjects found."
    if not batches:
        return False, "No batches found."
    if not rooms:
        return False, "No rooms found."
    if not slots:
        return False, "No usable time slots found. Check the college timing, recess and working days."

    slot_minutes = config.slot_minutes
    ordered_slots = _sorted_slots(slots, slot_minutes)
    faculty_subjects = {(x.faculty_id, x.subject_id) for x in db.query(models.FacultySubject).all()}

    busy_faculty: set[tuple[int, int]] = set()
    busy_batch: set[tuple[int, int]] = set()
    busy_room: set[tuple[int, int]] = set()
    faculty_day_load: dict[tuple[int, str], int] = {}
    batch_day_load: dict[tuple[int, str], int] = {}
    subject_day_count: dict[tuple[int, int, str], int] = {}
    generated: list[dict] = []

    def candidate_blocks(requirement):
        duration_slots = max(1, requirement.duration_minutes // slot_minutes)
        output = []
        for index, first in enumerate(ordered_slots):
            if index + duration_slots > len(ordered_slots):
                break
            block = ordered_slots[index : index + duration_slots]
            if len(block) != duration_slots:
                continue
            if any(s.day != first.day for s in block):
                continue
            starts = [_minutes(s.start_time) for s in block]
            expected = starts[0]
            if any((start != expected + slot_minutes * offset) for offset, start in enumerate(starts)):
                continue
            output.append(tuple(block))
        return output

    def score(requirement, block):
        day = block[0].day
        same_subject = subject_day_count.get((requirement.batch_id, requirement.subject_id, day), 0)
        batch_load = batch_day_load.get((requirement.batch_id, day), 0)
        faculty_load = faculty_day_load.get((requirement.faculty_id, day), 0)
        return (
            same_subject * 10000
            + batch_load * 100
            + faculty_load * 25
            + _minutes(block[0].start_time) / 100.0
        )

    requirement_order = sorted(
        requirements,
        key=lambda r: (
            0 if subjects.get(r.subject_id) and subjects[r.subject_id].is_practical else 1,
            -r.duration_minutes,
            -r.lectures_per_week,
            r.batch_id,
            r.subject_id,
        ),
    )

    for requirement in requirement_order:
        if requirement.batch_id not in batches:
            return False, f"Batch {requirement.batch_id} does not exist."
        if requirement.subject_id not in subjects:
            return False, f"Subject {requirement.subject_id} does not exist."
        if requirement.faculty_id not in faculties:
            return False, f"Faculty {requirement.faculty_id} does not exist."

        subject = subjects[requirement.subject_id]
        faculty = faculties[requirement.faculty_id]
        if requirement.duration_minutes % slot_minutes != 0:
            return False, f"{subject.name}: duration must be a multiple of {slot_minutes} minutes."
        if faculty_subjects and (requirement.faculty_id, requirement.subject_id) not in faculty_subjects:
            return False, f"{faculty.name} is not mapped to {subject.name}. Add that faculty-subject mapping first."

        matching_rooms = [r for r in rooms if (not subject.is_practical) or r.is_lab]
        if not matching_rooms:
            return False, f"No lab room is available for practical subject {subject.name}."

        candidates = candidate_blocks(requirement)
        scheduled = 0
        while scheduled < requirement.lectures_per_week:
            feasible = []
            for block in candidates:
                day = block[0].day
                if subject_day_count.get((requirement.batch_id, requirement.subject_id, day), 0) >= requirement.max_per_day:
                    continue

                if faculty_day_load.get((requirement.faculty_id, day), 0) + len(block) > faculty.max_daily_lectures:
                    continue

                if any((requirement.faculty_id, slot.id) in busy_faculty for slot in block):
                    continue
                if any((requirement.batch_id, slot.id) in busy_batch for slot in block):
                    continue

                rooms_for_block = [
                    room
                    for room in matching_rooms
                    if all((room.id, slot.id) not in busy_room for slot in block)
                ]
                if not rooms_for_block:
                    continue

                feasible.append((score(requirement, block), block, rooms_for_block[0]))

            if not feasible:
                break

            _, block, room = min(feasible, key=lambda item: item[0])
            for slot in block:
                generated.append(
                    {
                        "faculty_id": requirement.faculty_id,
                        "subject_id": requirement.subject_id,
                        "batch_id": requirement.batch_id,
                        "room_id": room.id,
                        "time_slot_id": slot.id,
                        "is_practical": subject.is_practical,
                    }
                )
                busy_faculty.add((requirement.faculty_id, slot.id))
                busy_batch.add((requirement.batch_id, slot.id))
                busy_room.add((room.id, slot.id))
                faculty_day_load[(requirement.faculty_id, slot.day)] = faculty_day_load.get((requirement.faculty_id, slot.day), 0) + 1
                batch_day_load[(requirement.batch_id, slot.day)] = batch_day_load.get((requirement.batch_id, slot.day), 0) + 1

            subject_day_count[(requirement.batch_id, requirement.subject_id, block[0].day)] = (
                subject_day_count.get((requirement.batch_id, requirement.subject_id, block[0].day), 0) + 1
            )
            scheduled += 1

        if scheduled < requirement.lectures_per_week:
            batch_name = batches[requirement.batch_id].name
            return (
                False,
                f"Could not schedule {scheduled}/{requirement.lectures_per_week} lectures of {subject.name} for {batch_name}. "
                "Try fewer lectures, more working days, a larger college time range, or higher faculty daily limits.",
            )

    for data in generated:
        db.add(models.TimetableEntry(**data))
    db.flush()
    return True, f"Timetable generated successfully with {len(generated)} scheduled blocks."
