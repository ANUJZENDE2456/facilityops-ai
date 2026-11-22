from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class WorkOrderCreate(BaseModel):
    issue_type: str = Field(min_length=3, max_length=100)
    description: str | None = None
    maintenance_date: date | None = None
    priority: str = "MEDIUM"


class WorkOrderStatusUpdate(BaseModel):
    status: Literal[
        "SCHEDULED",
        "IN_PROGRESS",
        "COMPLETED",
        "CANCELLED",
    ]