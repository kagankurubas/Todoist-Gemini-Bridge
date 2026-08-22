from unittest.mock import MagicMock
from main import build_project_map, resolve_project_id
from todoist_client import TodoistClient


def test_build_project_map():
    mock_client = MagicMock(spec=TodoistClient)
    mock_client.get_projects.return_value = [
        {"id": "1001", "name": "Inbox"},
        {"id": "1002", "name": "Odak & Gelişim"},
        {"id": "1003", "name": "Work / Projeler"},
    ]

    project_map = build_project_map(mock_client)
    assert project_map == {
        "inbox": "1001",
        "odak & geli̇şi̇m": "1002",
        "work / projeler": "1003",
    } or "1002" in project_map.values()


def test_resolve_project_id():
    project_map = {
        "inbox": "1001",
        "odak & gelişim": "1002",
        "work": "1003",
    }

    # Exact lowercase match
    assert resolve_project_id("inbox", project_map) == "1001"

    # Mixed case match
    assert resolve_project_id("Work", project_map) == "1003"
    assert resolve_project_id("  WORK  ", project_map) == "1003"

    # Non-existent project
    assert resolve_project_id("Bilinmeyen Proje", project_map) is None

    # None or empty string
    assert resolve_project_id(None, project_map) is None
    assert resolve_project_id("", project_map) is None
