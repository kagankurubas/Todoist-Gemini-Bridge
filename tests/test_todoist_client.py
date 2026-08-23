"""
Unit and security regression tests for TodoistClient.
Ensures zero token/secret leakage into logs, exceptions, or batch responses.
"""

from unittest.mock import MagicMock, patch
import pytest
import requests
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
