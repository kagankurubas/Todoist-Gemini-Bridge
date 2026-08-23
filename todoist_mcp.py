"""
Todoist Model Context Protocol (MCP) Server
Integrates Todoist API tools via FastMCP over STDIO.
"""

import logging
import os
from typing import Annotated, Optional
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from todoist_api_python.api import TodoistAPI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("todoist_mcp")

load_dotenv()

mcp = FastMCP("Todoist")

MAX_CONTENT_LENGTH = 500
MAX_DESCRIPTION_LENGTH = 4096
MAX_PROJECT_NAME_LENGTH = 120
MAX_DUE_STRING_LENGTH = 150
MAX_FILTER_QUERY_LENGTH = 500
MAX_TASK_ID_LENGTH = 100


def _get_api_client() -> TodoistAPI:
    """Reads TODOIST_API_TOKEN from environment and returns a TodoistAPI client instance."""
    token = os.getenv("TODOIST_API_TOKEN")
    if not token or not token.strip():
        logger.error("TODOIST_API_TOKEN is missing or empty in environment configuration", exc_info=False)
        raise RuntimeError("Todoist API authentication token is not configured.")
    return TodoistAPI(token.strip())


def _normalize(text: str) -> str:
    """Normalizes string for robust case-insensitive comparison (supporting Turkish and Unicode chars)."""
    return text.strip().lower().replace("ı", "i").replace("İ", "i").replace("i̇", "i")


def _find_project_id(api: TodoistAPI, project_name: str) -> Optional[str]:
    """Resolves matching Todoist project ID by project name."""
    normalized_target = _normalize(project_name)

    inbox_aliases = ["gelen kutusu", "inbox", "gelenkutusu", "inbox/gelen kutusu"]
    is_inbox_query = normalized_target in inbox_aliases

    try:
        projects = []
        for batch in api.get_projects():
            projects.extend(batch)
    except Exception as e:
        logger.error(
            "Failed to retrieve projects list for project resolution (error_type=%s)",
            type(e).__name__,
            exc_info=False,
        )
        return None

    if is_inbox_query:
        for project in projects:
            if getattr(project, "is_inbox_project", False):
                return project.id
            if _normalize(getattr(project, "name", "")) in inbox_aliases:
                return project.id
        return None

    for project in projects:
        if _normalize(getattr(project, "name", "")) == normalized_target:
            return project.id

    for project in projects:
        if normalized_target in _normalize(getattr(project, "name", "")):
            return project.id

    return None


@mcp.tool()
def create_task(
    content: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_CONTENT_LENGTH,
            description="The text content/title of the task (required).",
        ),
    ],
    description: Annotated[
        str,
        Field(
            default="",
            max_length=MAX_DESCRIPTION_LENGTH,
            description="Detailed description or notes for the task (optional).",
        ),
    ] = "",
    project_name: Annotated[
        str,
        Field(
            default="Gelen Kutusu",
            max_length=MAX_PROJECT_NAME_LENGTH,
            description="Target Todoist project name (defaults to 'Gelen Kutusu' / Inbox).",
        ),
    ] = "Gelen Kutusu",
    due_string: Annotated[
        Optional[str],
        Field(
            default=None,
            max_length=MAX_DUE_STRING_LENGTH,
            description="Natural language due date/time or recurring schedule (e.g. 'tomorrow at 14:00', 'every Monday').",
        ),
    ] = None,
    priority: Annotated[
        int,
        Field(
            default=1,
            ge=1,
            le=4,
            description="Task priority level from 1 (Normal) to 4 (Urgent).",
        ),
    ] = 1,
) -> str:
    """Creates a new task in Todoist with smart project resolution and natural language due dates.

    Args:
        content: Task title/content (must not be empty, max 500 chars).
        description: Task notes or description (max 4096 chars).
        project_name: Target project name (max 120 chars, defaults to 'Gelen Kutusu').
        due_string: Natural language date string (e.g. 'tomorrow at 14:00', max 150 chars).
        priority: Priority integer strictly between 1 (normal) and 4 (urgent).
    """
    clean_content = content.strip() if isinstance(content, str) else ""
    if not clean_content:
        return "❌ Invalid input: Task content cannot be empty or whitespace."
    if len(clean_content) > MAX_CONTENT_LENGTH:
        return f"❌ Invalid input: Task content exceeds maximum length of {MAX_CONTENT_LENGTH} characters."

    clean_description = description.strip() if isinstance(description, str) else ""
    if len(clean_description) > MAX_DESCRIPTION_LENGTH:
        return f"❌ Invalid input: Task description exceeds maximum length of {MAX_DESCRIPTION_LENGTH} characters."

    clean_project_name = project_name.strip() if isinstance(project_name, str) else ""
    if len(clean_project_name) > MAX_PROJECT_NAME_LENGTH:
        return f"❌ Invalid input: Project name exceeds maximum length of {MAX_PROJECT_NAME_LENGTH} characters."

    clean_due_string = due_string.strip() if isinstance(due_string, str) else None
    if clean_due_string and len(clean_due_string) > MAX_DUE_STRING_LENGTH:
        return f"❌ Invalid input: Due date string exceeds maximum length of {MAX_DUE_STRING_LENGTH} characters."

    if not isinstance(priority, int) or priority < 1 or priority > 4:
        return "❌ Invalid input: Priority must be an integer between 1 (Normal) and 4 (Urgent)."

    try:
        api = _get_api_client()
        project_id = _find_project_id(api, clean_project_name) if clean_project_name else None

        task = api.add_task(
            content=clean_content,
            description=clean_description or None,
            project_id=project_id,
            due_string=clean_due_string or None,
            priority=priority,
        )

        due_info = task.due.string if task.due and task.due.string else (clean_due_string or "Belirtilmedi")
        project_display = clean_project_name if clean_project_name else "Gelen Kutusu"

        return (
            f"✅ Görev başarıyla oluşturuldu!\n"
            f"• ID: {task.id}\n"
            f"• Başlık: {task.content}\n"
            f"• Proje: {project_display}\n"
            f"• Öncelik: p{task.priority}\n"
            f"• Tarih / Tekrar: {due_info}\n"
            f"• URL: {task.url}"
        )
    except Exception as e:
        logger.error(
            "Failed to create task in Todoist (content_len=%d, error_type=%s)",
            len(clean_content),
            type(e).__name__,
            exc_info=False,
        )
        return "❌ Todoist task creation failed. Check server logs for details."


@mcp.tool()
def list_tasks(
    filter_query: Annotated[
        str,
        Field(
            default="today",
            min_length=1,
            max_length=MAX_FILTER_QUERY_LENGTH,
            description="Todoist filter query (e.g. 'today', 'tomorrow', 'overdue', 'p1', 'all').",
        ),
    ] = "today",
) -> str:
    """Lists open tasks in Todoist matching the specified filter query.

    Args:
        filter_query: Todoist filter query (e.g. 'today', 'p1', 'overdue', max 500 chars).
    """
    clean_query = filter_query.strip() if isinstance(filter_query, str) else ""
    if not clean_query:
        return "❌ Invalid input: Filter query cannot be empty or whitespace."
    if len(clean_query) > MAX_FILTER_QUERY_LENGTH:
        return f"❌ Invalid input: Filter query exceeds maximum length of {MAX_FILTER_QUERY_LENGTH} characters."

    try:
        api = _get_api_client()
        tasks = []
        for batch in api.filter_tasks(query=clean_query):
            tasks.extend(batch)

        if not tasks:
            return f"ℹ️ '{clean_query}' filtresine uygun açık görev bulunamadı."

        priority_labels = {4: "🔴 p4 (Çok Acil)", 3: "🟠 p3 (Yüksek)", 2: "🔵 p2 (Orta)", 1: "⚪ p1 (Normal)"}

        lines = [f"📋 Açık Görevler (Filtre: '{clean_query}', Toplam: {len(tasks)}):", ""]
        for idx, task in enumerate(tasks, start=1):
            due_str = task.due.string if task.due and task.due.string else "Tarih yok"
            p_str = priority_labels.get(task.priority, f"p{task.priority}")
            lines.append(f"{idx}. [{task.id}] {task.content}")
            lines.append(f"   • Öncelik: {p_str}")
            lines.append(f"   • Tarih: {due_str}")
            if task.description:
                lines.append(f"   • Açıklama: {task.description}")
            lines.append("")

        return "\n".join(lines).strip()
    except Exception as e:
        logger.error(
            "Failed to retrieve tasks from Todoist (filter_len=%d, error_type=%s)",
            len(clean_query),
            type(e).__name__,
            exc_info=False,
        )
        return "❌ Failed to retrieve tasks from Todoist. Check server logs for details."


@mcp.tool()
def complete_task(
    task_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_TASK_ID_LENGTH,
            description="The Todoist Task ID to complete (required).",
        ),
    ],
) -> str:
    """Marks an existing Todoist task as completed. This modifies the user's Todoist data.

    Args:
        task_id: The ID of the Todoist task to mark as completed (max 100 chars).
    """
    clean_task_id = str(task_id).strip() if task_id is not None else ""
    if not clean_task_id:
        return "❌ Invalid input: Task ID cannot be empty or whitespace."
    if len(clean_task_id) > MAX_TASK_ID_LENGTH:
        return f"❌ Invalid input: Task ID exceeds maximum length of {MAX_TASK_ID_LENGTH} characters."

    try:
        api = _get_api_client()
        success = api.complete_task(task_id=clean_task_id)
        if success:
            return f"✅ Görev başarıyla tamamlandı (ID: {clean_task_id})."
        else:
            return f"⚠️ Görev tamamlanamadı veya zaten tamamlanmış olabilir (ID: {clean_task_id})."
    except Exception as e:
        logger.error(
            "Failed to complete task in Todoist (task_id=%s, error_type=%s)",
            clean_task_id,
            type(e).__name__,
            exc_info=False,
        )
        return f"❌ Failed to complete task in Todoist (ID: {clean_task_id}). Check server logs for details."


if __name__ == "__main__":
    mcp.run()
