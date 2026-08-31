"""
Unit and security tests for the Todoist FastMCP Server.
All tests use mocks to ensure zero network calls and deterministic results.
"""

from datetime import date
from unittest.mock import MagicMock, patch
import httpx
import pytest
from todoist_mcp import (
    MAX_COLOR_LENGTH,
    MAX_COMMENT_LENGTH,
    MAX_CONTENT_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_DUE_STRING_LENGTH,
    MAX_FILTER_QUERY_LENGTH,
    MAX_LABEL_NAME_LENGTH,
    MAX_PROJECT_NAME_LENGTH,
    MAX_SECTION_NAME_LENGTH,
    MAX_TASK_ID_LENGTH,
    _find_project_id,
    _resolve_label,
    _resolve_project,
    _resolve_section,
    add_comment,
    complete_task,
    create_label,
    create_project,
    create_section,
    create_task,
    delete_label,
    delete_project,
    delete_section,
    delete_task,
    get_comments,
    get_project,
    get_task,
    list_labels,
    list_projects,
    list_sections,
    list_tasks,
    reopen_task,
    update_label,
    update_project,
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
        is_favorite: bool = False,
        view_style: str = None,
    ):
        self.id = project_id
        self.name = name
        self.is_inbox_project = is_inbox
        self.color = color
        self.url = url or f"https://app.todoist.com/app/project/{project_id}"
        self.parent_id = parent_id
        self.is_favorite = is_favorite
        self.view_style = view_style


class MockLabel:
    """Mock Todoist label object."""

    def __init__(self, label_id: str, name: str, color: str = None, is_favorite: bool = False):
        self.id = label_id
        self.name = name
        self.color = color
        self.is_favorite = is_favorite


class MockSection:
    """Mock Todoist section object."""

    def __init__(self, section_id: str, name: str, project_id: str = "proj_default", order: int = 1):
        self.id = section_id
        self.name = name
        self.project_id = project_id
        self.order = order


class MockComment:
    """Mock Todoist comment object."""

    def __init__(self, comment_id: str, content: str, task_id: str = "task_default", posted_at: str = "2026-08-24T12:00:00Z"):
        self.id = comment_id
        self.content = content
        self.task_id = task_id
        self.posted_at = posted_at


def _make_http_status_error(status_code: int, text: str = "") -> httpx.HTTPStatusError:
    """Builds a real httpx.HTTPStatusError with a `.response` carrying the given status/body,
    matching what the todoist_api_python SDK raises on a non-2xx response."""
    request = httpx.Request("POST", "https://api.todoist.com/api/v1/tasks")
    response = httpx.Response(status_code, text=text, request=request)
    return httpx.HTTPStatusError(f"{status_code} error", request=request, response=response)


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
        section_id: str = None,
        project_id: str = "proj_default",
        parent_id: str = None,
    ):
        self.id = task_id
        self.content = content
        self.priority = priority
        self.project_id = project_id
        self.parent_id = parent_id
        self.due = MagicMock(string=due_string) if due_string else None
        self.description = description
        self.url = url or f"https://app.todoist.com/app/task/{task_id}"
        self.labels = labels or []
        self.section_id = section_id


# =====================================================================
# CREATE_TASK TESTS
# =====================================================================

@patch("todoist_mcp._get_api_client")
def test_create_task_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api

    mock_project = MockProject("proj_100", "Odak & Gelişim")
    mock_section = MockSection("sec_200", "Acil İşler", project_id="proj_100")
    mock_api.get_projects.return_value = [[mock_project]]
    mock_api.get_sections.return_value = [[mock_section]]
    mock_api.add_task.return_value = MockTask(
        task_id="task_001",
        content="Read 10 pages",
        priority=2,
        due_string="tomorrow at 10:00",
        labels=["kitap", "odak"],
        section_id="sec_200",
    )

    result = create_task(
        content="Read 10 pages",
        description="Daily habit",
        project_name="Odak & Gelişim",
        section_name_or_id="Acil İşler",
        due_string="tomorrow at 10:00",
        priority=2,
        labels=["@kitap", "odak"],
    )

    assert "✅ Görev başarıyla oluşturuldu!" in result
    assert "ID: task_001" in result
    assert "Başlık: Read 10 pages" in result
    assert "Proje: Odak & Gelişim" in result
    assert "Bölüm: Acil İşler (ID: sec_200)" in result
    assert "Öncelik: p2" in result
    assert "Etiketler: @kitap, @odak" in result
    mock_api.add_task.assert_called_once_with(
        content="Read 10 pages",
        description="Daily habit",
        project_id="proj_100",
        section_id="sec_200",
        due_string="tomorrow at 10:00",
        priority=2,
        labels=["kitap", "odak"],
    )


@patch("todoist_mcp._get_api_client")
def test_create_task_section_not_found(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_project = MockProject("proj_100", "İş")
    mock_api.get_projects.return_value = [[mock_project]]
    mock_api.get_sections.return_value = [[]]

    result = create_task(
        content="Task without section",
        project_name="İş",
        section_name_or_id="Olmayan Bölüm",
    )
    assert "⚠️ Belirtilen bölüm bulunamadı: 'Olmayan Bölüm'." in result


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


@patch("todoist_mcp._get_api_client")
def test_create_task_with_parent_id(mock_get_client):
    """parent_id verildiğinde SDK çağrısına dahil edilmelidir (alt görev/subtask)."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api

    mock_api.get_projects.return_value = [[]]
    mock_api.add_task.return_value = MockTask(
        task_id="task_child_001",
        content="Alt görev",
        priority=1,
    )

    result = create_task(content="Alt görev", parent_id="task_parent_999")

    assert "✅ Görev başarıyla oluşturuldu!" in result
    mock_api.add_task.assert_called_once_with(
        content="Alt görev",
        description=None,
        project_id=None,
        due_string=None,
        priority=1,
        parent_id="task_parent_999",
    )


@patch("todoist_mcp._get_api_client")
def test_create_task_without_parent_id_omitted(mock_get_client):
    """parent_id verilmediğinde SDK çağrısında hiç yer almamalıdır."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api

    mock_api.get_projects.return_value = [[]]
    mock_api.add_task.return_value = MockTask(
        task_id="task_003",
        content="Bağımsız görev",
        priority=1,
    )

    create_task(content="Bağımsız görev")

    call_kwargs = mock_api.add_task.call_args.kwargs
    assert "parent_id" not in call_kwargs


@patch("todoist_mcp._get_api_client")
def test_create_task_with_deadline_date(mock_get_client):
    """deadline_date verildiğinde bir date nesnesine çevrilip SDK çağrısına dahil edilmelidir."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api

    mock_api.get_projects.return_value = [[]]
    mock_api.add_task.return_value = MockTask(
        task_id="task_deadline_001",
        content="Son teslimli görev",
        priority=1,
    )

    result = create_task(content="Son teslimli görev", deadline_date="2026-09-01")

    assert "✅ Görev başarıyla oluşturuldu!" in result
    assert "Son Teslim Tarihi (Deadline): 2026-09-01" in result
    mock_api.add_task.assert_called_once_with(
        content="Son teslimli görev",
        description=None,
        project_id=None,
        due_string=None,
        priority=1,
        deadline_date=date(2026, 9, 1),
    )


@patch("todoist_mcp._get_api_client")
def test_create_task_without_deadline_date_omitted(mock_get_client):
    """deadline_date verilmediğinde SDK çağrısında hiç yer almamalıdır."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api

    mock_api.get_projects.return_value = [[]]
    mock_api.add_task.return_value = MockTask(
        task_id="task_004",
        content="Son teslimsiz görev",
        priority=1,
    )

    create_task(content="Son teslimsiz görev")

    call_kwargs = mock_api.add_task.call_args.kwargs
    assert "deadline_date" not in call_kwargs


def test_create_task_invalid_deadline_date_format():
    result = create_task(content="Task", deadline_date="01-09-2026")
    assert "❌ Invalid input: deadline_date must be in YYYY-MM-DD format" in result


@patch("todoist_mcp._get_api_client")
def test_create_task_due_string_and_deadline_date_together(mock_get_client):
    """due_string ve deadline_date aynı anda verildiğinde birbirini geçersiz kılmadan,
    ikisi de bağımsız alanlar olarak SDK çağrısına dahil edilmelidir."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api

    mock_api.get_projects.return_value = [[]]
    mock_api.add_task.return_value = MockTask(
        task_id="task_both_001",
        content="Hem tarihli hem son teslimli görev",
        priority=1,
        due_string="tomorrow at 10:00",
    )

    result = create_task(
        content="Hem tarihli hem son teslimli görev",
        due_string="tomorrow at 10:00",
        deadline_date="2026-09-01",
    )

    assert "✅ Görev başarıyla oluşturuldu!" in result
    assert "Tarih / Tekrar: tomorrow at 10:00" in result
    assert "Son Teslim Tarihi (Deadline): 2026-09-01" in result
    mock_api.add_task.assert_called_once_with(
        content="Hem tarihli hem son teslimli görev",
        description=None,
        project_id=None,
        due_string="tomorrow at 10:00",
        priority=1,
        deadline_date=date(2026, 9, 1),
    )


@patch("todoist_mcp._get_api_client")
def test_create_task_deadline_date_403_reports_plan_restriction(mock_get_client):
    """deadline_date verilen bir istek 403 Forbidden ile reddedilirse, Free/Beginner planında
    Deadline özelliğinin desteklenmediğini açıklayan özel bir hata mesajı dönmelidir."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api

    mock_api.get_projects.return_value = [[]]
    mock_api.add_task.side_effect = _make_http_status_error(403, text="Forbidden")

    result = create_task(content="Son teslimli görev", deadline_date="2026-09-01")

    assert result == (
        "❌ Deadline özelliği Todoist Free/Beginner planında desteklenmiyor "
        "— Pro veya Business plan gerekiyor (403 Forbidden)."
    )


@patch("todoist_mcp._get_api_client")
def test_create_task_403_without_deadline_date_uses_generic_message(mock_get_client):
    """deadline_date verilmeden gelen bir 403, plan-kısıtlaması mesajını değil genel hata
    mesajını dönmelidir (deadline dışı 403 sebepleri etkilenmemeli)."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api

    mock_api.get_projects.return_value = [[]]
    mock_api.add_task.side_effect = _make_http_status_error(403, text="Forbidden")

    result = create_task(content="Son teslimsiz görev")

    assert result == "❌ Todoist task creation failed. Check server logs for details."


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
# GET_TASK TESTS
# =====================================================================

@patch("todoist_mcp._get_api_client")
def test_get_task_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_task.return_value = MockTask(
        task_id="task_777",
        content="Sub-task example",
        priority=3,
        due_string="tomorrow at 09:00",
        description="Details here",
        labels=["work", "urgent"],
        section_id="sec_10",
        project_id="proj_20",
        parent_id="task_parent_5",
    )

    result = get_task(task_id="task_777")

    assert "📄 Görev Detayları (ID: task_777)" in result
    assert "Başlık: Sub-task example" in result
    assert "Açıklama: Details here" in result
    assert "Proje ID: proj_20" in result
    assert "Bölüm ID: sec_10" in result
    assert "Üst Görev ID (parent_id): task_parent_5" in result
    assert "Öncelik: p3" in result
    assert "Tarih / Tekrar: tomorrow at 09:00" in result
    assert "Etiketler: @work, @urgent" in result
    mock_api.get_task.assert_called_once_with(task_id="task_777")


@patch("todoist_mcp._get_api_client")
def test_get_task_without_parent_shows_top_level(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_task.return_value = MockTask(
        task_id="task_888",
        content="Standalone task",
        project_id="proj_20",
    )

    result = get_task(task_id="task_888")
    assert "Üst Görev ID (parent_id): Yok (üst seviye görev)" in result
    assert "Bölüm ID: Yok" in result
    assert "Açıklama: Yok" in result
    assert "Etiketler: Yok" in result


def test_get_task_empty_id():
    result = get_task(task_id="   ")
    assert "❌ Invalid input: Task ID cannot be empty or whitespace." in result


def test_get_task_id_too_long():
    result = get_task(task_id="x" * (MAX_TASK_ID_LENGTH + 1))
    assert f"❌ Invalid input: Task ID exceeds maximum length of {MAX_TASK_ID_LENGTH} characters." in result


@patch("todoist_mcp._get_api_client")
def test_get_task_sanitizes_exception_and_logs_cleanly(mock_get_client, caplog):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_task.side_effect = Exception(
        "TODOIST_API_TOKEN=SUPER_SECRET_TOKEN_123 failed Authorization: Bearer SUPER_SECRET_TOKEN_123"
    )

    with caplog.at_level("INFO"):
        result = get_task(task_id="task_err")

    assert result == "❌ Failed to retrieve task from Todoist (ID: task_err). Check server logs for details."
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
    mock_section = MockSection("sec_55", "Tamamlananlar", project_id="proj_99")
    mock_api.get_projects.return_value = [[mock_project]]
    mock_api.get_sections.return_value = [[mock_section]]

    result = update_task(
        task_id="task_123",
        content="Yeni Başlık",
        description="Yeni Açıklama",
        project_name="İş",
        section_name_or_id="Tamamlananlar",
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
    assert "Hedef Bölüm: 'Tamamlananlar' (ID: sec_55)" in result

    mock_api.update_task.assert_called_once_with(
        task_id="task_123",
        content="Yeni Başlık",
        description="Yeni Açıklama",
        due_string="yarın 15:00",
        priority=3,
        labels=["önemli", "proje"],
    )
    mock_api.move_task.assert_called_once_with(task_id="task_123", project_id="proj_99", section_id="sec_55")


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


def test_update_task_parent_id_too_long():
    result = update_task(task_id="task_123", parent_id="x" * (MAX_TASK_ID_LENGTH + 1))
    assert f"❌ Invalid input: Parent task ID exceeds maximum length of {MAX_TASK_ID_LENGTH} characters." in result


@patch("todoist_mcp._get_api_client")
def test_update_task_sets_parent_id(mock_get_client):
    """parent_id dolu bir string olarak verildiğinde move_task ile yeni üst görev atanmalı."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api

    result = update_task(task_id="task_child", parent_id="task_parent_1")

    assert "✅ Görev başarıyla güncellendi (ID: task_child)!" in result
    assert "Üst Görev (parent_id): 'task_parent_1'" in result
    mock_api.get_task.assert_not_called()
    mock_api.update_task.assert_not_called()
    mock_api.move_task.assert_called_once_with(task_id="task_child", parent_id="task_parent_1")


@patch("todoist_mcp._get_api_client")
def test_update_task_unparent_with_empty_string(mock_get_client):
    """parent_id="" verildiğinde, görevin mevcut projesi (api.get_task ile) çekilip
    move_task(project_id=...) ile üst seviyeye taşınmalı (Todoist API'de parent_id'yi
    null yaparak unparent etme desteklenmediği için)."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_task.return_value = MagicMock(project_id="proj_999")

    result = update_task(task_id="task_child", parent_id="")

    assert "✅ Görev başarıyla güncellendi (ID: task_child)!" in result
    assert "Üst Görev: Kaldırıldı (görev üst seviyeye taşındı)" in result
    mock_api.get_task.assert_called_once_with(task_id="task_child")
    mock_api.move_task.assert_called_once_with(task_id="task_child", project_id="proj_999")


@patch("todoist_mcp._get_api_client")
def test_update_task_unparent_with_project_name_skips_current_project_lookup(mock_get_client):
    """parent_id="" ile aynı anda project_name de verilirse, hedef proje zaten
    resolve edildiğinden api.get_task ile mevcut proje sorgusu yapılmamalı."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_project = MockProject("proj_42", "Kişisel")
    mock_api.get_projects.return_value = [[mock_project]]

    result = update_task(task_id="task_child", project_name="Kişisel", parent_id="")

    assert "Hedef Proje: 'Kişisel' (ID: proj_42)" in result
    assert "Üst Görev: Kaldırıldı (görev üst seviyeye taşındı)" in result
    mock_api.get_task.assert_not_called()
    mock_api.move_task.assert_called_once_with(task_id="task_child", project_id="proj_42")


@patch("todoist_mcp._get_api_client")
def test_update_task_with_deadline_date(mock_get_client):
    """deadline_date verildiğinde bir date nesnesine çevrilip api.update_task çağrısına dahil edilmelidir."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api

    result = update_task(task_id="task_123", deadline_date="2026-09-01")

    assert "✅ Görev başarıyla güncellendi (ID: task_123)!" in result
    assert "Son Teslim Tarihi (Deadline): '2026-09-01'" in result
    mock_api.update_task.assert_called_once_with(task_id="task_123", deadline_date=date(2026, 9, 1))


@patch("todoist_mcp._get_api_client")
def test_update_task_without_deadline_date_omitted(mock_get_client):
    """deadline_date verilmediğinde api.update_task çağrısında hiç yer almamalıdır."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api

    update_task(task_id="task_123", content="Yeni Başlık")

    call_kwargs = mock_api.update_task.call_args.kwargs
    assert "deadline_date" not in call_kwargs


def test_update_task_invalid_deadline_date_format():
    result = update_task(task_id="task_123", deadline_date="01-09-2026")
    assert "❌ Invalid input: deadline_date must be in YYYY-MM-DD format" in result


@patch("todoist_mcp._get_api_client")
def test_update_task_due_string_and_deadline_date_together(mock_get_client):
    """due_string ve deadline_date aynı anda güncellendiğinde birbirini geçersiz kılmadan,
    ikisi de bağımsız alanlar olarak tek bir api.update_task çağrısına dahil edilmelidir."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api

    result = update_task(
        task_id="task_123",
        due_string="tomorrow at 10:00",
        deadline_date="2026-09-01",
    )

    assert "✅ Görev başarıyla güncellendi (ID: task_123)!" in result
    assert "Tarih: 'tomorrow at 10:00'" in result
    assert "Son Teslim Tarihi (Deadline): '2026-09-01'" in result
    mock_api.update_task.assert_called_once_with(
        task_id="task_123",
        due_string="tomorrow at 10:00",
        deadline_date=date(2026, 9, 1),
    )


@patch("todoist_mcp._get_api_client")
def test_update_task_deadline_date_403_reports_plan_restriction(mock_get_client):
    """deadline_date güncellenirken 403 Forbidden alınırsa, Free/Beginner planında Deadline
    özelliğinin desteklenmediğini açıklayan özel bir hata mesajı dönmelidir."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.update_task.side_effect = _make_http_status_error(403, text="Forbidden")

    result = update_task(task_id="task_123", deadline_date="2026-09-01")

    assert result == (
        "❌ Deadline özelliği Todoist Free/Beginner planında desteklenmiyor "
        "— Pro veya Business plan gerekiyor (403 Forbidden)."
    )


@patch("todoist_mcp._get_api_client")
def test_update_task_403_without_deadline_date_uses_generic_message(mock_get_client):
    """deadline_date olmadan gelen bir 403, plan-kısıtlaması mesajını değil görev-kimliğini
    içeren genel hata mesajını dönmelidir (deadline dışı 403 sebepleri etkilenmemeli)."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.update_task.side_effect = _make_http_status_error(403, text="Forbidden")

    result = update_task(task_id="task_123", content="Updated Content")

    assert result == "❌ Failed to update task in Todoist (ID: task_123). Check server logs for details."


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
# GET_PROJECT TESTS
# =====================================================================

@patch("todoist_mcp._get_api_client")
def test_get_project_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_project.return_value = MockProject(
        "proj_777",
        "İş Projesi",
        color="berry_red",
        parent_id="proj_parent_1",
        is_favorite=True,
        view_style="board",
    )

    result = get_project(project_id="proj_777")

    assert "📁 Proje Detayları (ID: proj_777)" in result
    assert "İsim: İş Projesi" in result
    assert "Renk: berry_red" in result
    assert "Üst Proje ID (parent_id): proj_parent_1" in result
    assert "Favori mi: Evet" in result
    assert "Görünüm Stili: board" in result
    mock_api.get_project.assert_called_once_with(project_id="proj_777")


@patch("todoist_mcp._get_api_client")
def test_get_project_without_parent_shows_top_level(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_project.return_value = MockProject("proj_888", "Kişisel")

    result = get_project(project_id="proj_888")
    assert "Üst Proje ID (parent_id): Yok (üst seviye proje)" in result
    assert "Renk: Yok" in result
    assert "Favori mi: Hayır" in result
    assert "Görünüm Stili: Belirlenmedi" in result


def test_get_project_empty_id():
    result = get_project(project_id="   ")
    assert "❌ Invalid input: Project ID cannot be empty or whitespace." in result


def test_get_project_id_too_long():
    result = get_project(project_id="x" * (MAX_TASK_ID_LENGTH + 1))
    assert f"❌ Invalid input: Project ID exceeds maximum length of {MAX_TASK_ID_LENGTH} characters." in result


@patch("todoist_mcp._get_api_client")
def test_get_project_sanitizes_exception_and_logs_cleanly(mock_get_client, caplog):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_project.side_effect = Exception(
        "TODOIST_API_TOKEN=SUPER_SECRET_TOKEN_123 failed Authorization: Bearer SUPER_SECRET_TOKEN_123"
    )

    with caplog.at_level("INFO"):
        result = get_project(project_id="proj_err")

    assert result == "❌ Failed to retrieve project from Todoist (ID: proj_err). Check server logs for details."
    assert "SUPER_SECRET_TOKEN_123" not in result
    assert "SUPER_SECRET_TOKEN_123" not in caplog.text


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
# UPDATE_PROJECT TESTS
# =====================================================================

@patch("todoist_mcp._get_api_client")
def test_update_project_name_only(mock_get_client):
    """Sadece name verildiğinde body'de yalnızca name gönderilmeli."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_project = MockProject("proj_1", "Eski İsim")
    mock_api.get_projects.return_value = [[mock_project]]

    result = update_project(project_name_or_id="proj_1", name="Yeni İsim")

    assert "✅ Proje başarıyla güncellendi (ID: proj_1)!" in result
    assert "İsim: 'Yeni İsim'" in result
    assert "Renk:" not in result
    mock_api.update_project.assert_called_once_with(project_id="proj_1", name="Yeni İsim")


@patch("todoist_mcp._get_api_client")
def test_update_project_color_only(mock_get_client):
    """Sadece color verildiğinde body'de yalnızca color gönderilmeli."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_project = MockProject("proj_2", "Proje İsmi")
    mock_api.get_projects.return_value = [[mock_project]]

    result = update_project(project_name_or_id="Proje İsmi", color="teal")

    assert "✅ Proje başarıyla güncellendi (ID: proj_2)!" in result
    assert "Renk: 'teal'" in result
    assert "İsim:" not in result
    mock_api.update_project.assert_called_once_with(project_id="proj_2", color="teal")


@patch("todoist_mcp._get_api_client")
def test_update_project_name_and_color(mock_get_client):
    """İkisi birden verildiğinde body'de her ikisi de gönderilmeli."""
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_project = MockProject("proj_3", "Eski İsim")
    mock_api.get_projects.return_value = [[mock_project]]

    result = update_project(project_name_or_id="proj_3", name="Güncel İsim", color="mint_green")

    assert "✅ Proje başarıyla güncellendi (ID: proj_3)!" in result
    assert "İsim: 'Güncel İsim'" in result
    assert "Renk: 'mint_green'" in result
    mock_api.update_project.assert_called_once_with(project_id="proj_3", name="Güncel İsim", color="mint_green")


def test_update_project_no_fields_provided():
    """Hiçbir alan verilmeden çağrıldığında API'ye hiç gitmeden uyarı dönmeli (no-op)."""
    result = update_project(project_name_or_id="proj_4")
    assert "⚠️ Güncellenecek hiçbir alan belirtilmedi" in result


def test_update_project_empty_identifier():
    result = update_project(project_name_or_id="   ", name="Yeni İsim")
    assert "❌ Invalid input: Project identifier cannot be empty" in result


@patch("todoist_mcp._get_api_client")
def test_update_project_not_found(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_projects.return_value = [[]]

    result = update_project(project_name_or_id="Olmayan Proje", name="Yeni İsim")
    assert "⚠️ Güncellenecek proje bulunamadı: 'Olmayan Proje'." in result
    mock_api.update_project.assert_not_called()


@patch("todoist_mcp._get_api_client")
def test_update_project_sanitizes_exception(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_project = MockProject("proj_5", "Proje")
    mock_api.get_projects.return_value = [[mock_project]]
    mock_api.update_project.side_effect = Exception("TODOIST_API_TOKEN=SECRET")

    result = update_project(project_name_or_id="proj_5", name="Yeni İsim")
    assert result == "❌ Failed to update project 'proj_5' in Todoist. Check server logs for details."
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
# LABELS (LIST_LABELS, CREATE_LABEL, UPDATE_LABEL, DELETE_LABEL) TESTS
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


@patch("todoist_mcp._get_api_client")
def test_update_label_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    lbl = MockLabel("lbl_100", "eski_ad")
    mock_api.get_labels.return_value = [[lbl]]

    result = update_label(label_name_or_id="eski_ad", new_name="yeni_ad", color="charcoal")
    assert "✅ Etiket başarıyla güncellendi (ID: lbl_100)!" in result
    assert "İsim: '@yeni_ad'" in result
    assert "Renk: 'charcoal'" in result
    mock_api.update_label.assert_called_once_with(label_id="lbl_100", name="yeni_ad", color="charcoal")


@patch("todoist_mcp._get_api_client")
def test_update_label_not_found(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_labels.return_value = [[]]

    result = update_label(label_name_or_id="olmayan_etiket", new_name="yeni_ad")
    assert "⚠️ Güncellenecek etiket bulunamadı: '@olmayan_etiket'." in result


def test_update_label_no_fields():
    result = update_label(label_name_or_id="lbl_1")
    assert "⚠️ Güncellenecek hiçbir alan belirtilmedi" in result


@patch("todoist_mcp._get_api_client")
def test_delete_label_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    lbl = MockLabel("lbl_200", "silinecek")
    mock_api.get_labels.return_value = [[lbl]]
    mock_api.delete_label.return_value = True

    result = delete_label(label_name_or_id="silinecek")
    assert "🗑️ Etiket başarıyla silindi: '@silinecek' (ID: lbl_200)." in result
    mock_api.delete_label.assert_called_once_with(label_id="lbl_200")


@patch("todoist_mcp._get_api_client")
def test_delete_label_not_found(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_labels.return_value = [[]]

    result = delete_label(label_name_or_id="olmayan_etiket")
    assert "⚠️ Silinecek etiket bulunamadı: '@olmayan_etiket'." in result


# =====================================================================
# SECTIONS (CREATE_SECTION, LIST_SECTIONS, DELETE_SECTION) TESTS
# =====================================================================

@patch("todoist_mcp._get_api_client")
def test_create_section_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_proj = MockProject("proj_10", "Yazılım")
    mock_api.get_projects.return_value = [[mock_proj]]
    mock_api.add_section.return_value = MockSection("sec_101", "In Progress", project_id="proj_10")

    result = create_section(name="In Progress", project_name_or_id="Yazılım")
    assert "✅ Bölüm başarıyla oluşturuldu!" in result
    assert "ID: sec_101" in result
    assert "İsim: In Progress" in result
    assert "Proje: 'Yazılım' (ID: proj_10)" in result
    mock_api.add_section.assert_called_once_with(name="In Progress", project_id="proj_10")


@patch("todoist_mcp._get_api_client")
def test_create_section_project_not_found(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_projects.return_value = [[]]

    result = create_section(name="In Progress", project_name_or_id="Olmayan Proje")
    assert "⚠️ Bölüm oluşturulacak hedef proje bulunamadı: 'Olmayan Proje'." in result


@patch("todoist_mcp._get_api_client")
def test_list_sections_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_proj = MockProject("proj_10", "Yazılım")
    mock_api.get_projects.return_value = [[mock_proj]]
    sec1 = MockSection("sec_1", "Backlog", project_id="proj_10")
    sec2 = MockSection("sec_2", "Done", project_id="proj_10")
    mock_api.get_sections.return_value = [[sec1, sec2]]

    result = list_sections(project_name_or_id="Yazılım")
    assert "📑 Mevcut Bölümler ('Yazılım' Projesi, Toplam: 2):" in result
    assert "1. [sec_1] Backlog" in result
    assert "2. [sec_2] Done" in result


@patch("todoist_mcp._get_api_client")
def test_list_sections_empty(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_sections.return_value = [[]]

    result = list_sections()
    assert "ℹ️ Todoist hesabınızda herhangi bir bölüm bulunamadı." in result


@patch("todoist_mcp._get_api_client")
def test_delete_section_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    sec = MockSection("sec_123", "Eski Bölüm")
    mock_api.get_sections.return_value = [[sec]]
    mock_api.delete_section.return_value = True

    result = delete_section(section_name_or_id="Eski Bölüm")
    assert "🗑️ Bölüm başarıyla silindi: 'Eski Bölüm' (ID: sec_123)." in result
    mock_api.delete_section.assert_called_once_with(section_id="sec_123")


@patch("todoist_mcp._get_api_client")
def test_delete_section_not_found(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_sections.return_value = [[]]

    result = delete_section(section_name_or_id="Olmayan Bölüm")
    assert "⚠️ Silinecek bölüm bulunamadı: 'Olmayan Bölüm'." in result


# =====================================================================
# COMMENTS (ADD_COMMENT, GET_COMMENTS) TESTS
# =====================================================================

@patch("todoist_mcp._get_api_client")
def test_add_comment_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.add_comment.return_value = MockComment(
        comment_id="comm_1",
        content="Bu görev için ilk not.",
        task_id="task_99",
        posted_at="2026-08-24T15:00:00Z",
    )

    result = add_comment(task_id="task_99", content="Bu görev için ilk not.")
    assert "💬 Yorum başarıyla eklendi!" in result
    assert "Yorum ID: comm_1" in result
    assert "Görev ID: task_99" in result
    assert "İçerik: Bu görev için ilk not." in result
    mock_api.add_comment.assert_called_once_with(content="Bu görev için ilk not.", task_id="task_99")


def test_add_comment_empty_content():
    result = add_comment(task_id="task_1", content="   ")
    assert "❌ Invalid input: Comment content cannot be empty" in result


@patch("todoist_mcp._get_api_client")
def test_get_comments_success(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    c1 = MockComment("c1", "Not 1", task_id="task_1", posted_at="2026-08-24 10:00")
    c2 = MockComment("c2", "Not 2", task_id="task_1", posted_at="2026-08-24 11:00")
    mock_api.get_comments.return_value = [[c1, c2]]

    result = get_comments(task_id="task_1")
    assert "💬 Görev Yorumları (Görev ID: task_1, Toplam: 2):" in result
    assert "1. [c1] [2026-08-24 10:00] Not 1" in result
    assert "2. [c2] [2026-08-24 11:00] Not 2" in result


@patch("todoist_mcp._get_api_client")
def test_get_comments_empty(mock_get_client):
    mock_api = MagicMock()
    mock_get_client.return_value = mock_api
    mock_api.get_comments.return_value = [[]]

    result = get_comments(task_id="task_no_comm")
    assert "ℹ️ Göreve ait (ID: task_no_comm) herhangi bir yorum veya not bulunamadı." in result


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
