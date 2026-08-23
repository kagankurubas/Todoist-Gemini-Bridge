import logging
from typing import Any, Dict, List, Optional, Union
import requests
from config import settings

logger = logging.getLogger(__name__)


class TodoistAPIError(Exception):
    """Base exception for Todoist API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class TodoistAuthError(TodoistAPIError):
    """Raised when authentication fails (HTTP 401)."""
    pass


class TodoistValidationError(TodoistAPIError):
    """Raised when request data is invalid (HTTP 400)."""
    pass


class TodoistServerError(TodoistAPIError):
    """Raised when Todoist server encounters an error (HTTP 500+)."""
    pass


class TodoistClient:
    """Client for interacting with the Todoist API (v1)."""

    BASE_URL = "https://api.todoist.com/api/v1"

    def __init__(self, token: Optional[str] = None, timeout: int = 10):
        self.token = token or settings.TODOIST_API_TOKEN
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        })

    def _handle_response(self, response: requests.Response) -> Any:
        """Evaluates HTTP response status codes and raises custom exceptions on errors."""
        status_code = response.status_code

        if response.ok:
            if status_code == 204 or not response.text:
                return {}
            try:
                return response.json()
            except ValueError:
                return response.text

        error_detail = response.text
        logger.error(
            "Todoist API Error [%s]: %s",
            status_code,
            response.reason,
            exc_info=False,
        )

        if status_code == 401:
            raise TodoistAuthError(
                f"Authentication failed (401 Unauthorized): Invalid or missing API token. Detail: {error_detail}",
                status_code=status_code,
                response_text=error_detail,
            )
        elif status_code == 400:
            raise TodoistValidationError(
                f"Bad request (400 Bad Request): Invalid parameters supplied. Detail: {error_detail}",
                status_code=status_code,
                response_text=error_detail,
            )
        elif 500 <= status_code < 600:
            raise TodoistServerError(
                f"Server error ({status_code}): Todoist API encountered an internal issue. Detail: {error_detail}",
                status_code=status_code,
                response_text=error_detail,
            )
        else:
            raise TodoistAPIError(
                f"API request failed with status code {status_code}: {error_detail}",
                status_code=status_code,
                response_text=error_detail,
            )

    def get_projects(self) -> List[Dict[str, Any]]:
        """
        Lists all user projects.

        Returns:
            List[Dict[str, Any]]: List of project objects from Todoist.
        """
        url = f"{self.BASE_URL}/projects"
        logger.debug("Fetching Todoist projects from %s", url)

        try:
            response = self.session.get(url, timeout=self.timeout)
            data = self._handle_response(response)
            if isinstance(data, dict) and "results" in data:
                return data["results"]
            return data
        except requests.RequestException as e:
            logger.error(
                "Network error while fetching projects (error_type=%s)",
                type(e).__name__,
                exc_info=False,
            )
            raise TodoistAPIError(f"Network error while connecting to Todoist API: {type(e).__name__}") from e

    def resolve_project_name(self, project_name: str) -> Optional[str]:
        """
        Resolves a project name to its Todoist project ID (case-insensitive).
        """
        if not project_name:
            return None
        try:
            projects = self.get_projects()
            norm = project_name.strip().lower()
            for p in projects:
                if p.get("name", "").strip().lower() == norm:
                    return str(p.get("id"))
        except Exception as e:
            logger.warning(
                "Error resolving project name '%s' (error_type=%s)",
                project_name,
                type(e).__name__,
                exc_info=False,
            )
        return None

    def create_task(
        self,
        content: Optional[Union[str, Any]] = None,
        project_id: Optional[str] = None,
        due_string: Optional[str] = None,
        due_date: Optional[str] = None,
        due_datetime: Optional[str] = None,
        due_lang: Optional[str] = "tr",
        priority: int = 1,
        description: Optional[str] = None,
        project_name: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Creates a new task in Todoist.
        Supports keyword arguments, direct parameters, and TaskPayload / dict instances.

        Args:
            content: Task title string, or a TaskPayload / dict instance.
            project_id: Optional Todoist project ID.
            due_string: Optional natural language due date/time (e.g. 'tomorrow at 15:30').
            due_date: Optional specific due date in YYYY-MM-DD format.
            due_datetime: Optional specific due datetime in RFC3339 / ISO 8601 format.
            due_lang: 2-letter language code for due_string (defaults to 'tr').
            priority: Task priority from 1 (normal) to 4 (urgent).
            description: Optional detailed description.
            project_name: Optional project name (automatically resolved if project_id is not set).

        Returns:
            Dict[str, Any]: The created task object.
        """
        # Case 1: First argument is a Pydantic model or dict object
        if content is not None and not isinstance(content, str):
            task_obj = content
            if hasattr(task_obj, "model_dump"):
                data = task_obj.model_dump(exclude_none=True)
            elif hasattr(task_obj, "dict"):
                data = task_obj.dict(exclude_none=True)
            elif isinstance(task_obj, dict):
                data = task_obj
            else:
                data = getattr(task_obj, "__dict__", {})

            task_content = data.get("content", "")
            task_project_id = data.get("project_id") or project_id
            task_project_name = data.get("project_name") or project_name
            task_due_string = data.get("due_string") or due_string
            task_due_date = data.get("due_date") or due_date
            task_due_datetime = data.get("due_datetime") or due_datetime
            task_due_lang = data.get("due_lang") or due_lang
            task_priority = data.get("priority", priority)
            task_description = data.get("description") or description or ""
        else:
            task_content = str(content or kwargs.get("content", ""))
            task_project_id = project_id or kwargs.get("project_id")
            task_project_name = project_name or kwargs.get("project_name")
            task_due_string = due_string or kwargs.get("due_string")
            task_due_date = due_date or kwargs.get("due_date")
            task_due_datetime = due_datetime or kwargs.get("due_datetime")
            task_due_lang = due_lang or kwargs.get("due_lang")
            task_priority = priority if priority is not None else kwargs.get("priority", 1)
            task_description = description or kwargs.get("description", "")

        # If project_name is supplied without project_id, attempt to resolve it
        if not task_project_id and task_project_name:
            task_project_id = self.resolve_project_name(task_project_name)

        url = f"{self.BASE_URL}/tasks"
        payload: Dict[str, Any] = {
            "content": task_content,
            "priority": task_priority,
        }

        if task_project_id:
            payload["project_id"] = task_project_id

        # Due Date / DateTime / Due String resolution
        if task_due_string:
            payload["due_string"] = task_due_string
            if task_due_lang:
                payload["due_lang"] = task_due_lang
        elif task_due_datetime:
            payload["due_datetime"] = task_due_datetime
        elif task_due_date:
            payload["due_date"] = task_due_date

        if task_description:
            payload["description"] = task_description

        logger.debug(
            "Creating Todoist task (content_len=%d, has_description=%s, has_due=%s, has_project_id=%s, priority=%d)",
            len(task_content),
            bool(task_description),
            bool(task_due_string or task_due_date or task_due_datetime),
            bool(task_project_id),
            task_priority,
        )

        try:
            response = self.session.post(url, json=payload, timeout=self.timeout)
            return self._handle_response(response)
        except requests.RequestException as e:
            logger.error(
                "Network error while creating task (error_type=%s)",
                type(e).__name__,
                exc_info=False,
            )
            raise TodoistAPIError(f"Network error while connecting to Todoist API: {type(e).__name__}") from e

    def create_tasks_batch(
        self,
        tasks: List[Any],
        project_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Batch creates multiple tasks in Todoist, automatically resolving project names.

        Args:
            tasks: List of TaskPayload objects or dictionaries.
            project_map: Optional dictionary of {lowercase_project_name: project_id}.

        Returns:
            Dict[str, Any]: Summary dictionary containing 'created' and 'failed' task lists.
        """
        if project_map is None:
            try:
                raw_projects = self.get_projects()
                project_map = {
                    p.get("name", "").strip().lower(): str(p.get("id"))
                    for p in raw_projects
                    if p.get("name")
                }
            except Exception as e:
                logger.warning(
                    "Failed to fetch project map in create_tasks_batch (error_type=%s)",
                    type(e).__name__,
                    exc_info=False,
                )
                project_map = {}

        created_tasks = []
        failed_tasks = []

        for task in tasks:
            if hasattr(task, "model_dump"):
                task_data = task.model_dump()
            elif isinstance(task, dict):
                task_data = task
            else:
                task_data = getattr(task, "__dict__", {})

            content = task_data.get("content", "")
            project_name = task_data.get("project_name")
            due_string = task_data.get("due_string")
            due_date = task_data.get("due_date")
            due_datetime = task_data.get("due_datetime")
            due_lang = task_data.get("due_lang", "tr")
            priority = task_data.get("priority", 1)
            description = task_data.get("description") or ""

            target_project_id = None
            if project_name:
                target_project_id = project_map.get(project_name.strip().lower())

            try:
                created = self.create_task(
                    content=content,
                    project_id=target_project_id,
                    due_string=due_string,
                    due_date=due_date,
                    due_datetime=due_datetime,
                    due_lang=due_lang,
                    priority=priority,
                    description=description,
                )
                task_id = created.get("id", "N/A")
                task_url = created.get("url") or f"https://app.todoist.com/app/task/{task_id}"

                created_tasks.append({
                    "original_task": task,
                    "id": task_id,
                    "content": content,
                    "project_name": project_name if target_project_id else "Inbox",
                    "project_id": target_project_id,
                    "due_string": due_string or due_date or due_datetime,
                    "priority": priority,
                    "url": task_url,
                    "raw": created,
                })
            except Exception as e:
                logger.error(
                    "Failed to create task in create_tasks_batch (content_len=%d, error_type=%s)",
                    len(content) if isinstance(content, str) else 0,
                    type(e).__name__,
                    exc_info=False,
                )
                failed_tasks.append({
                    "original_task": task,
                    "content": content,
                    "error": "Failed to create task in Todoist.",
                })

        return {
            "success": len(failed_tasks) == 0,
            "total": len(tasks),
            "created_count": len(created_tasks),
            "failed_count": len(failed_tasks),
            "created": created_tasks,
            "failed": failed_tasks,
        }


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    logging.basicConfig(level=logging.INFO)
    client = TodoistClient()
    print("--- Todoist Projects ---")
    projects = client.get_projects()
    for p in projects:
        print(f"ID: {p.get('id')} | Name: {p.get('name')}")
