import pytest
from parser import TaskParseError, clean_json_text, parse_tasks_from_json
from sync_worker import parse_google_task


def test_clean_json_text_markdown_fence():
    raw = "```json\n[{\"content\": \"Test Task\"}]\n```"
    assert clean_json_text(raw) == '[{"content": "Test Task"}]'


def test_clean_json_text_generic_fence():
    raw = "```\n{\"tasks\": []}\n```"
    assert clean_json_text(raw) == '{"tasks": []}'


def test_clean_json_text_plain():
    raw = '  [{"content": "No Fences"}]  '
    assert clean_json_text(raw) == '[{"content": "No Fences"}]'


def test_parse_tasks_from_json_list():
    raw = """[
        {"content": "Task 1", "project_name": "Inbox", "priority": 3, "due_string": "today"},
        {"content": "Task 2", "priority": 1}
    ]"""
    tasks = parse_tasks_from_json(raw)
    assert len(tasks) == 2
    assert tasks[0].content == "Task 1"
    assert tasks[0].project_name == "Inbox"
    assert tasks[0].priority == 3
    assert tasks[0].due_string == "today"
    assert tasks[1].content == "Task 2"
    assert tasks[1].project_name == "Odak & Gelişim"  # Default


def test_parse_tasks_from_json_batch_dict():
    raw = '{"tasks": [{"content": "Batch Item 1", "priority": 4}]}'
    tasks = parse_tasks_from_json(raw)
    assert len(tasks) == 1
    assert tasks[0].content == "Batch Item 1"
    assert tasks[0].priority == 4


def test_parse_tasks_from_json_single_dict():
    raw = '{"content": "Single Task", "due_string": "tomorrow"}'
    tasks = parse_tasks_from_json(raw)
    assert len(tasks) == 1
    assert tasks[0].content == "Single Task"
    assert tasks[0].due_string == "tomorrow"


def test_parse_tasks_invalid_json():
    with pytest.raises(TaskParseError, match="Invalid JSON format"):
        parse_tasks_from_json("invalid json string {]")


def test_parse_tasks_validation_error_priority_out_of_bounds():
    # priority must be between 1 and 4
    with pytest.raises(TaskParseError, match="Data validation failed"):
        parse_tasks_from_json('{"content": "Bad Priority", "priority": 5}')


def test_parse_google_task_full_tags():
    title = "ESP32 Pin Şeması Çizimi #Odak & Gelişim p1 @today"
    notes = "DHT22 pinout detayları"
    payload = parse_google_task(title, notes)

    assert payload.content == "ESP32 Pin Şeması Çizimi"
    assert payload.project_name == "Odak & Gelişim"
    assert payload.priority == 4  # p1 -> 4
    assert payload.due_string == "today"
    assert payload.description == "DHT22 pinout detayları"


def test_parse_google_task_bracket_project_stripping():
    # Verify [Project Name] is completely stripped from content
    title = "[Odak & Gelişim] ESP32 Devre Çizimi p1 @tomorrow at 15:30"
    payload = parse_google_task(title)

    assert payload.content == "ESP32 Devre Çizimi"
    assert payload.project_name == "Odak & Gelişim"
    assert payload.priority == 4
    assert payload.due_string == "tomorrow at 15:30"
    assert payload.due_lang == "tr"


def test_parse_google_task_bracket_project_simple():
    title = "[İş] Haftalık Ekip Toplantısı p2"
    payload = parse_google_task(title)

    assert payload.content == "Haftalık Ekip Toplantısı"
    assert payload.project_name == "İş"
    assert payload.priority == 3


def test_parse_google_task_due_field_date_only():
    # RFC 3339 timestamp with 00:00:00 -> due_date
    payload = parse_google_task(
        title="Rapor Teslimi",
        due="2026-08-25T00:00:00.000Z",
    )
    assert payload.content == "Rapor Teslimi"
    assert payload.due_date == "2026-08-25"
    assert payload.due_datetime is None
    assert payload.due_string is None


def test_parse_google_task_due_field_datetime():
    # RFC 3339 timestamp with specific time -> due_datetime
    payload = parse_google_task(
        title="Müşteri Görüşmesi",
        due="2026-08-25T14:30:00.000Z",
    )
    assert payload.content == "Müşteri Görüşmesi"
    assert payload.due_datetime == "2026-08-25T14:30:00.000Z"
    assert payload.due_date is None


def test_parse_google_task_priority_mapping():
    # p1=4, p2=3, p3=2, p4=1
    assert parse_google_task("Görev p1").priority == 4
    assert parse_google_task("Görev p2").priority == 3
    assert parse_google_task("Görev p3").priority == 2
    assert parse_google_task("Görev p4").priority == 1


def test_parse_google_task_defaults():
    payload = parse_google_task("Yalnızca Başlık")
    assert payload.content == "Yalnızca Başlık"
    assert payload.project_name == "Odak & Gelişim"
    assert payload.priority == 1
    assert payload.due_string is None
    assert payload.due_date is None
    assert payload.due_datetime is None
    assert payload.description is None


def test_setup_cloud_credentials(tmp_path, monkeypatch):
    import os
    from sync_worker import setup_cloud_credentials

    token_file = str(tmp_path / "token_test.json")
    creds_file = str(tmp_path / "creds_test.json")

    monkeypatch.setenv("GOOGLE_TOKEN_JSON", '{"token": "test_token_123"}')
    monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", '{"installed": {"client_id": "test_client"}}')

    setup_cloud_credentials(credentials_path=creds_file, token_path=token_file)

    assert os.path.exists(token_file)
    assert os.path.exists(creds_file)

    with open(token_file, "r", encoding="utf-8") as f:
        assert f.read() == '{"token": "test_token_123"}'

    with open(creds_file, "r", encoding="utf-8") as f:
        assert f.read() == '{"installed": {"client_id": "test_client"}}'


def test_main_handler_mock(monkeypatch):
    from unittest.mock import MagicMock
    import sync_worker

    mock_run_sync = MagicMock(return_value=3)
    monkeypatch.setattr(sync_worker, "run_sync", mock_run_sync)

    result = sync_worker.main_handler()
    assert result["statusCode"] == 200
    assert result["status"] == "success"
    assert result["synced_count"] == 3

