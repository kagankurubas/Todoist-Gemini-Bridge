import logging
from typing import Any, Dict, List, Optional
import requests
from config import settings

# Setup module logger
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
            "Todoist API Error [%s]: %s - Response: %s",
            status_code,
            response.reason,
            error_detail,
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
            logger.error("Network error while fetching projects: %s", e)
            raise TodoistAPIError(f"Network error while connecting to Todoist API: {e}") from e

    def create_task(
        self,
        content: str,
        project_id: Optional[str] = None,
        due_string: Optional[str] = None,
        priority: int = 1,
        description: str = "",
    ) -> Dict[str, Any]:
        """
        Creates a new task in Todoist.

        Args:
            content: The text content/title of the task.
            project_id: Optional ID of the project to place the task into.
            due_string: Optional natural language due date string (e.g. 'tomorrow at 12:00', 'every Monday').
            priority: Task priority from 1 (normal) to 4 (urgent).
            description: Optional detailed description for the task.

        Returns:
            Dict[str, Any]: The created task object.
        """
        url = f"{self.BASE_URL}/tasks"
        payload: Dict[str, Any] = {
            "content": content,
            "priority": priority,
        }

        if project_id:
            payload["project_id"] = project_id
        if due_string:
            payload["due_string"] = due_string
        if description:
            payload["description"] = description

        logger.debug("Creating task at %s with payload: %s", url, payload)

        try:
            response = self.session.post(url, json=payload, timeout=self.timeout)
            return self._handle_response(response)
        except requests.RequestException as e:
            logger.error("Network error while creating task: %s", e)
            raise TodoistAPIError(f"Network error while connecting to Todoist API: {e}") from e


if __name__ == "__main__":
    import sys
    # Set standard output to utf-8 if supported
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    logging.basicConfig(level=logging.INFO)
    client = TodoistClient()
    print("--- Todoist Projects ---")
    projects = client.get_projects()
    for p in projects:
        print(f"ID: {p.get('id')} | Name: {p.get('name')}")


