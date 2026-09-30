from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class FacultyBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    max_daily_lectures: int = Field(default=4, ge=1, le=12)


class FacultyCreate(FacultyBase):
    pass


class FacultyRead(FacultyBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class RoomBase(BaseModel):
    room_number: str = Field(min_length=1, max_length=100)
    is_lab: bool = False


class RoomCreate(RoomBase):
    pass


class RoomRead(RoomBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class SubjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    is_practical: bool = False


class SubjectCreate(SubjectBase):
    pass


class SubjectRead(SubjectBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class BatchBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class BatchCreate(BatchBase):
    pass


class BatchRead(BatchBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class FacultySubjectBase(BaseModel):
    faculty_id: int
    subject_id: int


class FacultySubjectCreate(FacultySubjectBase):
    pass


class FacultySubjectRead(FacultySubjectBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class TimeSlotBase(BaseModel):
    day: str
    start_time: str
    end_time: str


class TimeSlotCreate(TimeSlotBase):
    pass


class TimeSlotRead(TimeSlotBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


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
    model_config = ConfigDict(from_attributes=True)


class UserBase(BaseModel):
    name: str
    email: str
    role: str
    faculty_id: Optional[int] = None
    batch_id: Optional[int] = None


class UserCreate(UserBase):
    pass


class UserRead(UserBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    username: str
    password: str
    role: str


class SubstitutionRequestBase(BaseModel):
    timetable_entry_id: int
    original_faculty_id: int
    substitute_faculty_id: Optional[int] = None
    reason: Optional[str] = None
    status: str = "PENDING"


class SubstitutionRequestCreate(SubstitutionRequestBase):
    pass


class SubstitutionRequestRead(SubstitutionRequestBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class NotificationBase(BaseModel):
    user_id: int
    message: str
    is_read: bool = False


class NotificationCreate(NotificationBase):
    pass


class NotificationRead(NotificationBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class CalendarEventBase(BaseModel):
    timetable_entry_id: int
    user_id: int
    event_uid: str


class CalendarEventCreate(CalendarEventBase):
    pass


class CalendarEventRead(CalendarEventBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class RequirementInput(BaseModel):
    batch_id: int
    subject_id: int
    faculty_id: int
    lectures_per_week: int = Field(ge=1, le=50)
    duration_minutes: int = Field(default=60, ge=30, le=240)
    max_per_day: int = Field(default=1, ge=1, le=10)


class TimetableConfigurationInput(BaseModel):
    working_days: List[str] = Field(min_length=1, max_length=7)
    college_start: str
    college_end: str
    recess_start: Optional[str] = None
    recess_end: Optional[str] = None
    slot_minutes: int = Field(default=60, ge=30, le=120)
    requirements: List[RequirementInput] = Field(min_length=1, max_length=500)
    faculty_daily_limits: Dict[str, int] = Field(default_factory=dict)


class TimetableRequirementRead(BaseModel):
    id: int
    batch_id: int
    subject_id: int
    faculty_id: int
    lectures_per_week: int
    duration_minutes: int
    max_per_day: int
    model_config = ConfigDict(from_attributes=True)
