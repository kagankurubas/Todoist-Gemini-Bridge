"""
Unit and security tests for the Todoist FastMCP Server.
All tests use mocks to ensure zero network calls and deterministic results.
"""

from unittest.mock import MagicMock, patch
import pytest
from todoist_mcp import (
    MAX_COLOR_LENGTH,
    MAX_CONTENT_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_DUE_STRING_LENGTH,
    MAX_FILTER_QUERY_LENGTH,
    MAX_LABEL_NAME_LENGTH,
    MAX_PROJECT_NAME_LENGTH,
    MAX_TASK_ID_LENGTH,
    _find_project_id,
    _resolve_project,
    complete_task,
    create_label,
    create_project,
    create_task,
    delete_project,
    delete_task,
    list_labels,
    list_projects,
    list_tasks,
    reopen_task,
    update_task,
)


class MockProject:
    """Mock Todoist project object."""

    def __init__(
        self,
        project_id: str,
        name: str,
        is_inbox: bool = False,
        color: str = None,
        url: str = None,
        parent_id: str = None,
    ):
        self.id = project_id
        self.name = name
        self.is_inbox_project = is_inbox
        self.color = color
        self.url = url or f"https://app.todoist.com/app/project/{project_id}"
        self.parent_id = parent_id


class MockLabel:
    """Mock Todoist label object."""

    def __init__(self, label_id: str, name: str, color: str = None, is_favorite: bool = False):
        self.id = label_id
        self.name = name
        self.color = color
        self.is_favorite = is_favorite


class MockTask:
    """Mock Todoist task object."""

    def __init__(
        self,
        task_id: str,
        content: str,
        priority: int = 1,
        due_string: str = None,
        description: str = "",
        url: str = None,
        labels: list = None,
    ):
        self.id = task_id
        self.content = content
        self.priority = priority
        self.due = MagicMock(string=due_string) if due_string else None
        self.description = description
        self.url = url or f"https://app.todoist.com/app/task/{task_id}"
        self.labels = labels or []


# =====================================================================
# CREATE_TASK TESTS
# =====================================================================

@patch("todoist_mcp._get_api_client")
def test_create_task_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api

    mock_project = MockProject("proj_100", "Odak & Gelişim")
    mock_api.get_projects.return_value = [[mock_project]]
    mock_api.add_task.return_value = MockTask(
        task_id="task_001",
        content="Read 10 pages",
        priority=2,
        due_string="tomorrow at 10:00",
        labels=["kitap", "odak"],
    )

    result = create_task(
        content="Read 10 pages",
        description="Daily habit",
        project_name="Odak & Gelişim",
        due_string="tomorrow at 10:00",
        priority=2,
        labels=["@kitap", "odak"],
    )

    assert "✅ Görev başarıyla oluşturuldu!" in result
    assert "ID: task_001" in result
    assert "Başlık: Read 10 pages" in result
    assert "Proje: Odak & Gelişim" in result
    assert "Öncelik: p2" in result
    assert "Etiketler: @kitap, @odak" in result
    mock_api.add_task.assert_called_once_with(
        content="Read 10 pages",
        description="Daily habit",
        project_id="proj_100",
        due_string="tomorrow at 10:00",
        priority=2,
        labels=["kitap", "odak"],
    )


@patch("todoist_mcp._get_api_client")
def test_create_task_inbox_default(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api

    mock_inbox = MockProject("inbox_id", "Inbox", is_inbox=True)
    mock_api.get_projects.return_value = [[mock_inbox]]
    mock_api.add_task.return_value = MockTask(
        task_id="task_002",
        content="General Task",
        priority=1,
    )

    result = create_task(content="General Task", project_name="Gelen Kutusu")
    assert "✅ Görev başarıyla oluşturuldu!" in result
    assert "ID: task_002" in result
    mock_api.add_task.assert_called_once_with(
        content="General Task",
        description=None,
        project_id="inbox_id",
        due_string=None,
        priority=1,
    )


def test_create_task_empty_content():
    result = create_task(content="   ")
    assert "❌ Invalid input: Task content cannot be empty" in result


def test_create_task_content_too_long():
    long_content = "A" * (MAX_CONTENT_LENGTH + 1)
    result = create_task(content=long_content)
    assert "❌ Invalid input: Task content exceeds maximum length" in result


def test_create_task_description_too_long():
    long_desc = "D" * (MAX_DESCRIPTION_LENGTH + 1)
    result = create_task(content="Valid title", description=long_desc)
    assert "❌ Invalid input: Task description exceeds maximum length" in result


def test_create_task_project_name_too_long():
    long_proj = "P" * (MAX_PROJECT_NAME_LENGTH + 1)
    result = create_task(content="Valid title", project_name=long_proj)
    assert "❌ Invalid input: Project name exceeds maximum length" in result


def test_create_task_due_string_too_long():
    long_due = "T" * (MAX_DUE_STRING_LENGTH + 1)
    result = create_task(content="Valid title", due_string=long_due)
    assert "❌ Invalid input: Due date string exceeds maximum length" in result


@pytest.mark.parametrize("invalid_priority", [0, 5, -1, 999, "high"])
def test_create_task_invalid_priority_rejected(invalid_priority):
    result = create_task(content="Valid task", priority=invalid_priority)
    assert "❌ Invalid input: Priority must be an integer between 1" in result


def test_create_task_invalid_labels_type():
    result = create_task(content="Valid task", labels="not_a_list")
    assert "❌ Invalid input: Labels must be a list of strings" in result


@patch("todoist_mcp._get_api_client")
def test_create_task_sanitizes_exception_and_logs_cleanly(mock_get_client, caplog):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_projects.return_value = []
    mock_api.add_task.side_effect = Exception(
        "TODOIST_API_TOKEN=SUPER_SECRET_TOKEN_123 failed Authorization: Bearer SUPER_SECRET_TOKEN_123"
    )

    with caplog.at_level("INFO"):
        result = create_task(content="Test Task")

    assert result == "❌ Todoist task creation failed. Check server logs for details."
    assert "SUPER_SECRET_TOKEN_123" not in result
    assert "Bearer" not in result
    assert "SUPER_SECRET_TOKEN_123" not in caplog.text
    assert "Bearer" not in caplog.text


# =====================================================================
# LIST_TASKS TESTS
# =====================================================================

@patch("todoist_mcp._get_api_client")
def test_list_tasks_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api

    task1 = MockTask("t1", "First task", priority=4, due_string="today", description="Note 1", labels=["acil"])
    task2 = MockTask("t2", "Second task", priority=1, due_string=None)
    mock_api.filter_tasks.return_value = [[task1, task2]]

    result = list_tasks(filter_query="today")
    assert "📋 Açık Görevler (Filtre: 'today', Toplam: 2):" in result
    assert "[t1] First task [@acil]" in result
    assert "🔴 p4 (Çok Acil)" in result
    assert "Tarih: today" in result
    assert "Açıklama: Note 1" in result
    assert "[t2] Second task" in result
    assert "⚪ p1 (Normal)" in result
    assert "Tarih: Tarih yok" in result


@patch("todoist_mcp._get_api_client")
def test_list_tasks_empty_result(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.filter_tasks.return_value = [[]]

    result = list_tasks(filter_query="overdue")
    assert "ℹ️ 'overdue' filtresine uygun açık görev bulunamadı." in result


def test_list_tasks_empty_filter():
    result = list_tasks(filter_query="   ")
    assert "❌ Invalid input: Filter query cannot be empty" in result


def test_list_tasks_filter_too_long():
    long_filter = "Q" * (MAX_FILTER_QUERY_LENGTH + 1)
    result = list_tasks(filter_query=long_filter)
    assert "❌ Invalid input: Filter query exceeds maximum length" in result


@patch("todoist_mcp._get_api_client")
def test_list_tasks_sanitizes_exception_and_logs_cleanly(mock_get_client, caplog):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.filter_tasks.side_effect = RuntimeError(
        "TODOIST_API_TOKEN=SUPER_SECRET_TOKEN_123 failed Authorization: Bearer SUPER_SECRET_TOKEN_123"
    )

    with caplog.at_level("INFO"):
        result = list_tasks(filter_query="today")

    assert result == "❌ Failed to retrieve tasks from Todoist. Check server logs for details."
    assert "SUPER_SECRET_TOKEN_123" not in result
    assert "SUPER_SECRET_TOKEN_123" not in caplog.text


# =====================================================================
# COMPLETE_TASK & REOPEN_TASK TESTS
# =====================================================================

@patch("todoist_mcp._get_api_client")
def test_complete_task_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.complete_task.return_value = True

    result = complete_task(task_id="  task_abc123  ")
    assert "✅ Görev başarıyla tamamlandı (ID: task_abc123)." in result
    mock_api.complete_task.assert_called_once_with(task_id="task_abc123")


@patch("todoist_mcp._get_api_client")
def test_complete_task_unsuccessful(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.complete_task.return_value = False

    result = complete_task(task_id="task_not_found")
    assert "⚠️ Görev tamamlanamadı veya zaten tamamlanmış olabilir (ID: task_not_found)." in result


def test_complete_task_empty_id():
    result = complete_task(task_id="   ")
    assert "❌ Invalid input: Task ID cannot be empty" in result


def test_complete_task_id_too_long():
    long_id = "X" * (MAX_TASK_ID_LENGTH + 1)
    result = complete_task(task_id=long_id)
    assert "❌ Invalid input: Task ID exceeds maximum length" in result


@patch("todoist_mcp._get_api_client")
def test_complete_task_sanitizes_exception_and_logs_cleanly(mock_get_client, caplog):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.complete_task.side_effect = Exception(
        "TODOIST_API_TOKEN=SUPER_SECRET_TOKEN_123 failed Authorization: Bearer SUPER_SECRET_TOKEN_123"
    )

    with caplog.at_level("INFO"):
        result = complete_task(task_id="task_error_123")

    assert result == "❌ Failed to complete task in Todoist (ID: task_error_123). Check server logs for details."
    assert "SUPER_SECRET_TOKEN_123" not in result
    assert "SUPER_SECRET_TOKEN_123" not in caplog.text


@patch("todoist_mcp._get_api_client")
def test_reopen_task_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.uncomplete_task.return_value = True

    result = reopen_task(task_id="  task_reopen_1  ")
    assert "🔄 Görev başarıyla yeniden açıldı (ID: task_reopen_1)." in result
    mock_api.uncomplete_task.assert_called_once_with(task_id="task_reopen_1")


@patch("todoist_mcp._get_api_client")
def test_reopen_task_unsuccessful(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.uncomplete_task.return_value = False

    result = reopen_task(task_id="task_already_active")
    assert "⚠️ Görev yeniden açılamadı veya zaten açık olabilir (ID: task_already_active)." in result


def test_reopen_task_empty_id():
    result = reopen_task(task_id="   ")
    assert "❌ Invalid input: Task ID cannot be empty" in result


@patch("todoist_mcp._get_api_client")
def test_reopen_task_sanitizes_exception(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.uncomplete_task.side_effect = Exception("TODOIST_API_TOKEN=SECRET")

    result = reopen_task(task_id="task_err")
    assert result == "❌ Failed to reopen task in Todoist (ID: task_err). Check server logs for details."
    assert "SECRET" not in result


# =====================================================================
# UPDATE_TASK TESTS
# =====================================================================

@patch("todoist_mcp._get_api_client")
def test_update_task_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_project = MockProject("proj_99", "İş")
    mock_api.get_projects.return_value = [[mock_project]]

    result = update_task(
        task_id="task_123",
        content="Yeni Başlık",
        description="Yeni Açıklama",
        project_name="İş",
        due_string="yarın 15:00",
        priority=3,
        labels=["@önemli", "proje"],
    )

    assert "✅ Görev başarıyla güncellendi (ID: task_123)!" in result
    assert "Başlık: 'Yeni Başlık'" in result
    assert "Açıklama: 'Yeni Açıklama'" in result
    assert "Tarih: 'yarın 15:00'" in result
    assert "Öncelik: p3" in result
    assert "Etiketler: @önemli, @proje" in result
    assert "Hedef Proje: 'İş' (ID: proj_99)" in result

    mock_api.update_task.assert_called_once_with(
        task_id="task_123",
        content="Yeni Başlık",
        description="Yeni Açıklama",
        due_string="yarın 15:00",
        priority=3,
        labels=["önemli", "proje"],
    )
    mock_api.move_task.assert_called_once_with(task_id="task_123", project_id="proj_99")


def test_update_task_no_fields_provided():
    result = update_task(task_id="task_123")
    assert "⚠️ Güncellenecek hiçbir alan belirtilmedi" in result


def test_update_task_invalid_priority():
    result = update_task(task_id="task_123", priority=5)
    assert "❌ Invalid input: Priority must be an integer between 1" in result


def test_update_task_invalid_labels_type():
    result = update_task(task_id="task_123", labels="not_a_list")
    assert "❌ Invalid input: Labels must be a list of strings" in result


@patch("todoist_mcp._get_api_client")
def test_update_task_sanitizes_exception(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.update_task.side_effect = Exception("TODOIST_API_TOKEN=SECRET")

    result = update_task(task_id="task_err", content="Updated Content")
    assert result == "❌ Failed to update task in Todoist (ID: task_err). Check server logs for details."
    assert "SECRET" not in result


# =====================================================================
# DELETE_TASK TESTS
# =====================================================================

@patch("todoist_mcp._get_api_client")
def test_delete_task_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.delete_task.return_value = True

    result = delete_task(task_id="task_to_del")
    assert "🗑️ Görev kalıcı olarak silindi (ID: task_to_del)." in result
    mock_api.delete_task.assert_called_once_with(task_id="task_to_del")


@patch("todoist_mcp._get_api_client")
def test_delete_task_unsuccessful(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.delete_task.return_value = False

    result = delete_task(task_id="task_missing")
    assert "⚠️ Görev silinemedi (ID: task_missing)." in result


def test_delete_task_empty_id():
    result = delete_task(task_id="   ")
    assert "❌ Invalid input: Task ID cannot be empty" in result


@patch("todoist_mcp._get_api_client")
def test_delete_task_sanitizes_exception(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.delete_task.side_effect = Exception("TODOIST_API_TOKEN=SECRET")

    result = delete_task(task_id="task_err")
    assert result == "❌ Failed to delete task in Todoist (ID: task_err). Check server logs for details."
    assert "SECRET" not in result


# =====================================================================
# CREATE_PROJECT & NESTED PROJECT TESTS
# =====================================================================

@patch("todoist_mcp._get_api_client")
def test_create_project_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.add_project.return_value = MockProject("proj_new_1", "Yeni Proje", color="berry_red")

    result = create_project(name="Yeni Proje", color="berry_red")
    assert "✅ Proje başarıyla oluşturuldu!" in result
    assert "ID: proj_new_1" in result
    assert "İsim: Yeni Proje" in result
    assert "Renk: berry_red" in result
    mock_api.add_project.assert_called_once_with(name="Yeni Proje", color="berry_red")


@patch("todoist_mcp._get_api_client")
def test_create_project_with_parent_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    parent_proj = MockProject("parent_123", "Ana Kategori")
    mock_api.get_projects.return_value = [[parent_proj]]
    mock_api.add_project.return_value = MockProject("child_456", "Alt Kategori", parent_id="parent_123")

    result = create_project(
        name="Alt Kategori",
        parent_project_name_or_id="Ana Kategori",
    )
    assert "✅ Proje başarıyla oluşturuldu!" in result
    assert "ID: child_456" in result
    assert "İsim: Alt Kategori" in result
    assert "Üst Proje: 'Ana Kategori' (ID: parent_123)" in result
    mock_api.add_project.assert_called_once_with(name="Alt Kategori", parent_id="parent_123")


@patch("todoist_mcp._get_api_client")
def test_create_project_parent_not_found(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_projects.return_value = [[]]

    result = create_project(name="Alt Kategori", parent_project_name_or_id="Olmayan Proje")
    assert "⚠️ Belirtilen üst proje bulunamadı: 'Olmayan Proje'." in result


def test_create_project_empty_name():
    result = create_project(name="   ")
    assert "❌ Invalid input: Project name cannot be empty" in result


def test_create_project_name_too_long():
    long_name = "N" * (MAX_PROJECT_NAME_LENGTH + 1)
    result = create_project(name=long_name)
    assert "❌ Invalid input: Project name exceeds maximum length" in result


def test_create_project_color_too_long():
    long_color = "C" * (MAX_COLOR_LENGTH + 1)
    result = create_project(name="Valid Project", color=long_color)
    assert "❌ Invalid input: Color name exceeds maximum length" in result


@patch("todoist_mcp._get_api_client")
def test_create_project_sanitizes_exception(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.add_project.side_effect = Exception("TODOIST_API_TOKEN=SECRET")

    result = create_project(name="ErrProj")
    assert result == "❌ Failed to create project 'ErrProj' in Todoist. Check server logs for details."
    assert "SECRET" not in result


# =====================================================================
# DELETE_PROJECT TESTS
# =====================================================================

@patch("todoist_mcp._get_api_client")
def test_delete_project_by_id_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_project = MockProject("proj_123", "Eski Proje")
    mock_api.get_projects.return_value = [[mock_project]]
    mock_api.delete_project.return_value = True

    result = delete_project(project_name_or_id="proj_123")
    assert "🗑️ Proje başarıyla silindi: 'Eski Proje' (ID: proj_123)." in result
    mock_api.delete_project.assert_called_once_with(project_id="proj_123")


@patch("todoist_mcp._get_api_client")
def test_delete_project_by_name_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_project = MockProject("proj_456", "Silinecek Proje")
    mock_api.get_projects.return_value = [[mock_project]]
    mock_api.delete_project.return_value = True

    result = delete_project(project_name_or_id="Silinecek Proje")
    assert "🗑️ Proje başarıyla silindi: 'Silinecek Proje' (ID: proj_456)." in result
    mock_api.delete_project.assert_called_once_with(project_id="proj_456")


@patch("todoist_mcp._get_api_client")
def test_delete_project_not_found(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_projects.return_value = [[]]

    result = delete_project(project_name_or_id="Nonexistent")
    assert "⚠️ Silinecek proje bulunamadı: 'Nonexistent'." in result


def test_delete_project_empty_identifier():
    result = delete_project(project_name_or_id="   ")
    assert "❌ Invalid input: Project identifier cannot be empty" in result


# =====================================================================
# LIST_PROJECTS TESTS (HIERARCHICAL)
# =====================================================================

@patch("todoist_mcp._get_api_client")
def test_list_projects_hierarchical(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    p1 = MockProject("p1", "Gelen Kutusu", is_inbox=True)
    p2 = MockProject("p2", "İş", color="berry_red")
    p3 = MockProject("p3", "Alt Görevler", parent_id="p2")
    mock_api.get_projects.return_value = [[p1, p2, p3]]

    result = list_projects()
    assert "📁 Mevcut Projeler (Toplam: 3):" in result
    assert "1. [p1] Gelen Kutusu [Gelen Kutusu]" in result
    assert "2. [p2] İş, Renk: berry_red" in result
    assert "└── [p3] Alt Görevler" in result


@patch("todoist_mcp._get_api_client")
def test_list_projects_empty(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_projects.return_value = [[]]

    result = list_projects()
    assert "ℹ️ Todoist hesabınızda herhangi bir proje bulunamadı." in result


# =====================================================================
# LABELS (LIST_LABELS & CREATE_LABEL) TESTS
# =====================================================================

@patch("todoist_mcp._get_api_client")
def test_list_labels_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    lbl1 = MockLabel("lbl_1", "önemli", color="berry_red", is_favorite=True)
    lbl2 = MockLabel("lbl_2", "iş", color="blue")
    mock_api.get_labels.return_value = [[lbl1, lbl2]]

    result = list_labels()
    assert "🏷️ Mevcut Etiketler (Toplam: 2):" in result
    assert "1. [lbl_1] @önemli ⭐, Renk: berry_red" in result
    assert "2. [lbl_2] @iş, Renk: blue" in result


@patch("todoist_mcp._get_api_client")
def test_list_labels_empty(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_labels.return_value = [[]]

    result = list_labels()
    assert "ℹ️ Todoist hesabınızda herhangi bir etiket bulunamadı." in result


@patch("todoist_mcp._get_api_client")
def test_list_labels_sanitizes_exception(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_labels.side_effect = Exception("TODOIST_API_TOKEN=SECRET")

    result = list_labels()
    assert result == "❌ Failed to list labels from Todoist. Check server logs for details."
    assert "SECRET" not in result


@patch("todoist_mcp._get_api_client")
def test_create_label_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.add_label.return_value = MockLabel("lbl_new_1", "odak", color="mint_green")

    result = create_label(name="@odak", color="mint_green")
    assert "✅ Etiket başarıyla oluşturuldu!" in result
    assert "ID: lbl_new_1" in result
    assert "İsim: @odak" in result
    assert "Renk: mint_green" in result
    mock_api.add_label.assert_called_once_with(name="odak", color="mint_green")


def test_create_label_empty_name():
    result = create_label(name="   ")
    assert "❌ Invalid input: Label name cannot be empty" in result


def test_create_label_name_too_long():
    long_name = "L" * (MAX_LABEL_NAME_LENGTH + 1)
    result = create_label(name=long_name)
    assert "❌ Invalid input: Label name exceeds maximum length" in result


@patch("todoist_mcp._get_api_client")
def test_create_label_sanitizes_exception(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.add_label.side_effect = Exception("TODOIST_API_TOKEN=SECRET")

    result = create_label(name="error_label")
    assert result == "❌ Failed to create label '@error_label' in Todoist. Check server logs for details."
    assert "SECRET" not in result


# =====================================================================
# PROJECT RESOLUTION TESTS
# =====================================================================

def test_find_project_id_exact_and_case_insensitive():
    mock_api = MagicMock()
    mock_api.get_projects.return_value = [
        [
            MockProject("p1", "Inbox", is_inbox=True),
            MockProject("p2", "Odak & Gelişim"),
            MockProject("p3", "Kişisel Projeler"),
        ]
    ]

    assert _find_project_id(mock_api, "Odak & Gelişim") == "p2"
    assert _find_project_id(mock_api, "odak & gelişim") == "p2"
    assert _find_project_id(mock_api, "KİŞİSEL PROJELER") == "p3"


def test_find_project_id_inbox_aliases():
    mock_api = MagicMock()
    mock_api.get_projects.return_value = [
        [MockProject("inbox_99", "Gelen Kutusu", is_inbox=True)]
    ]

    assert _find_project_id(mock_api, "Inbox") == "inbox_99"
    assert _find_project_id(mock_api, "gelen kutusu") == "inbox_99"
    assert _find_project_id(mock_api, "GelenKutusu") == "inbox_99"


def test_find_project_id_partial_match_fallback():
    mock_api = MagicMock()
    mock_api.get_projects.return_value = [
        [MockProject("p_sub", "Yazılım Geliştirme Çalışmaları")]
    ]

    assert _find_project_id(mock_api, "Yazılım Geliştirme") == "p_sub"


def test_find_project_id_api_failure_fallback():
    mock_api = MagicMock()
    mock_api.get_projects.side_effect = RuntimeError("Network timeout")

    assert _find_project_id(mock_api, "Nonexistent") is None
