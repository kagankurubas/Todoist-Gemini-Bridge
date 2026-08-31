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
    due_date: Optional[str] = Field(
        default=None,
        description="Specific due date in YYYY-MM-DD format (e.g. '2026-08-23').",
    )
    due_datetime: Optional[str] = Field(
        default=None,
        description="Specific due date and time in RFC 3339 / ISO 8601 format (e.g. '2026-08-23T15:30:00Z').",
    )
    due_lang: Optional[str] = Field(
        default="tr",
        description="2-letter language code for natural language due_string (defaults to 'tr').",
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
    parent_id: Optional[str] = Field(
        default=None,
        description="Optional ID of the parent task, making this task a sub-task.",
    )
    deadline_date: Optional[str] = Field(
        default=None,
        description=(
            "Optional official deadline date in YYYY-MM-DD format (e.g. '2026-09-01'). "
            "This is independent from due_string/due_date/due_datetime: due_* fields control "
            "when the task is scheduled to be worked on, while deadline_date represents Todoist's "
            "separate 'Deadline' concept (a hard due-by date shown distinctly in the UI)."
        ),
    )


class BatchTaskPayload(BaseModel):
    """Model representing a batch of tasks."""

    tasks: List[TaskPayload] = Field(
        default_factory=list,
        max_length=50,
        description="List of task payloads (maximum 50 tasks per batch).",
    )
