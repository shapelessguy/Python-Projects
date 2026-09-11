from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

ColType = Literal["number", "text", "bool", "enum"]


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
