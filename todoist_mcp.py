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
MAX_LABEL_NAME_LENGTH = 60
MAX_SECTION_NAME_LENGTH = 120
MAX_COMMENT_LENGTH = 4096


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


def _get_all_labels(api: TodoistAPI) -> list:
    """Retrieves all labels from Todoist API across batches."""
    labels = []
    for batch in api.get_labels():
        labels.extend(batch)
    return labels


def _get_all_sections(api: TodoistAPI, project_id: Optional[str] = None) -> list:
    """Retrieves sections from Todoist API across batches."""
    sections = []
    kwargs = {}
    if project_id:
        kwargs["project_id"] = project_id
    for batch in api.get_sections(**kwargs):
        sections.extend(batch)
    return sections


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


def _resolve_label(api: TodoistAPI, name_or_id: str) -> tuple[Optional[str], Optional[str]]:
    """Resolves label ID and name from either ID or name.

    Returns:
        tuple[Optional[str], Optional[str]]: (label_id, label_name) or (None, None)
    """
    clean_identifier = name_or_id.strip().lstrip("@") if isinstance(name_or_id, str) else ""
    if not clean_identifier:
        return None, None

    try:
        labels = _get_all_labels(api)
    except Exception as e:
        logger.error(
            "Failed to retrieve labels for resolution (error_type=%s)",
            type(e).__name__,
            exc_info=False,
        )
        return None, None

    # 1. Direct ID match
    for label in labels:
        if str(getattr(label, "id", "")) == clean_identifier:
            return str(label.id), getattr(label, "name", "")

    # 2. Exact name match
    normalized = _normalize(clean_identifier)
    for label in labels:
        if _normalize(getattr(label, "name", "")) == normalized:
            return str(label.id), getattr(label, "name", "")

    return None, None


def _resolve_section(api: TodoistAPI, name_or_id: str, project_id: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    """Resolves section ID and name from either ID or name.

    Returns:
        tuple[Optional[str], Optional[str]]: (section_id, section_name) or (None, None)
    """
    clean_identifier = name_or_id.strip() if isinstance(name_or_id, str) else ""
    if not clean_identifier:
        return None, None

    try:
        sections = _get_all_sections(api, project_id=project_id)
    except Exception as e:
        logger.error(
            "Failed to retrieve sections for resolution (error_type=%s)",
            type(e).__name__,
            exc_info=False,
        )
        return None, None

    # 1. Direct ID match
    for section in sections:
        if str(getattr(section, "id", "")) == clean_identifier:
            return str(section.id), getattr(section, "name", "")

    # 2. Exact name match
    normalized = _normalize(clean_identifier)
    for section in sections:
        if _normalize(getattr(section, "name", "")) == normalized:
            return str(section.id), getattr(section, "name", "")

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
    labels: Annotated[
        Optional[list[str]],
        Field(
            default=None,
            description="List of label names to attach to the task (e.g. ['work', 'urgent'], optional).",
        ),
    ] = None,
    section_name_or_id: Annotated[
        Optional[str],
        Field(
            default=None,
            max_length=MAX_SECTION_NAME_LENGTH,
            description="Target section name or ID within the project (optional).",
        ),
    ] = None,
    parent_id: Annotated[
        Optional[str],
        Field(
            default=None,
            max_length=MAX_TASK_ID_LENGTH,
            description="Bu görevi belirtilen Todoist görev ID'sinin alt görevi (subtask) yapar (opsiyonel).",
        ),
    ] = None,
) -> str:
    """Creates a new task in Todoist with smart project, section, label, and due date resolution.

    Args:
        content: Task title/content (must not be empty, max 500 chars).
        description: Task notes or description (max 4096 chars).
        project_name: Target project name (max 120 chars, defaults to 'Gelen Kutusu').
        due_string: Natural language date string (e.g. 'tomorrow at 14:00', max 150 chars).
        priority: Priority integer strictly between 1 (normal) and 4 (urgent).
        labels: Optional list of label strings to attach to the task.
        section_name_or_id: Optional target section name or ID within the project.
        parent_id: Optional Todoist task ID to create this task as a subtask of (max 100 chars).
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

    clean_labels = None
    if labels is not None:
        if isinstance(labels, list):
            clean_labels = [str(l).strip().lstrip("@") for l in labels if str(l).strip()]
        else:
            return "❌ Invalid input: Labels must be a list of strings."

    clean_section = section_name_or_id.strip() if isinstance(section_name_or_id, str) else None
    if clean_section and len(clean_section) > MAX_SECTION_NAME_LENGTH:
        return f"❌ Invalid input: Section identifier exceeds maximum length of {MAX_SECTION_NAME_LENGTH} characters."

    clean_parent_id = parent_id.strip() if isinstance(parent_id, str) else None
    if clean_parent_id and len(clean_parent_id) > MAX_TASK_ID_LENGTH:
        return f"❌ Invalid input: Parent task ID exceeds maximum length of {MAX_TASK_ID_LENGTH} characters."

    try:
        api = _get_api_client()
        project_id = _find_project_id(api, clean_project_name) if clean_project_name else None

        section_id = None
        section_display_name = ""
        if clean_section:
            section_id, section_display_name = _resolve_section(api, clean_section, project_id=project_id)
            if not section_id:
                return f"⚠️ Belirtilen bölüm bulunamadı: '{clean_section}'."

        task_kwargs = {
            "content": clean_content,
            "description": clean_description or None,
            "project_id": project_id,
            "due_string": clean_due_string or None,
            "priority": priority,
        }
        if section_id:
            task_kwargs["section_id"] = section_id
        if clean_labels:
            task_kwargs["labels"] = clean_labels
        if clean_parent_id:
            task_kwargs["parent_id"] = clean_parent_id

        task = api.add_task(**task_kwargs)

        due_info = task.due.string if task.due and task.due.string else (clean_due_string or "Belirtilmedi")
        project_display = clean_project_name if clean_project_name else "Gelen Kutusu"
        section_display = f"\n• Bölüm: {section_display_name} (ID: {section_id})" if section_id else ""
        labels_display = f"\n• Etiketler: {', '.join(['@' + l for l in task.labels])}" if getattr(task, "labels", None) else ""

        return (
            f"✅ Görev başarıyla oluşturuldu!\n"
            f"• ID: {task.id}\n"
            f"• Başlık: {task.content}\n"
            f"• Proje: {project_display}"
            f"{section_display}\n"
            f"• Öncelik: p{task.priority}\n"
            f"• Tarih / Tekrar: {due_info}"
            f"{labels_display}\n"
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
            description="Todoist filter query (e.g. 'today', 'tomorrow', 'overdue', 'p1', 'all', '@work').",
        ),
    ] = "today",
) -> str:
    """Lists open tasks in Todoist matching the specified filter query.

    Args:
        filter_query: Todoist filter query (e.g. 'today', 'p1', 'overdue', '@work', max 500 chars).
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
            labels_str = f" [{' '.join(['@' + l for l in task.labels])}]" if getattr(task, "labels", None) else ""
            lines.append(f"{idx}. [{task.id}] {task.content}{labels_str}")
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
def reopen_task(
    task_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_TASK_ID_LENGTH,
            description="The Todoist Task ID to reopen/uncomplete (required).",
        ),
    ],
) -> str:
    """Reopens an existing completed Todoist task (makes it active again).

    Args:
        task_id: The ID of the completed Todoist task to reopen.
    """
    clean_task_id = str(task_id).strip() if task_id is not None else ""
    if not clean_task_id:
        return "❌ Invalid input: Task ID cannot be empty or whitespace."
    if len(clean_task_id) > MAX_TASK_ID_LENGTH:
        return f"❌ Invalid input: Task ID exceeds maximum length of {MAX_TASK_ID_LENGTH} characters."

    try:
        api = _get_api_client()
        success = api.uncomplete_task(task_id=clean_task_id)
        if success:
            return f"🔄 Görev başarıyla yeniden açıldı (ID: {clean_task_id})."
        else:
            return f"⚠️ Görev yeniden açılamadı veya zaten açık olabilir (ID: {clean_task_id})."
    except Exception as e:
        logger.error(
            "Failed to reopen task in Todoist (task_id=%s, error_type=%s)",
            clean_task_id,
            type(e).__name__,
            exc_info=False,
        )
        return f"❌ Failed to reopen task in Todoist (ID: {clean_task_id}). Check server logs for details."


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
    labels: Annotated[
        Optional[list[str]],
        Field(
            default=None,
            description="New list of label names for the task (replaces existing labels, optional).",
        ),
    ] = None,
    section_name_or_id: Annotated[
        Optional[str],
        Field(
            default=None,
            max_length=MAX_SECTION_NAME_LENGTH,
            description="Target section name or ID to move the task into (optional).",
        ),
    ] = None,
) -> str:
    """Updates an existing Todoist task's title, description, due date, priority, labels, or moves it to another project/section.

    Args:
        task_id: The ID of the Todoist task to update (required).
        content: New title/content for the task.
        description: New description or notes for the task.
        project_name: Name of target project to move task into.
        due_string: New natural language due date or schedule.
        priority: Priority integer between 1 (Normal) and 4 (Urgent).
        labels: New list of label names for the task.
        section_name_or_id: Target section name or ID to move task into.
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

    clean_labels = None
    if labels is not None:
        if isinstance(labels, list):
            clean_labels = [str(l).strip().lstrip("@") for l in labels if str(l).strip()]
        else:
            return "❌ Invalid input: Labels must be a list of strings."

    clean_section = section_name_or_id.strip() if isinstance(section_name_or_id, str) else None
    if clean_section is not None and len(clean_section) > MAX_SECTION_NAME_LENGTH:
        return f"❌ Invalid input: Section identifier exceeds maximum length of {MAX_SECTION_NAME_LENGTH} characters."

    if (
        clean_content is None
        and clean_description is None
        and clean_project_name is None
        and clean_due_string is None
        and priority is None
        and clean_labels is None
        and clean_section is None
    ):
        return "⚠️ Güncellenecek hiçbir alan belirtilmedi. Lütfen en az bir parametre (content, description, project_name, due_string, priority, labels, section_name_or_id) girin."

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
        if clean_labels is not None:
            update_kwargs["labels"] = clean_labels
            updated_fields.append(f"Etiketler: {', '.join(['@' + l for l in clean_labels]) if clean_labels else 'Temizlendi'}")

        if update_kwargs:
            api.update_task(task_id=clean_task_id, **update_kwargs)

        # 2. Move task to target project / section if requested
        target_project_id = None
        if clean_project_name is not None:
            target_project_id = _find_project_id(api, clean_project_name)
            if not target_project_id:
                return f"⚠️ Görev güncellendi fakat hedef proje bulunamadı: '{clean_project_name}'."

        target_section_id = None
        if clean_section is not None:
            target_section_id, sec_name = _resolve_section(api, clean_section, project_id=target_project_id)
            if not target_section_id:
                return f"⚠️ Görev güncellendi fakat hedef bölüm bulunamadı: '{clean_section}'."

        if target_project_id is not None or target_section_id is not None:
            move_kwargs = {}
            if target_project_id is not None:
                move_kwargs["project_id"] = target_project_id
                updated_fields.append(f"Hedef Proje: '{clean_project_name}' (ID: {target_project_id})")
            if target_section_id is not None:
                move_kwargs["section_id"] = target_section_id
                updated_fields.append(f"Hedef Bölüm: '{sec_name}' (ID: {target_section_id})")

            api.move_task(task_id=clean_task_id, **move_kwargs)

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
    """Lists all user projects in Todoist with their hierarchy (nested/subprojects), names, IDs, and details."""
    try:
        api = _get_api_client()
        projects = _get_all_projects(api)

        if not projects:
            return "ℹ️ Todoist hesabınızda herhangi bir proje bulunamadı."

        children_map: dict[Optional[str], list] = {}
        all_ids = {str(getattr(p, "id", "")) for p in projects}

        for project in projects:
            parent_id = str(project.parent_id) if getattr(project, "parent_id", None) else None
            if parent_id not in all_ids:
                parent_id = None
            children_map.setdefault(parent_id, []).append(project)

        lines = [f"📁 Mevcut Projeler (Toplam: {len(projects)}):", ""]

        def format_project_tree(parent_id: Optional[str], depth: int = 0, counter: list[int] = None):
            if counter is None:
                counter = [1]
            for project in children_map.get(parent_id, []):
                is_inbox = " [Gelen Kutusu]" if getattr(project, "is_inbox_project", False) else ""
                is_fav = " ⭐" if getattr(project, "is_favorite", False) else ""
                color_info = f", Renk: {project.color}" if getattr(project, "color", None) else ""
                
                if depth == 0:
                    prefix = f"{counter[0]}. "
                    counter[0] += 1
                else:
                    prefix = "   " * depth + "└── "

                lines.append(f"{prefix}[{project.id}] {project.name}{is_inbox}{is_fav}{color_info}")
                if getattr(project, "url", None):
                    url_indent = "   " * (depth + 1)
                    lines.append(f"{url_indent}• URL: {project.url}")

                format_project_tree(str(project.id), depth + 1, counter)

        format_project_tree(None, depth=0)

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
    parent_project_name_or_id: Annotated[
        Optional[str],
        Field(
            default=None,
            max_length=MAX_PROJECT_NAME_LENGTH,
            description="Parent project name or ID to create this project as a nested subproject (optional).",
        ),
    ] = None,
    color: Annotated[
        Optional[str],
        Field(
            default=None,
            max_length=MAX_COLOR_LENGTH,
            description="Color name for the project icon (e.g. 'berry_red', 'charcoal', 'teal', optional).",
        ),
    ] = None,
) -> str:
    """Creates a new project or subproject in Todoist.

    Args:
        name: Name of the project (must not be empty, max 120 chars).
        parent_project_name_or_id: Optional parent project name or ID to create as a nested subproject.
        color: Optional color name (e.g. 'berry_red', 'sky_blue', 'mint_green').
    """
    clean_name = name.strip() if isinstance(name, str) else ""
    if not clean_name:
        return "❌ Invalid input: Project name cannot be empty or whitespace."
    if len(clean_name) > MAX_PROJECT_NAME_LENGTH:
        return f"❌ Invalid input: Project name exceeds maximum length of {MAX_PROJECT_NAME_LENGTH} characters."

    clean_parent = parent_project_name_or_id.strip() if isinstance(parent_project_name_or_id, str) else None
    if clean_parent and len(clean_parent) > MAX_PROJECT_NAME_LENGTH:
        return f"❌ Invalid input: Parent project identifier exceeds maximum length of {MAX_PROJECT_NAME_LENGTH} characters."

    clean_color = color.strip().lower() if isinstance(color, str) else None
    if clean_color and len(clean_color) > MAX_COLOR_LENGTH:
        return f"❌ Invalid input: Color name exceeds maximum length of {MAX_COLOR_LENGTH} characters."

    try:
        api = _get_api_client()
        kwargs = {}
        parent_display = ""

        if clean_parent:
            parent_id, parent_name = _resolve_project(api, clean_parent)
            if not parent_id:
                return f"⚠️ Belirtilen üst proje bulunamadı: '{clean_parent}'."
            kwargs["parent_id"] = parent_id
            parent_display = f"\n• Üst Proje: '{parent_name}' (ID: {parent_id})"

        if clean_color:
            kwargs["color"] = clean_color

        project = api.add_project(name=clean_name, **kwargs)

        color_str = f"\n• Renk: {project.color}" if getattr(project, "color", None) else ""
        url_str = f"\n• URL: {project.url}" if getattr(project, "url", None) else ""

        return (
            f"✅ Proje başarıyla oluşturuldu!\n"
            f"• ID: {project.id}\n"
            f"• İsim: {project.name}"
            f"{parent_display}"
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


@mcp.tool()
def list_labels() -> str:
    """Lists all user labels in Todoist with their names, IDs, and color information."""
    try:
        api = _get_api_client()
        labels = _get_all_labels(api)

        if not labels:
            return "ℹ️ Todoist hesabınızda herhangi bir etiket bulunamadı."

        lines = [f"🏷️ Mevcut Etiketler (Toplam: {len(labels)}):", ""]
        for idx, label in enumerate(labels, start=1):
            is_fav = " ⭐" if getattr(label, "is_favorite", False) else ""
            color_info = f", Renk: {label.color}" if getattr(label, "color", None) else ""
            lines.append(f"{idx}. [{label.id}] @{label.name}{is_fav}{color_info}")

        return "\n".join(lines).strip()
    except Exception as e:
        logger.error(
            "Failed to list labels from Todoist (error_type=%s)",
            type(e).__name__,
            exc_info=False,
        )
        return "❌ Failed to list labels from Todoist. Check server logs for details."


@mcp.tool()
def create_label(
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_LABEL_NAME_LENGTH,
            description="The name of the new label (required, e.g. 'work', 'focus').",
        ),
    ],
    color: Annotated[
        Optional[str],
        Field(
            default=None,
            max_length=MAX_COLOR_LENGTH,
            description="Color name for the label icon (e.g. 'berry_red', 'mint_green', 'teal', optional).",
        ),
    ] = None,
) -> str:
    """Creates a new label in Todoist.

    Args:
        name: Name of the label (must not be empty, max 60 chars).
        color: Optional color name (e.g. 'berry_red', 'sky_blue', 'mint_green').
    """
    clean_name = name.strip().lstrip("@") if isinstance(name, str) else ""
    if not clean_name:
        return "❌ Invalid input: Label name cannot be empty or whitespace."
    if len(clean_name) > MAX_LABEL_NAME_LENGTH:
        return f"❌ Invalid input: Label name exceeds maximum length of {MAX_LABEL_NAME_LENGTH} characters."

    clean_color = color.strip().lower() if isinstance(color, str) else None
    if clean_color and len(clean_color) > MAX_COLOR_LENGTH:
        return f"❌ Invalid input: Color name exceeds maximum length of {MAX_COLOR_LENGTH} characters."

    try:
        api = _get_api_client()
        kwargs = {}
        if clean_color:
            kwargs["color"] = clean_color

        label = api.add_label(name=clean_name, **kwargs)

        color_str = f"\n• Renk: {label.color}" if getattr(label, "color", None) else ""

        return (
            f"✅ Etiket başarıyla oluşturuldu!\n"
            f"• ID: {label.id}\n"
            f"• İsim: @{label.name}"
            f"{color_str}"
        )
    except Exception as e:
        logger.error(
            "Failed to create label in Todoist (name=%s, error_type=%s)",
            clean_name,
            type(e).__name__,
            exc_info=False,
        )
        return f"❌ Failed to create label '@{clean_name}' in Todoist. Check server logs for details."


@mcp.tool()
def update_label(
    label_name_or_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_LABEL_NAME_LENGTH,
            description="The Todoist Label ID or Name to update (required).",
        ),
    ],
    new_name: Annotated[
        Optional[str],
        Field(
            default=None,
            max_length=MAX_LABEL_NAME_LENGTH,
            description="New name for the label (optional).",
        ),
    ] = None,
    color: Annotated[
        Optional[str],
        Field(
            default=None,
            max_length=MAX_COLOR_LENGTH,
            description="New color name for the label (e.g. 'berry_red', 'teal', optional).",
        ),
    ] = None,
) -> str:
    """Updates an existing Todoist label's name or color.

    Args:
        label_name_or_id: Name or ID of the label to update (required).
        new_name: New name for the label.
        color: New color name for the label.
    """
    clean_identifier = str(label_name_or_id).strip().lstrip("@") if label_name_or_id is not None else ""
    if not clean_identifier:
        return "❌ Invalid input: Label identifier cannot be empty or whitespace."
    if len(clean_identifier) > MAX_LABEL_NAME_LENGTH:
        return f"❌ Invalid input: Label identifier exceeds maximum length of {MAX_LABEL_NAME_LENGTH} characters."

    clean_new_name = new_name.strip().lstrip("@") if isinstance(new_name, str) else None
    if clean_new_name is not None and len(clean_new_name) > MAX_LABEL_NAME_LENGTH:
        return f"❌ Invalid input: New label name exceeds maximum length of {MAX_LABEL_NAME_LENGTH} characters."

    clean_color = color.strip().lower() if isinstance(color, str) else None
    if clean_color and len(clean_color) > MAX_COLOR_LENGTH:
        return f"❌ Invalid input: Color name exceeds maximum length of {MAX_COLOR_LENGTH} characters."

    if clean_new_name is None and clean_color is None:
        return "⚠️ Güncellenecek hiçbir alan belirtilmedi. Lütfen new_name veya color parametresi girin."

    try:
        api = _get_api_client()
        label_id, old_name = _resolve_label(api, clean_identifier)

        if not label_id:
            return f"⚠️ Güncellenecek etiket bulunamadı: '@{clean_identifier}'."

        kwargs = {}
        updated_fields = []
        if clean_new_name is not None:
            kwargs["name"] = clean_new_name
            updated_fields.append(f"İsim: '@{clean_new_name}'")
        if clean_color is not None:
            kwargs["color"] = clean_color
            updated_fields.append(f"Renk: '{clean_color}'")

        api.update_label(label_id=label_id, **kwargs)

        changes_summary = "\n".join([f"• {field}" for field in updated_fields])
        return (
            f"✅ Etiket başarıyla güncellendi (ID: {label_id})!\n"
            f"Yapılan değişiklikler:\n"
            f"{changes_summary}"
        )
    except Exception as e:
        logger.error(
            "Failed to update label in Todoist (identifier=%s, error_type=%s)",
            clean_identifier,
            type(e).__name__,
            exc_info=False,
        )
        return f"❌ Failed to update label '@{clean_identifier}' in Todoist. Check server logs for details."


@mcp.tool()
def delete_label(
    label_name_or_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_LABEL_NAME_LENGTH,
            description="The Todoist Label ID or Name to delete (required).",
        ),
    ],
) -> str:
    """Deletes a label from Todoist by either its ID or label name.

    Args:
        label_name_or_id: The ID or name of the label to delete.
    """
    clean_identifier = str(label_name_or_id).strip().lstrip("@") if label_name_or_id is not None else ""
    if not clean_identifier:
        return "❌ Invalid input: Label identifier cannot be empty or whitespace."
    if len(clean_identifier) > MAX_LABEL_NAME_LENGTH:
        return f"❌ Invalid input: Label identifier exceeds maximum length of {MAX_LABEL_NAME_LENGTH} characters."

    try:
        api = _get_api_client()
        label_id, label_name = _resolve_label(api, clean_identifier)

        if not label_id:
            return f"⚠️ Silinecek etiket bulunamadı: '@{clean_identifier}'."

        success = api.delete_label(label_id=label_id)
        display_name = f"'@{label_name}' (ID: {label_id})" if label_name else f"ID: {label_id}"

        if success:
            return f"🗑️ Etiket başarıyla silindi: {display_name}."
        else:
            return f"⚠️ Etiket silinemedi: {display_name}."
    except Exception as e:
        logger.error(
            "Failed to delete label in Todoist (identifier=%s, error_type=%s)",
            clean_identifier,
            type(e).__name__,
            exc_info=False,
        )
        return f"❌ Failed to delete label '@{clean_identifier}' in Todoist. Check server logs for details."


@mcp.tool()
def create_section(
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_SECTION_NAME_LENGTH,
            description="The name of the new section/column (required, e.g. 'In Progress', 'Done').",
        ),
    ],
    project_name_or_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_PROJECT_NAME_LENGTH,
            description="The name or ID of the parent project where the section will be created (required).",
        ),
    ],
) -> str:
    """Creates a new section (column / Kanban list) in a Todoist project.

    Args:
        name: Name of the section (must not be empty, max 120 chars).
        project_name_or_id: Target project name or ID.
    """
    clean_name = name.strip() if isinstance(name, str) else ""
    if not clean_name:
        return "❌ Invalid input: Section name cannot be empty or whitespace."
    if len(clean_name) > MAX_SECTION_NAME_LENGTH:
        return f"❌ Invalid input: Section name exceeds maximum length of {MAX_SECTION_NAME_LENGTH} characters."

    clean_project = str(project_name_or_id).strip() if project_name_or_id is not None else ""
    if not clean_project:
        return "❌ Invalid input: Project identifier cannot be empty or whitespace."
    if len(clean_project) > MAX_PROJECT_NAME_LENGTH:
        return f"❌ Invalid input: Project identifier exceeds maximum length of {MAX_PROJECT_NAME_LENGTH} characters."

    try:
        api = _get_api_client()
        project_id, project_name = _resolve_project(api, clean_project)

        if not project_id:
            return f"⚠️ Bölüm oluşturulacak hedef proje bulunamadı: '{clean_project}'."

        section = api.add_section(name=clean_name, project_id=project_id)

        return (
            f"✅ Bölüm başarıyla oluşturuldu!\n"
            f"• ID: {section.id}\n"
            f"• İsim: {section.name}\n"
            f"• Proje: '{project_name}' (ID: {project_id})"
        )
    except Exception as e:
        logger.error(
            "Failed to create section in Todoist (name=%s, error_type=%s)",
            clean_name,
            type(e).__name__,
            exc_info=False,
        )
        return f"❌ Failed to create section '{clean_name}' in Todoist. Check server logs for details."


@mcp.tool()
def list_sections(
    project_name_or_id: Annotated[
        Optional[str],
        Field(
            default=None,
            max_length=MAX_PROJECT_NAME_LENGTH,
            description="Optional project name or ID to list sections specifically for that project.",
        ),
    ] = None,
) -> str:
    """Lists sections (Kanban columns) in Todoist for a specific project or across all projects."""
    clean_project = project_name_or_id.strip() if isinstance(project_name_or_id, str) else None
    if clean_project and len(clean_project) > MAX_PROJECT_NAME_LENGTH:
        return f"❌ Invalid input: Project identifier exceeds maximum length of {MAX_PROJECT_NAME_LENGTH} characters."

    try:
        api = _get_api_client()
        project_id = None
        project_name = None

        if clean_project:
            project_id, project_name = _resolve_project(api, clean_project)
            if not project_id:
                return f"⚠️ Belirtilen proje bulunamadı: '{clean_project}'."

        sections = _get_all_sections(api, project_id=project_id)

        if not sections:
            scope = f"'{project_name}' projesinde" if project_name else "hesabınızda"
            return f"ℹ️ Todoist {scope} herhangi bir bölüm bulunamadı."

        title_scope = f"'{project_name}' Projesi" if project_name else "Tüm Projeler"
        lines = [f"📑 Mevcut Bölümler ({title_scope}, Toplam: {len(sections)}):", ""]

        for idx, section in enumerate(sections, start=1):
            lines.append(f"{idx}. [{section.id}] {section.name} (Proje ID: {section.project_id})")

        return "\n".join(lines).strip()
    except Exception as e:
        logger.error(
            "Failed to list sections from Todoist (error_type=%s)",
            type(e).__name__,
            exc_info=False,
        )
        return "❌ Failed to list sections from Todoist. Check server logs for details."


@mcp.tool()
def delete_section(
    section_name_or_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_SECTION_NAME_LENGTH,
            description="The Todoist Section ID or Name to delete (required).",
        ),
    ],
) -> str:
    """Deletes a section from Todoist by its ID or name.

    Args:
        section_name_or_id: The ID or name of the section to delete.
    """
    clean_identifier = str(section_name_or_id).strip() if section_name_or_id is not None else ""
    if not clean_identifier:
        return "❌ Invalid input: Section identifier cannot be empty or whitespace."
    if len(clean_identifier) > MAX_SECTION_NAME_LENGTH:
        return f"❌ Invalid input: Section identifier exceeds maximum length of {MAX_SECTION_NAME_LENGTH} characters."

    try:
        api = _get_api_client()
        section_id, section_name = _resolve_section(api, clean_identifier)

        if not section_id:
            return f"⚠️ Silinecek bölüm bulunamadı: '{clean_identifier}'."

        success = api.delete_section(section_id=section_id)
        display_name = f"'{section_name}' (ID: {section_id})" if section_name else f"ID: {section_id}"

        if success:
            return f"🗑️ Bölüm başarıyla silindi: {display_name}."
        else:
            return f"⚠️ Bölüm silinemedi: {display_name}."
    except Exception as e:
        logger.error(
            "Failed to delete section in Todoist (identifier=%s, error_type=%s)",
            clean_identifier,
            type(e).__name__,
            exc_info=False,
        )
        return f"❌ Failed to delete section '{clean_identifier}' in Todoist. Check server logs for details."


@mcp.tool()
def add_comment(
    task_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_TASK_ID_LENGTH,
            description="The Todoist Task ID to attach the comment to (required).",
        ),
    ],
    content: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_COMMENT_LENGTH,
            description="The text content or markdown note of the comment (required).",
        ),
    ],
) -> str:
    """Adds a comment or note to an existing Todoist task.

    Args:
        task_id: ID of the task to attach the comment to.
        content: Comment text or markdown notes (max 4096 chars).
    """
    clean_task_id = str(task_id).strip() if task_id is not None else ""
    if not clean_task_id:
        return "❌ Invalid input: Task ID cannot be empty or whitespace."
    if len(clean_task_id) > MAX_TASK_ID_LENGTH:
        return f"❌ Invalid input: Task ID exceeds maximum length of {MAX_TASK_ID_LENGTH} characters."

    clean_content = content.strip() if isinstance(content, str) else ""
    if not clean_content:
        return "❌ Invalid input: Comment content cannot be empty or whitespace."
    if len(clean_content) > MAX_COMMENT_LENGTH:
        return f"❌ Invalid input: Comment content exceeds maximum length of {MAX_COMMENT_LENGTH} characters."

    try:
        api = _get_api_client()
        comment = api.add_comment(content=clean_content, task_id=clean_task_id)

        posted_str = f"\n• Tarih: {comment.posted_at}" if getattr(comment, "posted_at", None) else ""

        return (
            f"💬 Yorum başarıyla eklendi!\n"
            f"• Yorum ID: {comment.id}\n"
            f"• Görev ID: {clean_task_id}\n"
            f"• İçerik: {comment.content}"
            f"{posted_str}"
        )
    except Exception as e:
        logger.error(
            "Failed to add comment to task in Todoist (task_id=%s, error_type=%s)",
            clean_task_id,
            type(e).__name__,
            exc_info=False,
        )
        return f"❌ Failed to add comment to task (ID: {clean_task_id}) in Todoist. Check server logs for details."


@mcp.tool()
def get_comments(
    task_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_TASK_ID_LENGTH,
            description="The Todoist Task ID to retrieve comments for (required).",
        ),
    ],
) -> str:
    """Retrieves all comments and notes attached to a specific Todoist task.

    Args:
        task_id: The ID of the task whose comments will be retrieved.
    """
    clean_task_id = str(task_id).strip() if task_id is not None else ""
    if not clean_task_id:
        return "❌ Invalid input: Task ID cannot be empty or whitespace."
    if len(clean_task_id) > MAX_TASK_ID_LENGTH:
        return f"❌ Invalid input: Task ID exceeds maximum length of {MAX_TASK_ID_LENGTH} characters."

    try:
        api = _get_api_client()
        comments = []
        for batch in api.get_comments(task_id=clean_task_id):
            comments.extend(batch)

        if not comments:
            return f"ℹ️ Göreve ait (ID: {clean_task_id}) herhangi bir yorum veya not bulunamadı."

        lines = [f"💬 Görev Yorumları (Görev ID: {clean_task_id}, Toplam: {len(comments)}):", ""]
        for idx, comment in enumerate(comments, start=1):
            posted = f" [{comment.posted_at}]" if getattr(comment, "posted_at", None) else ""
            lines.append(f"{idx}. [{comment.id}]{posted} {comment.content}")

        return "\n".join(lines).strip()
    except Exception as e:
        logger.error(
            "Failed to retrieve comments from Todoist (task_id=%s, error_type=%s)",
            clean_task_id,
            type(e).__name__,
            exc_info=False,
        )
        return f"❌ Failed to retrieve comments for task (ID: {clean_task_id}) from Todoist. Check server logs for details."


if __name__ == "__main__":
    mcp.run()
