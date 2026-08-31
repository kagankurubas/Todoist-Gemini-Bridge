"""
Unit and security regression tests for TodoistClient.
Ensures zero token/secret leakage into logs, exceptions, or batch responses.
"""

from unittest.mock import MagicMock, patch
import pytest
import requests
from models import TaskPayload
from todoist_client import (
    TodoistAPIError,
    TodoistAuthError,
    TodoistClient,
    TodoistServerError,
    TodoistValidationError,
)


@pytest.fixture
def mock_client():
    return TodoistClient(token="mock_token_abc")


def test_task_payload_privacy_in_logs(mock_client, caplog):
    """Test A: Private user content and descriptions are never logged."""
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "task_1", "url": "https://todoist.com/task/1"}

    with patch.object(mock_client.session, "post", return_value=mock_resp):
        with caplog.at_level("DEBUG"):
            res = mock_client.create_task(
                content="PRIVATE_TASK_CONTENT_987",
                description="PRIVATE_DESCRIPTION_654",
                due_string="tomorrow",
                priority=2,
            )

    assert res["id"] == "task_1"
    # Ensure private content and description are completely absent from logs
    assert "PRIVATE_TASK_CONTENT_987" not in caplog.text
    assert "PRIVATE_DESCRIPTION_654" not in caplog.text


def test_network_exception_sanitization_in_logs(mock_client, caplog):
    """Test B: Network exceptions with Authorization headers are not logged in raw form."""
    secret_leak_exception = requests.RequestException(
        "Connection failed: Authorization: Bearer SUPER_SECRET_TOKEN_123"
    )

    with patch.object(mock_client.session, "post", side_effect=secret_leak_exception):
        with caplog.at_level("INFO"):
            with pytest.raises(TodoistAPIError) as exc_info:
                mock_client.create_task(content="Any task")

    assert "SUPER_SECRET_TOKEN_123" not in caplog.text
    assert "SUPER_SECRET_TOKEN_123" not in str(exc_info.value)


def test_project_resolution_exception_sanitization_in_logs(mock_client, caplog):
    """Test C: Project retrieval failures containing sensitive tokens do not log secrets."""
    secret_leak_exception = requests.RequestException(
        "Failed fetching: TODOIST_API_TOKEN=SUPER_SECRET_TOKEN_123"
    )

    with patch.object(mock_client.session, "get", side_effect=secret_leak_exception):
        with caplog.at_level("INFO"):
            resolved = mock_client.resolve_project_name("Work")

    assert resolved is None
    assert "SUPER_SECRET_TOKEN_123" not in caplog.text


def test_batch_creation_exception_sanitization(mock_client, caplog):
    """Test D: Batch task creation failure sanitizes errors in both logs and returned dict."""
    secret_exception = Exception(
        "HTTP error with Authorization: Bearer SUPER_SECRET_TOKEN_123"
    )

    with patch.object(mock_client, "create_task", side_effect=secret_exception):
        with caplog.at_level("INFO"):
            batch_result = mock_client.create_tasks_batch(
                tasks=[{"content": "Task 1", "project_name": "Inbox"}]
            )

    assert batch_result["success"] is False
    assert batch_result["total"] == 1
    assert batch_result["created_count"] == 0
    assert batch_result["failed_count"] == 1
    assert len(batch_result["failed"]) == 1

    failed_entry = batch_result["failed"][0]
    # Check that error is generic and does not leak the exception text
    assert failed_entry["error"] == "Failed to create task in Todoist."
    assert "SUPER_SECRET_TOKEN_123" not in failed_entry["error"]
    assert "SUPER_SECRET_TOKEN_123" not in caplog.text


def test_api_error_response_body_not_logged(mock_client, caplog):
    """Test E: API error response bodies containing secrets are not logged."""
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 401
    mock_resp.reason = "Unauthorized"
    mock_resp.text = '{"error": "Invalid token SUPER_SECRET_TOKEN_123", "code": 401}'

    with patch.object(mock_client.session, "get", return_value=mock_resp):
        with caplog.at_level("INFO"):
            with pytest.raises(TodoistAuthError):
                mock_client.get_projects()

    # The log must contain the status code and reason, but NOT the response body with secrets
    assert "SUPER_SECRET_TOKEN_123" not in caplog.text


def test_get_projects_network_error_sanitization(mock_client, caplog):
    """Test network error in get_projects."""
    secret_leak_exception = requests.RequestException(
        "Connection aborted: Authorization: Bearer SUPER_SECRET_TOKEN_123"
    )

    with patch.object(mock_client.session, "get", side_effect=secret_leak_exception):
        with caplog.at_level("INFO"):
            with pytest.raises(TodoistAPIError) as exc_info:
                mock_client.get_projects()

    assert "SUPER_SECRET_TOKEN_123" not in caplog.text
    assert "SUPER_SECRET_TOKEN_123" not in str(exc_info.value)


def test_create_task_includes_parent_id_when_provided(mock_client):
    """parent_id kwarg olarak verildiğinde request body'sinde gönderilmelidir."""
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "task_child", "url": "https://todoist.com/task/task_child"}

    with patch.object(mock_client.session, "post", return_value=mock_resp) as mock_post:
        mock_client.create_task(content="Sub-task", parent_id="task_parent_1")

    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload["parent_id"] == "task_parent_1"


def test_create_task_omits_parent_id_when_not_provided(mock_client):
    """parent_id verilmediğinde request body'sinde hiç yer almamalıdır."""
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "task_1", "url": "https://todoist.com/task/task_1"}

    with patch.object(mock_client.session, "post", return_value=mock_resp) as mock_post:
        mock_client.create_task(content="Standalone task")

    sent_payload = mock_post.call_args.kwargs["json"]
    assert "parent_id" not in sent_payload


def test_create_task_from_payload_includes_parent_id(mock_client):
    """TaskPayload nesnesi üzerinden geçirilen parent_id de body'ye eklenmelidir."""
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "task_child", "url": "https://todoist.com/task/task_child"}

    payload = TaskPayload(content="Sub-task via payload", parent_id="task_parent_2")

    with patch.object(mock_client.session, "post", return_value=mock_resp) as mock_post:
        mock_client.create_task(payload)

    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload["parent_id"] == "task_parent_2"


def test_create_task_from_payload_omits_parent_id_when_none(mock_client):
    """TaskPayload'da parent_id None ise body'de hiç yer almamalıdır."""
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "task_1", "url": "https://todoist.com/task/task_1"}

    payload = TaskPayload(content="Standalone task via payload")

    with patch.object(mock_client.session, "post", return_value=mock_resp) as mock_post:
        mock_client.create_task(payload)

    sent_payload = mock_post.call_args.kwargs["json"]
    assert "parent_id" not in sent_payload


def test_get_task_calls_correct_endpoint_and_parses_response(mock_client):
    """get_task, GET /tasks/{id} endpoint'ini çağırmalı ve tüm alanları (parent_id, due,
    labels, description dahil) response'dan olduğu gibi parse edip döndürmelidir."""
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "task_555",
        "content": "Sub-task example",
        "description": "Some details",
        "project_id": "proj_1",
        "section_id": "sec_1",
        "parent_id": "task_parent_1",
        "labels": ["urgent", "work"],
        "priority": 3,
        "due": {"date": "2026-09-01", "string": "next tuesday", "is_recurring": False},
    }

    with patch.object(mock_client.session, "get", return_value=mock_resp) as mock_get:
        result = mock_client.get_task("task_555")

    called_url = mock_get.call_args.args[0]
    assert called_url == f"{mock_client.BASE_URL}/tasks/task_555"
    assert result["id"] == "task_555"
    assert result["parent_id"] == "task_parent_1"
    assert result["description"] == "Some details"
    assert result["labels"] == ["urgent", "work"]
    assert result["due"]["string"] == "next tuesday"


def test_get_task_not_found_raises_todoist_api_error(mock_client):
    """Var olmayan bir task_id için Todoist 404 döndürdüğünde uygun exception fırlatılmalı."""
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 404
    mock_resp.reason = "Not Found"
    mock_resp.text = '{"error": "Task not found"}'

    with patch.object(mock_client.session, "get", return_value=mock_resp):
        with pytest.raises(TodoistAPIError):
            mock_client.get_task("nonexistent_task")
