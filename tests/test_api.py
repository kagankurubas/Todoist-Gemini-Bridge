from unittest.mock import patch
from fastapi.testclient import TestClient
from app import _parse_allowed_origins, app
from config import settings

client = TestClient(app)


def test_health_check_public():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_projects_unauthorized():
    response = client.get("/projects")
    assert response.status_code == 401
    assert "Invalid or missing X-Bridge-Token" in response.json()["detail"]


@patch("app.TodoistClient")
def test_projects_authorized(mock_todoist_class):
    mock_instance = mock_todoist_class.return_value
    mock_instance.get_projects.return_value = [
        {"id": "p1", "name": "Inbox"},
        {"id": "p2", "name": "Odak & Gelişim"},
    ]

    headers = {"X-Bridge-Token": settings.WEBHOOK_SECRET_TOKEN}
    response = client.get("/projects", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "Inbox"


@patch("app.TodoistClient")
def test_projects_internal_error_sanitized(mock_todoist_class, caplog):
    mock_instance = mock_todoist_class.return_value
    mock_instance.get_projects.side_effect = Exception(
        "TODOIST_API_TOKEN=SUPER_SECRET_TOKEN_123 Authorization: Bearer SUPER_SECRET_TOKEN_123"
    )

    headers = {"X-Bridge-Token": settings.WEBHOOK_SECRET_TOKEN}
    with caplog.at_level("INFO"):
        response = client.get("/projects", headers=headers)

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error. Check server logs for details."
    assert "SUPER_SECRET_TOKEN_123" not in response.text
    assert "SUPER_SECRET_TOKEN_123" not in caplog.text


def test_create_tasks_unauthorized():
    payload = [{"content": "Test Task"}]
    response = client.post("/tasks", json=payload)
    assert response.status_code == 401


@patch("app.TodoistClient")
def test_create_tasks_single_payload(mock_todoist_class):
    mock_instance = mock_todoist_class.return_value
    mock_instance.get_projects.return_value = [{"id": "proj_123", "name": "Odak & Gelişim"}]
    mock_instance.create_task.return_value = {
        "id": "task_999",
        "content": "Single Task Test",
        "url": "https://app.todoist.com/app/task/task_999",
    }

    headers = {"X-Bridge-Token": settings.WEBHOOK_SECRET_TOKEN}
    payload = {
        "content": "Single Task Test",
        "project_name": "Odak & Gelişim",
        "priority": 2,
    }

    response = client.post("/tasks", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["created_count"] == 1
    assert data["created_tasks"][0]["id"] == "task_999"


@patch("app.TodoistClient")
def test_create_tasks_batch_payload(mock_todoist_class):
    mock_instance = mock_todoist_class.return_value
    mock_instance.get_projects.return_value = []
    mock_instance.create_task.side_effect = lambda **kwargs: {
        "id": f"id_{kwargs.get('content')}",
        "url": f"https://app.todoist.com/app/task/id_{kwargs.get('content')}",
    }

    headers = {"X-Bridge-Token": settings.WEBHOOK_SECRET_TOKEN}
    payload = {
        "tasks": [
            {"content": "Task A", "priority": 1},
            {"content": "Task B", "priority": 3},
        ]
    }

    response = client.post("/tasks", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["total"] == 2
    assert data["created_count"] == 2


def test_create_tasks_batch_limit_exceeded_dict():
    headers = {"X-Bridge-Token": settings.WEBHOOK_SECRET_TOKEN}
    # 51 tasks in {"tasks": [...]}
    payload = {"tasks": [{"content": f"Task {i}"} for i in range(51)]}
    response = client.post("/tasks", json=payload, headers=headers)
    assert response.status_code in [400, 422]


def test_create_tasks_batch_limit_exceeded_raw_list():
    headers = {"X-Bridge-Token": settings.WEBHOOK_SECRET_TOKEN}
    # 51 tasks in raw list [{...}, ...]
    payload = [{"content": f"Task {i}"} for i in range(51)]
    response = client.post("/tasks", json=payload, headers=headers)
    assert response.status_code == 400
    assert "Batch size exceeds maximum limit of 50 tasks" in response.json()["detail"]


def test_cors_origins_parsing():
    assert _parse_allowed_origins("*") == ["*"]
    assert _parse_allowed_origins("") == ["*"]
    assert _parse_allowed_origins("   ") == ["*"]
    assert _parse_allowed_origins("http://localhost:3000, http://127.0.0.1:3000") == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
