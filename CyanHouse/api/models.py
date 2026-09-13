from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

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
    shared: bool = False
    recur_freq: Optional[RecurFreq] = None
    recur_interval: int = Field(default=1, ge=1)
    recur_until: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class EventPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    all_day: Optional[bool] = None
    start_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    shared: Optional[bool] = None
    recur_freq: Optional[RecurFreq] = None
    recur_interval: Optional[int] = Field(default=None, ge=1)
    recur_until: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
