from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, StrictBool, StrictInt

ColType = Literal["number", "text", "bool", "enum"]
RecurFreq = Literal["daily", "weekly", "monthly", "yearly"]


class ColumnIn(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    unit: str = ""
    type: ColType = "number"
    options: list[str] = Field(default_factory=list)


class ColumnPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    type: Optional[ColType] = None
    position: Optional[int] = None
    options: Optional[list[str]] = None


class Column(BaseModel):
    key: str
    name: str
    description: str
    unit: str
    type: ColType
    position: int
    options: list[str] = Field(default_factory=list)


class UnitIn(BaseModel):
    unit: str = Field(min_length=1)


class ColumnOrderIn(BaseModel):
    keys: list[str]


class DayIn(BaseModel):
    values: dict[str, Any]


class BulkRow(BaseModel):
    date: str
    values: dict[str, Any]


class BulkIn(BaseModel):
    rows: list[BulkRow]


class EventIn(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    all_day: bool = True
    start_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    calendar_id: int
    recur_freq: Optional[RecurFreq] = None
    recur_interval: int = Field(default=1, ge=1)
    recur_until: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    alarm: StrictBool = False
    # Format enforced by the service layer (validate_alarm_ack in
    # calendar.py), since it depends on whether the event recurs: "" (not
    # acknowledged), else "true" for a plain event or a YYYY-MM-DD date --
    # the last occurrence acknowledged -- for a recurring one, compared
    # client-side against the series' latest visible occurrence to decide
    # whether the alarm is still due.
    alarm_ack: Optional[str] = None


class EventPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    all_day: Optional[bool] = None
    start_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    calendar_id: Optional[int] = None
    recur_freq: Optional[RecurFreq] = None
    recur_interval: Optional[int] = Field(default=None, ge=1)
    recur_until: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    alarm: Optional[StrictBool] = None
    alarm_ack: Optional[str] = None
    # Set together (or cleared together, both explicit null) -- see
    # calendar.py's _validate_snooze. Not on EventIn: a freshly created event
    # has nothing to snooze yet.
    alarm_snooze_occurrence: Optional[str] = None
    alarm_snooze_until: Optional[StrictInt] = None


class CalendarIn(BaseModel):
    name: str = Field(min_length=1)
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class CalendarPatch(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
