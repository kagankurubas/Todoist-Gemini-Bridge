import logging
import secrets
from typing import Any, Dict, List, Optional, Union
from fastapi import Body, Depends, FastAPI, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from config import settings
from main import build_project_map, resolve_project_id
from models import BatchTaskPayload, TaskPayload
from todoist_client import (
    TodoistAPIError,
    TodoistAuthError,
    TodoistClient,
    TodoistServerError,
    TodoistValidationError,
)

# Logger configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("todoist_bridge_api")

app = FastAPI(
    title="Todoist Gemini Bridge API",
    description="REST API Bridge to parse AI/LLM task payloads and sync them with Todoist.",
    version="1.0.0",
)

# CORS Middleware
def _parse_allowed_origins(raw: str) -> List[str]:
    cleaned = (raw or "").strip()
    if cleaned == "*" or not cleaned:
        return ["*"]
    return [origin.strip() for origin in cleaned.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_allowed_origins(settings.ALLOWED_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security / Token authentication header
bridge_token_header = APIKeyHeader(
    name="X-Bridge-Token",
    auto_error=False,
    description="Pre-shared secret token for authenticating webhook requests.",
)


async def verify_bridge_token(token: Optional[str] = Security(bridge_token_header)) -> str:
    """
    Validates that the incoming request contains a valid X-Bridge-Token header using constant-time comparison.
    """
    if not token or not secrets.compare_digest(token, settings.WEBHOOK_SECRET_TOKEN):
        logger.warning("Unauthorized access attempt: Invalid or missing X-Bridge-Token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Bridge-Token authentication header.",
        )
    return token


# Exception Handlers
@app.exception_handler(TodoistAuthError)
async def auth_exception_handler(request, exc: TodoistAuthError):
    logger.error("Authentication error with Todoist (error_type=%s)", type(exc).__name__, exc_info=False)
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"error": "Unauthorized", "detail": "Todoist authentication failed. Check server configuration."},
    )


@app.exception_handler(TodoistValidationError)
async def validation_exception_handler(request, exc: TodoistValidationError):
    logger.error("Todoist validation error (error_type=%s)", type(exc).__name__, exc_info=False)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Bad Request", "detail": "Invalid data provided to Todoist API."},
    )


@app.exception_handler(TodoistServerError)
async def server_exception_handler(request, exc: TodoistServerError):
    logger.error("Todoist remote server error (error_type=%s)", type(exc).__name__, exc_info=False)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"error": "Todoist Server Error", "detail": "Todoist service is temporarily unavailable."},
    )


@app.exception_handler(TodoistAPIError)
async def api_exception_handler(request, exc: TodoistAPIError):
    logger.error("Todoist API error (error_type=%s)", type(exc).__name__, exc_info=False)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Todoist API Error", "detail": "Internal error communicating with Todoist."},
    )


@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, str]:
    """Public health check endpoint."""
    return {"status": "ok"}


@app.get("/projects", tags=["Todoist"], dependencies=[Depends(verify_bridge_token)])
async def get_projects() -> List[Dict[str, Any]]:
    """
    Fetches and returns all projects from the user's Todoist account.
    Requires X-Bridge-Token header.
    """
    try:
        client = TodoistClient()
        return client.get_projects()
    except TodoistAPIError as e:
        logger.error("Todoist API error in get_projects (status=%s, error_type=%s)", getattr(e, "status_code", None), type(e).__name__, exc_info=False)
        raise HTTPException(
            status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error communicating with Todoist API. Check server logs for details.",
        )
    except Exception as e:
        logger.error("Unexpected error fetching projects (error_type=%s)", type(e).__name__, exc_info=False)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error. Check server logs for details.",
        )


@app.post("/tasks", tags=["Todoist"], dependencies=[Depends(verify_bridge_token)])
async def create_tasks(
    payload: Union[BatchTaskPayload, List[TaskPayload], TaskPayload] = Body(
        ...,
        description="Single task object, list of tasks, or a batch object containing a 'tasks' list.",
    )
) -> Dict[str, Any]:
    """
    Creates one or more tasks in Todoist, automatically resolving target project names.
    Requires X-Bridge-Token header.
    """
    # Normalize input into a List[TaskPayload]
    tasks_to_create: List[TaskPayload] = []
    if isinstance(payload, BatchTaskPayload):
        tasks_to_create = payload.tasks
    elif isinstance(payload, list):
        tasks_to_create = payload
    elif isinstance(payload, TaskPayload):
        tasks_to_create = [payload]

    if not tasks_to_create:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tasks provided in payload.",
        )

    if len(tasks_to_create) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch size exceeds maximum limit of 50 tasks (received {len(tasks_to_create)}).",
        )

    try:
        client = TodoistClient()
        project_map = build_project_map(client)
    except Exception as e:
        logger.error("Failed to connect to Todoist or fetch project map (error_type=%s)", type(e).__name__, exc_info=False)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error. Check server logs for details.",
        )

    successful_tasks = []
    failed_tasks = []

    for task in tasks_to_create:
        target_project_id = resolve_project_id(task.project_name, project_map)
        try:
            created = client.create_task(
                content=task.content,
                project_id=target_project_id,
                due_string=task.due_string,
                priority=task.priority,
                description=task.description or "",
            )
            task_id = created.get("id", "N/A")
            task_url = created.get("url") or f"https://app.todoist.com/app/task/{task_id}"

            successful_tasks.append({
                "id": task_id,
                "content": task.content,
                "project_name": task.project_name if target_project_id else "Inbox",
                "project_id": target_project_id,
                "due_string": task.due_string,
                "priority": task.priority,
                "url": task_url,
            })
        except Exception as e:
            logger.error("Error creating task '%s' (error_type=%s)", task.content, type(e).__name__, exc_info=False)
            failed_tasks.append({
                "content": task.content,
                "project_name": task.project_name,
                "error": "Failed to create task in Todoist. Check server logs for details.",
            })

    return {
        "success": len(failed_tasks) == 0,
        "total": len(tasks_to_create),
        "created_count": len(successful_tasks),
        "failed_count": len(failed_tasks),
        "created_tasks": successful_tasks,
        "failed_tasks": failed_tasks,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000)
