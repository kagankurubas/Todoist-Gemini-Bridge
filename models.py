from typing import List, Optional
from pydantic import BaseModel, Field


class TaskPayload(BaseModel):
    """Model representing a single task to be created in Todoist."""

    content: str = Field(
        ...,
        min_length=1,
        description="The text content/title of the task.",
    )
    project_name: str = Field(
        default="Odak & Gelişim",
        description="Target project name in Todoist (defaults to 'Odak & Gelişim').",
    )
    due_string: Optional[str] = Field(
        default=None,
        description="Natural language due date/time (e.g. 'tomorrow at 14:00', 'every Monday').",
    )
    priority: int = Field(
        default=1,
        ge=1,
        le=4,
        description="Task priority level from 1 (normal) to 4 (urgent).",
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional detailed description or additional notes for the task.",
    )


class BatchTaskPayload(BaseModel):
    """Model representing a batch of tasks."""

    tasks: List[TaskPayload] = Field(
        default_factory=list,
        description="List of task payloads.",
    )
