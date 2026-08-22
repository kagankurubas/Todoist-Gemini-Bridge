import json
import logging
import re
from typing import Any, List
from pydantic import ValidationError
from models import BatchTaskPayload, TaskPayload

logger = logging.getLogger(__name__)


class TaskParseError(Exception):
    """Raised when parsing or validating task JSON fails."""
    pass


def clean_json_text(raw_text: str) -> str:
    """
    Strips markdown code fence blocks (```json ... ```) or whitespace from raw text.
    """
    text = raw_text.strip()
    # Match ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def parse_tasks_from_json(raw_text: str) -> List[TaskPayload]:
    """
    Parses a raw JSON string (from LLM chat, webhook, or automation) into a list of TaskPayload objects.

    Supported JSON formats:
      1. List of task objects: [ {"content": "Task 1"}, {"content": "Task 2"} ]
      2. Batch object with tasks key: { "tasks": [ {"content": "Task 1"} ] }
      3. Single task object: { "content": "Single Task" }

    Args:
        raw_text: Raw JSON string, optionally wrapped in markdown code blocks.

    Returns:
        List[TaskPayload]: A list of validated TaskPayload instances.

    Raises:
        TaskParseError: If JSON decoding fails or structure does not conform to TaskPayload schema.
    """
    cleaned_text = clean_json_text(raw_text)

    try:
        data: Any = json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        logger.error("Failed to decode JSON: %s\nInput text: %s", e, raw_text)
        raise TaskParseError(f"Invalid JSON format: {e}") from e

    try:
        # Case 1: Direct list of tasks
        if isinstance(data, list):
            return [TaskPayload.model_validate(item) for item in data]

        # Case 2: Object containing a "tasks" list (BatchTaskPayload)
        elif isinstance(data, dict):
            if "tasks" in data and isinstance(data["tasks"], list):
                batch = BatchTaskPayload.model_validate(data)
                return batch.tasks
            # Case 3: Single task object
            return [TaskPayload.model_validate(data)]

        else:
            raise TaskParseError(f"Expected JSON object or list, but got {type(data).__name__}")

    except ValidationError as e:
        logger.error("Validation error while parsing tasks: %s", e)
        raise TaskParseError(f"Data validation failed: {e}") from e
