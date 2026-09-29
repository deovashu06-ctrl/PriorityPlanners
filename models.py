from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from database import Base


# =========================
# FACULTY
# =========================

class Faculty(Base):
    __tablename__ = "faculty"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)

    # Maximum lectures this faculty can take in one day
    max_daily_lectures = Column(Integer, default=4, nullable=False)


# =========================
# ROOM
# =========================

class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    room_number = Column(String, unique=True, nullable=False, index=True)

    # True = laboratory, False = normal classroom
    is_lab = Column(Boolean, default=False, nullable=False)


# =========================
# SUBJECT
# =========================

class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)

    # True = practical/laboratory subject
    is_practical = Column(Boolean, default=False, nullable=False)


# =========================
# BATCH
# =========================

class Batch(Base):
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)


# =========================
# FACULTY ↔ SUBJECT
# =========================

class FacultySubject(Base):
    __tablename__ = "faculty_subjects"

    id = Column(Integer, primary_key=True, index=True)

    faculty_id = Column(
        Integer,
        ForeignKey("faculty.id"),
        nullable=False
    )

    subject_id = Column(
        Integer,
        ForeignKey("subjects.id"),
        nullable=False
    )


# =========================
# TIME SLOT
# =========================

class TimeSlot(Base):
    __tablename__ = "time_slots"

    id = Column(Integer, primary_key=True, index=True)

    # Example: Monday
    day = Column(String, nullable=False)

    # Example: 09:00
    start_time = Column(String, nullable=False)

    # Example: 10:00
    end_time = Column(String, nullable=False)


# =========================
# TIMETABLE ENTRY
# =========================

class TimetableEntry(Base):
    __tablename__ = "timetable_entries"

    id = Column(Integer, primary_key=True, index=True)

    faculty_id = Column(
        Integer,
        ForeignKey("faculty.id"),
        nullable=False
    )

    subject_id = Column(
        Integer,
        ForeignKey("subjects.id"),
        nullable=False
    )

    batch_id = Column(
        Integer,
        ForeignKey("batches.id"),
        nullable=False
    )

    room_id = Column(
        Integer,
        ForeignKey("rooms.id"),
        nullable=False
    )

    time_slot_id = Column(
        Integer,
        ForeignKey("time_slots.id"),
        nullable=False
    )

    # Used later for laboratory/practical scheduling
    is_practical = Column(Boolean, default=False, nullable=False)