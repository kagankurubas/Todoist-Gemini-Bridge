import pytest
from pydantic import ValidationError

from models import BatchTaskPayload, TaskPayload


def test_task_payload_defaults():
    task = TaskPayload(content="Buy milk")
    assert task.content == "Buy milk"
    assert task.project_name == "Odak & Gelişim"
    assert task.priority == 1
    assert task.due_lang == "tr"
    assert task.due_string is None
    assert task.due_date is None
    assert task.due_datetime is None
    assert task.description is None


def test_task_payload_empty_content_rejected():
    with pytest.raises(ValidationError):
        TaskPayload(content="")


def test_task_payload_missing_content_rejected():
    with pytest.raises(ValidationError):
        TaskPayload()


@pytest.mark.parametrize("priority", [1, 2, 3, 4])
def test_task_payload_priority_within_bounds_accepted(priority):
    task = TaskPayload(content="Task", priority=priority)
    assert task.priority == priority


@pytest.mark.parametrize("priority", [0, 5])
def test_task_payload_priority_out_of_bounds_rejected(priority):
    with pytest.raises(ValidationError):
        TaskPayload(content="Task", priority=priority)


def test_batch_task_payload_defaults_to_empty_list():
    batch = BatchTaskPayload()
    assert batch.tasks == []


def test_batch_task_payload_accepts_up_to_max_tasks():
    batch = BatchTaskPayload(tasks=[{"content": f"Task {i}"} for i in range(50)])
    assert len(batch.tasks) == 50


def test_batch_task_payload_rejects_over_max_tasks():
    with pytest.raises(ValidationError):
        BatchTaskPayload(tasks=[{"content": f"Task {i}"} for i in range(51)])
