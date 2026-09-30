from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from database import Base


class Faculty(Base):
    __tablename__ = "faculty"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    max_daily_lectures = Column(Integer, default=4, nullable=False)


class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, index=True)
    room_number = Column(String, unique=True, nullable=False, index=True)
    is_lab = Column(Boolean, default=False, nullable=False)


class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    is_practical = Column(Boolean, default=False, nullable=False)


class Batch(Base):
    __tablename__ = "batches"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)


class FacultySubject(Base):
    __tablename__ = "faculty_subjects"
    id = Column(Integer, primary_key=True, index=True)
    faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)


class TimeSlot(Base):
    __tablename__ = "time_slots"
    id = Column(Integer, primary_key=True, index=True)
    day = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)


class TimetableEntry(Base):
    __tablename__ = "timetable_entries"
    id = Column(Integer, primary_key=True, index=True)
    faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    time_slot_id = Column(Integer, ForeignKey("time_slots.id"), nullable=False)
    is_practical = Column(Boolean, default=False, nullable=False)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    role = Column(String, nullable=False)
    faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=True)


class SubstitutionRequest(Base):
    __tablename__ = "substitution_requests"
    id = Column(Integer, primary_key=True, index=True)
    timetable_entry_id = Column(Integer, ForeignKey("timetable_entries.id"), nullable=False)
    original_faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=False)
    substitute_faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=True)
    reason = Column(String, nullable=True)
    status = Column(String, default="PENDING", nullable=False)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(String, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    id = Column(Integer, primary_key=True, index=True)
    timetable_entry_id = Column(Integer, ForeignKey("timetable_entries.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_uid = Column(String, unique=True, nullable=False)


class TimetableRequirement(Base):
    __tablename__ = "timetable_requirements"
    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=False)
    lectures_per_week = Column(Integer, nullable=False)
    duration_minutes = Column(Integer, default=60, nullable=False)
    max_per_day = Column(Integer, default=1, nullable=False)


class TimetableConfiguration(Base):
    __tablename__ = "timetable_configurations"
    id = Column(Integer, primary_key=True, index=True)
    working_days = Column(String, nullable=False)
    college_start = Column(String, nullable=False)
    college_end = Column(String, nullable=False)
    recess_start = Column(String, nullable=True)
    recess_end = Column(String, nullable=True)
    slot_minutes = Column(Integer, default=60, nullable=False)
