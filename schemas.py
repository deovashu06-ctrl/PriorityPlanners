from pydantic import BaseModel


# =========================
# FACULTY
# =========================

class FacultyBase(BaseModel):
    name: str
    max_daily_lectures: int = 4


class FacultyCreate(FacultyBase):
    pass


class FacultyRead(FacultyBase):
    id: int

    class Config:
        from_attributes = True


# =========================
# ROOM
# =========================

class RoomBase(BaseModel):
    room_number: str
    is_lab: bool = False


class RoomCreate(RoomBase):
    pass


class RoomRead(RoomBase):
    id: int

    class Config:
        from_attributes = True


# =========================
# SUBJECT
# =========================

class SubjectBase(BaseModel):
    name: str
    is_practical: bool = False


class SubjectCreate(SubjectBase):
    pass


class SubjectRead(SubjectBase):
    id: int

    class Config:
        from_attributes = True


# =========================
# BATCH
# =========================

class BatchBase(BaseModel):
    name: str


class BatchCreate(BatchBase):
    pass


class BatchRead(BatchBase):
    id: int

    class Config:
        from_attributes = True


# =========================
# FACULTY ↔ SUBJECT
# =========================

class FacultySubjectBase(BaseModel):
    faculty_id: int
    subject_id: int


class FacultySubjectCreate(FacultySubjectBase):
    pass


class FacultySubjectRead(FacultySubjectBase):
    id: int

    class Config:
        from_attributes = True


# =========================
# TIME SLOT
# =========================

class TimeSlotBase(BaseModel):
    day: str
    start_time: str
    end_time: str


class TimeSlotCreate(TimeSlotBase):
    pass


class TimeSlotRead(TimeSlotBase):
    id: int

    class Config:
        from_attributes = True


# =========================
# TIMETABLE ENTRY
# =========================

class TimetableEntryBase(BaseModel):
    faculty_id: int
    subject_id: int
    batch_id: int
    room_id: int
    time_slot_id: int
    is_practical: bool = False


class TimetableEntryCreate(TimetableEntryBase):
    pass


class TimetableEntryRead(TimetableEntryBase):
    id: int

    class Config:
        from_attributes = True