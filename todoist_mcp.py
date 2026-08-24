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
MAX_COLOR_LENGTH = 50


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


def _get_all_projects(api: TodoistAPI) -> list:
    """Retrieves all projects from Todoist API across batches."""
    projects = []
    for batch in api.get_projects():
        projects.extend(batch)
    return projects


def _find_project_id(api: TodoistAPI, project_name: str) -> Optional[str]:
    """Resolves matching Todoist project ID by project name."""
    project_id, _ = _resolve_project(api, project_name)
    return project_id


def _resolve_project(api: TodoistAPI, name_or_id: str) -> tuple[Optional[str], Optional[str]]:
    """Resolves project ID and display name from either a project ID or project name.

    Returns:
        tuple[Optional[str], Optional[str]]: (project_id, project_name) or (None, None)
    """
    clean_identifier = name_or_id.strip() if isinstance(name_or_id, str) else ""
    if not clean_identifier:
        return None, None

    try:
        projects = _get_all_projects(api)
    except Exception as e:
        logger.error(
            "Failed to retrieve projects list for project resolution (error_type=%s)",
            type(e).__name__,
            exc_info=False,
        )
        return None, None

    # 1. Direct ID match
    for project in projects:
        if str(getattr(project, "id", "")) == clean_identifier:
            return str(project.id), getattr(project, "name", "Bilinmeyen Proje")

    # 2. Inbox query alias check
    normalized_target = _normalize(clean_identifier)
    inbox_aliases = ["gelen kutusu", "inbox", "gelenkutusu", "inbox/gelen kutusu"]
    if normalized_target in inbox_aliases:
        for project in projects:
            if getattr(project, "is_inbox_project", False):
                return str(project.id), getattr(project, "name", "Gelen Kutusu")
            if _normalize(getattr(project, "name", "")) in inbox_aliases:
                return str(project.id), getattr(project, "name", "Gelen Kutusu")

    # 3. Exact name match
    for project in projects:
        if _normalize(getattr(project, "name", "")) == normalized_target:
            return str(project.id), getattr(project, "name", "")

    # 4. Partial name match
    for project in projects:
        if normalized_target in _normalize(getattr(project, "name", "")):
            return str(project.id), getattr(project, "name", "")

    return None, None


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
    """Marks an existing Todoist task as completed.

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


@mcp.tool()
def update_task(
    task_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_TASK_ID_LENGTH,
            description="The Todoist Task ID to update (required).",
        ),
    ],
    content: Annotated[
        Optional[str],
        Field(
            default=None,
            max_length=MAX_CONTENT_LENGTH,
            description="New title/content for the task (optional).",
        ),
    ] = None,
    description: Annotated[
        Optional[str],
        Field(
            default=None,
            max_length=MAX_DESCRIPTION_LENGTH,
            description="New description or notes for the task (optional).",
        ),
    ] = None,
    project_name: Annotated[
        Optional[str],
        Field(
            default=None,
            max_length=MAX_PROJECT_NAME_LENGTH,
            description="Target project name to move the task into (optional).",
        ),
    ] = None,
    due_string: Annotated[
        Optional[str],
        Field(
            default=None,
            max_length=MAX_DUE_STRING_LENGTH,
            description="New natural language due date/time (e.g. 'tomorrow at 15:00', 'no date', optional).",
        ),
    ] = None,
    priority: Annotated[
        Optional[int],
        Field(
            default=None,
            ge=1,
            le=4,
            description="New priority level from 1 (Normal) to 4 (Urgent) (optional).",
        ),
    ] = None,
) -> str:
    """Updates an existing Todoist task's title, description, due date, priority, or moves it to another project.

    Args:
        task_id: The ID of the Todoist task to update (required).
        content: New title/content for the task.
        description: New description or notes for the task.
        project_name: Name of target project to move task into.
        due_string: New natural language due date or schedule.
        priority: Priority integer between 1 (Normal) and 4 (Urgent).
    """
    clean_task_id = str(task_id).strip() if task_id is not None else ""
    if not clean_task_id:
        return "❌ Invalid input: Task ID cannot be empty or whitespace."
    if len(clean_task_id) > MAX_TASK_ID_LENGTH:
        return f"❌ Invalid input: Task ID exceeds maximum length of {MAX_TASK_ID_LENGTH} characters."

    clean_content = content.strip() if isinstance(content, str) else None
    if clean_content is not None and len(clean_content) > MAX_CONTENT_LENGTH:
        return f"❌ Invalid input: Task content exceeds maximum length of {MAX_CONTENT_LENGTH} characters."

    clean_description = description.strip() if isinstance(description, str) else None
    if clean_description is not None and len(clean_description) > MAX_DESCRIPTION_LENGTH:
        return f"❌ Invalid input: Task description exceeds maximum length of {MAX_DESCRIPTION_LENGTH} characters."

    clean_project_name = project_name.strip() if isinstance(project_name, str) else None
    if clean_project_name is not None and len(clean_project_name) > MAX_PROJECT_NAME_LENGTH:
        return f"❌ Invalid input: Project name exceeds maximum length of {MAX_PROJECT_NAME_LENGTH} characters."

    clean_due_string = due_string.strip() if isinstance(due_string, str) else None
    if clean_due_string is not None and len(clean_due_string) > MAX_DUE_STRING_LENGTH:
        return f"❌ Invalid input: Due date string exceeds maximum length of {MAX_DUE_STRING_LENGTH} characters."

    if priority is not None and (not isinstance(priority, int) or priority < 1 or priority > 4):
        return "❌ Invalid input: Priority must be an integer between 1 (Normal) and 4 (Urgent)."

    if (
        clean_content is None
        and clean_description is None
        and clean_project_name is None
        and clean_due_string is None
        and priority is None
    ):
        return "⚠️ Güncellenecek hiçbir alan belirtilmedi. Lütfen en az bir parametre (content, description, project_name, due_string, priority) girin."

    try:
        api = _get_api_client()
        updated_fields = []

        # 1. Update task attributes if provided
        update_kwargs = {}
        if clean_content is not None:
            update_kwargs["content"] = clean_content
            updated_fields.append(f"Başlık: '{clean_content}'")
        if clean_description is not None:
            update_kwargs["description"] = clean_description
            updated_fields.append(f"Açıklama: '{clean_description}'")
        if clean_due_string is not None:
            update_kwargs["due_string"] = clean_due_string
            updated_fields.append(f"Tarih: '{clean_due_string}'")
        if priority is not None:
            update_kwargs["priority"] = priority
            updated_fields.append(f"Öncelik: p{priority}")

        if update_kwargs:
            api.update_task(task_id=clean_task_id, **update_kwargs)

        # 2. Move task to target project if project_name provided
        if clean_project_name is not None:
            project_id = _find_project_id(api, clean_project_name)
            if not project_id:
                return f"⚠️ Görev güncellendi fakat hedef proje bulunamadı: '{clean_project_name}'."
            api.move_task(task_id=clean_task_id, project_id=project_id)
            updated_fields.append(f"Hedef Proje: '{clean_project_name}' (ID: {project_id})")

        changes_summary = "\n".join([f"• {field}" for field in updated_fields])
        return (
            f"✅ Görev başarıyla güncellendi (ID: {clean_task_id})!\n"
            f"Yapılan değişiklikler:\n"
            f"{changes_summary}"
        )
    except Exception as e:
        logger.error(
            "Failed to update task in Todoist (task_id=%s, error_type=%s)",
            clean_task_id,
            type(e).__name__,
            exc_info=False,
        )
        return f"❌ Failed to update task in Todoist (ID: {clean_task_id}). Check server logs for details."


@mcp.tool()
def delete_task(
    task_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_TASK_ID_LENGTH,
            description="The Todoist Task ID to delete permanently (required).",
        ),
    ],
) -> str:
    """Permanently deletes a task from Todoist by ID.

    Args:
        task_id: The ID of the Todoist task to delete permanently.
    """
    clean_task_id = str(task_id).strip() if task_id is not None else ""
    if not clean_task_id:
        return "❌ Invalid input: Task ID cannot be empty or whitespace."
    if len(clean_task_id) > MAX_TASK_ID_LENGTH:
        return f"❌ Invalid input: Task ID exceeds maximum length of {MAX_TASK_ID_LENGTH} characters."

    try:
        api = _get_api_client()
        success = api.delete_task(task_id=clean_task_id)
        if success:
            return f"🗑️ Görev kalıcı olarak silindi (ID: {clean_task_id})."
        else:
            return f"⚠️ Görev silinemedi (ID: {clean_task_id}). Görev zaten silinmiş veya bulunamıyor olabilir."
    except Exception as e:
        logger.error(
            "Failed to delete task in Todoist (task_id=%s, error_type=%s)",
            clean_task_id,
            type(e).__name__,
            exc_info=False,
        )
        return f"❌ Failed to delete task in Todoist (ID: {clean_task_id}). Check server logs for details."


@mcp.tool()
def list_projects() -> str:
    """Lists all user projects in Todoist with their names, IDs, and details."""
    try:
        api = _get_api_client()
        projects = _get_all_projects(api)

        if not projects:
            return "ℹ️ Todoist hesabınızda herhangi bir proje bulunamadı."

        lines = [f"📁 Mevcut Projeler (Toplam: {len(projects)}):", ""]
        for idx, project in enumerate(projects, start=1):
            is_inbox = " [Gelen Kutusu]" if getattr(project, "is_inbox_project", False) else ""
            is_fav = " ⭐" if getattr(project, "is_favorite", False) else ""
            color_info = f", Renk: {project.color}" if getattr(project, "color", None) else ""
            lines.append(f"{idx}. [{project.id}] {project.name}{is_inbox}{is_fav}{color_info}")
            if getattr(project, "url", None):
                lines.append(f"   • URL: {project.url}")

        return "\n".join(lines).strip()
    except Exception as e:
        logger.error(
            "Failed to list projects from Todoist (error_type=%s)",
            type(e).__name__,
            exc_info=False,
        )
        return "❌ Failed to list projects from Todoist. Check server logs for details."


@mcp.tool()
def create_project(
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_PROJECT_NAME_LENGTH,
            description="The name of the new project (required).",
        ),
    ],
    color: Annotated[
        Optional[str],
        Field(
            default=None,
            max_length=MAX_COLOR_LENGTH,
            description="Color name for the project icon (e.g. 'berry_red', 'charcoal', 'teal', optional).",
        ),
    ] = None,
) -> str:
    """Creates a new project in Todoist.

    Args:
        name: Name of the project (must not be empty, max 120 chars).
        color: Optional color name (e.g. 'berry_red', 'sky_blue', 'mint_green').
    """
    clean_name = name.strip() if isinstance(name, str) else ""
    if not clean_name:
        return "❌ Invalid input: Project name cannot be empty or whitespace."
    if len(clean_name) > MAX_PROJECT_NAME_LENGTH:
        return f"❌ Invalid input: Project name exceeds maximum length of {MAX_PROJECT_NAME_LENGTH} characters."

    clean_color = color.strip().lower() if isinstance(color, str) else None
    if clean_color and len(clean_color) > MAX_COLOR_LENGTH:
        return f"❌ Invalid input: Color name exceeds maximum length of {MAX_COLOR_LENGTH} characters."

    try:
        api = _get_api_client()
        kwargs = {}
        if clean_color:
            kwargs["color"] = clean_color

        project = api.add_project(name=clean_name, **kwargs)

        color_str = f"\n• Renk: {project.color}" if getattr(project, "color", None) else ""
        url_str = f"\n• URL: {project.url}" if getattr(project, "url", None) else ""

        return (
            f"✅ Proje başarıyla oluşturuldu!\n"
            f"• ID: {project.id}\n"
            f"• İsim: {project.name}"
            f"{color_str}"
            f"{url_str}"
        )
    except Exception as e:
        logger.error(
            "Failed to create project in Todoist (name=%s, error_type=%s)",
            clean_name,
            type(e).__name__,
            exc_info=False,
        )
        return f"❌ Failed to create project '{clean_name}' in Todoist. Check server logs for details."


@mcp.tool()
def delete_project(
    project_name_or_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_PROJECT_NAME_LENGTH,
            description="The Todoist Project ID or Project Name to delete (required).",
        ),
    ],
) -> str:
    """Deletes a project from Todoist by either its ID or project name.

    Args:
        project_name_or_id: The ID or name of the project to delete.
    """
    clean_identifier = str(project_name_or_id).strip() if project_name_or_id is not None else ""
    if not clean_identifier:
        return "❌ Invalid input: Project identifier cannot be empty or whitespace."
    if len(clean_identifier) > MAX_PROJECT_NAME_LENGTH:
        return f"❌ Invalid input: Project identifier exceeds maximum length of {MAX_PROJECT_NAME_LENGTH} characters."

    try:
        api = _get_api_client()
        project_id, project_name = _resolve_project(api, clean_identifier)

        if not project_id:
            return f"⚠️ Silinecek proje bulunamadı: '{clean_identifier}'."

        success = api.delete_project(project_id=project_id)
        display_name = f"'{project_name}' (ID: {project_id})" if project_name else f"ID: {project_id}"

        if success:
            return f"🗑️ Proje başarıyla silindi: {display_name}."
        else:
            return f"⚠️ Proje silinemedi: {display_name}."
    except Exception as e:
        logger.error(
            "Failed to delete project in Todoist (identifier=%s, error_type=%s)",
            clean_identifier,
            type(e).__name__,
            exc_info=False,
        )
        return f"❌ Failed to delete project '{clean_identifier}' in Todoist. Check server logs for details."


if __name__ == "__main__":
    mcp.run()
