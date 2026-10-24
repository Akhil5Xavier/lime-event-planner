from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, model_validator

Category = Literal["concert", "sport", "theatre", "festival", "expo", "conference", "film", "community", "other"]
Role = Literal["admin", "manager"]
Priority = Literal["low", "medium", "high"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth / users ---

class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=200)


class UserOut(ORM):
    id: int
    email: str
    name: str | None
    role: Role
    is_active: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str | None = None
    role: Role = "manager"


class UserUpdate(BaseModel):
    name: str | None = None
    role: Role | None = None
    password: str | None = Field(default=None, min_length=8)
    is_active: bool | None = None


# --- venues ---

class VenueIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address: str | None = None
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    capacity: int | None = Field(default=None, ge=0)
    aliases: str | None = None
    scooter_zone_note: str | None = None


class VenueUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    capacity: int | None = Field(default=None, ge=0)
    aliases: str | None = None
    scooter_zone_note: str | None = None


class VenueOut(ORM):
    id: int
    name: str
    address: str | None
    lat: float
    lng: float
    capacity: int | None
    aliases: str | None
    scooter_zone_note: str | None


# --- events ---

class UserBrief(ORM):
    id: int
    email: str
    name: str | None


class EventOut(ORM):
    id: int
    source: str
    title: str
    category: str
    description: str | None
    start_at: datetime
    end_at: datetime | None
    venue: VenueOut | None
    expected_attendance: int | None
    attendance_override: int | None
    url: str | None
    image_url: str | None
    is_manual: bool
    created_by: UserBrief | None
    updated_by: UserBrief | None
    updated_at: datetime


class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    category: Category = "other"
    description: str | None = None
    start_at: AwareDatetime
    end_at: AwareDatetime | None = None
    venue_id: int | None = None
    new_venue: VenueIn | None = None
    expected_attendance: int | None = Field(default=None, ge=0)
    url: str | None = None


class EventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    category: Category | None = None
    description: str | None = None
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    venue_id: int | None = None
    expected_attendance: int | None = Field(default=None, ge=0)
    url: str | None = None


class AttendanceOverrideIn(BaseModel):
    attendance_override: int | None = Field(default=None, ge=0)


class WindowOut(ORM):
    kind: Literal["arrival", "departure"]
    start: datetime
    end: datetime


class RecommendationOut(ORM):
    attendance: int
    attendance_source: Literal["manual", "api", "capacity", "default"]
    extra_scooters: int
    priority: Priority
    windows: list[WindowOut]


class DayEventOut(EventOut):
    recommendation: RecommendationOut


class HotspotOut(ORM):
    name: str
    lat: float
    lng: float
    extra_scooters: int
    priority: Priority
    venue_ids: list[int]
    event_ids: list[int]
    windows: list[WindowOut]


class DaySummary(BaseModel):
    event_count: int
    total_attendance: int
    extra_scooters: int
    priority: Priority | None


class DayOut(BaseModel):
    date: date
    events: list[DayEventOut]
    hotspots: list[HotspotOut]
    summary: DaySummary


class CalendarDayOut(DaySummary):
    date: date


# --- ingestion ---

class IngestRunOut(ORM):
    id: int
    source: str
    trigger: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    fetched: int
    created: int
    updated: int
    duplicates: int
    error: str | None


class SourceStatus(BaseModel):
    name: str
    enabled: bool


# --- AI assistant ---

MAX_CHAT_TURNS = 20
MAX_CHAT_CHARS = 4000


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_CHAT_CHARS)


class ChatIn(BaseModel):
    messages: list[ChatMessageIn] = Field(min_length=1, max_length=MAX_CHAT_TURNS)

    @model_validator(mode="after")
    def _alternating_user_first_and_last(self):
        for i, m in enumerate(self.messages):
            expected = "user" if i % 2 == 0 else "assistant"
            if m.role != expected:
                raise ValueError("messages must alternate user/assistant, starting with user")
        if self.messages[-1].role != "user":
            raise ValueError("the last message must be from the user")
        return self


class ChatOut(BaseModel):
    reply: str
    tools_used: list[str]


class ChatStatus(BaseModel):
    enabled: bool
    provider: str
    model: str
