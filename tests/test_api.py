from unittest.mock import patch
from fastapi.testclient import TestClient
from app import app
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
