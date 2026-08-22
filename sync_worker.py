import argparse
import logging
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional
from colorama import Fore, Style, init as colorama_init
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from models import TaskPayload
from todoist_client import TodoistClient

# Initialize colorama
colorama_init(autoreset=True)

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sync_worker")

# Google Tasks API Scope
SCOPES = ["https://www.googleapis.com/auth/tasks"]


def parse_google_task(
    title: str,
    notes: Optional[str] = None,
    due: Optional[str] = None,
) -> TaskPayload:
    """
    Parses a Google Tasks title and notes containing inline tags, time indicators,
    and metadata into a TaskPayload.

    Supported tag syntax in title/notes:
      - [Project Name] or #Project Name -> project_name (completely stripped from content)
      - p[1-4]                         -> priority (p1=4, p2=3, p3=2, p4=1)
      - @Date String                   -> due_string (e.g. @today, @tomorrow at 15:30, @Monday)
      - "Saat: HH:MM" or "HH:MM"       -> combined with due date into ISO due_datetime
      - Remaining text                 -> content (clean task title without project tags)
      - Cleaned notes                  -> description (time and date tags stripped)

    Examples:
      "[Odak & Gelişim] ESP32 Devre Şeması p1 @today"
      -> content: "ESP32 Devre Şeması", project_name: "Odak & Gelişim", priority: 4, due_string: "today"

      "[İş] Toplantı p2" (notes="Saat: 17:00\nMüşteri sunumu", due="2026-08-23T00:00:00.000Z")
      -> content: "Toplantı", project_name: "İş", priority: 3, due_datetime="2026-08-23T17:00:00", description="Müşteri sunumu"
    """
    raw_text = title.strip()

    # 1. Extract Priority: p1 (urgent/4) -> p4 (normal/1)
    priority = 1
    priority_map = {"1": 4, "2": 3, "3": 2, "4": 1}
    p_match = re.search(r"(?i)(?:^|\s)p([1-4])(?:\s|$)", raw_text)
    if p_match:
        p_val = p_match.group(1)
        priority = priority_map.get(p_val, 1)
        raw_text = raw_text[:p_match.start()] + " " + raw_text[p_match.end():]

    # 2. Extract @Date String: @today, @tomorrow at 18:00, @Friday, etc.
    due_string = None
    due_match = re.search(r"@([a-zA-Z0-9çğıöşüÇĞİÖŞÜ_:\s]+?)(?=\s+#|\s+\[|\s+p[1-4]|$)", raw_text, re.IGNORECASE)
    if due_match:
        due_string = due_match.group(1).strip()
        raw_text = raw_text[:due_match.start()] + " " + raw_text[due_match.end():]

    # 3. Extract Project Name: [Project Name] or #Project Name
    project_name = "Odak & Gelişim"

    # Check bracket format: [Project Name] e.g. [Odak & Gelişim], [İş], [Inbox]
    proj_bracket_match = re.search(r"\[([a-zA-Z0-9çğıöşüÇĞİÖŞÜ_&\s-]+?)\]", raw_text)
    if proj_bracket_match:
        project_name = proj_bracket_match.group(1).strip()
        raw_text = raw_text[:proj_bracket_match.start()] + " " + raw_text[proj_bracket_match.end():]
    else:
        # Check hashtag format: #Project Name e.g. #Odak & Gelişim, #İş
        proj_hash_match = re.search(r"#([a-zA-Z0-9çğıöşüÇĞİÖŞÜ_&\s-]+?)(?=\s+@|\s+\[|\s+p[1-4]|$)", raw_text, re.IGNORECASE)
        if proj_hash_match:
            project_name = proj_hash_match.group(1).strip()
            raw_text = raw_text[:proj_hash_match.start()] + " " + raw_text[proj_hash_match.end():]

    # 4. Clean content: trim and remove multiple spaces / leftover symbols
    content = " ".join(raw_text.split()).strip()
    if not content:
        content = "Untitled Task"

    # 5. Extract time pattern (Saat: HH:MM or HH:MM) from notes or title
    description = notes.strip() if notes else None
    extracted_time = None

    if description:
        # Priority 1: Match explicit "Saat: HH:MM" or "Saat:HH:MM"
        time_match_explicit = re.search(r"(?i)(?:^|\n|\r|\s)*Saat:\s*(\d{1,2}:\d{2})(?:\s*|$)", description)
        if time_match_explicit:
            time_raw = time_match_explicit.group(1)
            h, m = time_raw.split(":")
            if 0 <= int(h) <= 23 and 0 <= int(m) <= 59:
                extracted_time = f"{int(h):02d}:{m}"
                description = description[:time_match_explicit.start()] + "\n" + description[time_match_explicit.end():]
                description = "\n".join([line.strip() for line in description.splitlines() if line.strip()]).strip() or None
        else:
            # Priority 2: Match standalone time "17:00" or "09:30"
            time_match_standalone = re.search(r"(?i)(?:^|\n|\r|\s)*\b(\d{1,2}:\d{2})\b(?:\s*|$)", description)
            if time_match_standalone:
                time_raw = time_match_standalone.group(1)
                h, m = time_raw.split(":")
                if 0 <= int(h) <= 23 and 0 <= int(m) <= 59:
                    extracted_time = f"{int(h):02d}:{m}"
                    description = description[:time_match_standalone.start()] + "\n" + description[time_match_standalone.end():]
                    description = "\n".join([line.strip() for line in description.splitlines() if line.strip()]).strip() or None

    # Check notes for @Date if not found in title
    if not due_string and description:
        notes_due_match = re.search(r"@([a-zA-Z0-9çğıöşüÇĞİÖŞÜ_:\s]+?)(?=\s+#|\s+\[|\s+p[1-4]|$)", description, re.IGNORECASE)
        if notes_due_match:
            due_string = notes_due_match.group(1).strip()
            description = description[:notes_due_match.start()] + " " + description[notes_due_match.end():]
            description = "\n".join([line.strip() for line in description.splitlines() if line.strip()]).strip() or None

    # 6. Due date and datetime resolution
    due_date = None
    due_datetime = None

    if due:
        due_str = str(due).strip()
        date_part = due_str.split("T")[0]

        if extracted_time:
            # Combine Google Tasks date with extracted time into ISO due_datetime
            due_datetime = f"{date_part}T{extracted_time}:00"
        elif "T" in due_str:
            time_part = due_str.split("T", 1)[1]
            clean_time = time_part.rstrip("Z").replace(".000", "").replace(":00", "")
            if clean_time and clean_time != "00":
                due_datetime = due_str
            else:
                due_date = date_part
        else:
            due_date = due_str
    elif extracted_time and due_string:
        # If natural language due_string exists, append time if not already present
        if "at" not in due_string and ":" not in due_string:
            due_string = f"{due_string} at {extracted_time}"

    return TaskPayload(
        content=content,
        project_name=project_name,
        due_string=due_string,
        due_date=due_date,
        due_datetime=due_datetime,
        due_lang="tr",
        priority=priority,
        description=description,
    )


def setup_cloud_credentials(
    credentials_path: str = "credentials.json",
    token_path: str = "token.json",
) -> None:
    """
    Checks environment variables (GOOGLE_CREDENTIALS_JSON, GOOGLE_TOKEN_JSON)
    and writes them to disk if present. This allows seamless serverless execution
    in ephemeral cloud environments (Cloud Run Job, AWS Lambda, Render) without committing secrets.
    """
    token_env = os.environ.get("GOOGLE_TOKEN_JSON")
    if token_env and not os.path.exists(token_path):
        try:
            with open(token_path, "w", encoding="utf-8") as f:
                f.write(token_env.strip())
            logger.info("Successfully provisioned %s from GOOGLE_TOKEN_JSON environment variable.", token_path)
        except Exception as e:
            logger.error("Failed to write %s from environment variable: %s", token_path, e)

    creds_env = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_env and not os.path.exists(credentials_path):
        try:
            with open(credentials_path, "w", encoding="utf-8") as f:
                f.write(creds_env.strip())
            logger.info("Successfully provisioned %s from GOOGLE_CREDENTIALS_JSON environment variable.", credentials_path)
        except Exception as e:
            logger.error("Failed to write %s from environment variable: %s", credentials_path, e)


def get_google_tasks_service(
    credentials_path: str = "credentials.json",
    token_path: str = "token.json",
):
    """
    Authenticates via OAuth 2.0 and returns the Google Tasks API service.
    Generates token.json on first authorization if running interactively.
    """
    creds = None

    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception as e:
            logger.warning("Existing token.json is invalid (%s), re-authenticating...", e)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Google OAuth access token...")
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    f"Google OAuth credentials file '{credentials_path}' not found! "
                    "Please provide credentials.json or set GOOGLE_TOKEN_JSON / GOOGLE_CREDENTIALS_JSON."
                )
            logger.info("Starting local OAuth browser flow to authorize Google Tasks access...")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())
            logger.info("Saved new OAuth credentials to %s", token_path)

    return build("tasks", "v1", credentials=creds)


def print_sync_summary(summary: Dict[str, Any]) -> None:
    """
    Prints a formatted colored table of synchronized tasks.
    """
    created = summary.get("created_tasks", [])
    failed = summary.get("failed_tasks", [])
    total = summary.get("total", 0)
    synced = summary.get("synced", 0)

    print("\n" + "=" * 80)
    print(f"{Fore.LIGHTCYAN_EX}✨ GOOGLE TASKS ➔ TODOIST SYNC SUMMARY ✨{Style.RESET_ALL}".center(88))
    print("=" * 80)

    if created:
        print(f"\n{Fore.GREEN}✅ Successfully Transferred & Deleted from Google Tasks ({synced}/{total}):{Style.RESET_ALL}\n")
        header = f"{'#':<3} | {'Task Name':<30} | {'Project':<16} | {'Due Date':<15} | {'Priority':<8} | {'Todoist Link'}"
        print(Fore.LIGHTBLACK_EX + header)
        print("-" * len(header) + Style.RESET_ALL)

        for idx, item in enumerate(created, start=1):
            name_truncated = (item.get("content", "")[:27] + "...") if len(item.get("content", "")) > 30 else item.get("content", "")
            project_name = item.get("project_name") or "Inbox"
            due_string = item.get("due_string") or "-"
            priority = f"p{item.get('priority', 1)}"
            url = item.get("url", "-")

            row = (
                f"{idx:<3} | "
                f"{Fore.WHITE}{name_truncated:<30}{Style.RESET_ALL} | "
                f"{Fore.YELLOW}{project_name:<16}{Style.RESET_ALL} | "
                f"{Fore.CYAN}{due_string:<15}{Style.RESET_ALL} | "
                f"{Fore.MAGENTA}{priority:<8}{Style.RESET_ALL} | "
                f"{Fore.BLUE}{url}{Style.RESET_ALL}"
            )
            print(row)

    if failed:
        print(f"\n{Fore.RED}❌ Failed Tasks ({len(failed)}):{Style.RESET_ALL}")
        for item in failed:
            print(f"  - {Fore.YELLOW}{item.get('content')}{Style.RESET_ALL} -> Error: {item.get('error')}")

    print("\n" + "=" * 80 + "\n")


def sync_tasks(service, todoist_client: TodoistClient) -> int:
    """
    Fetches open tasks across all Google Tasks lists, converts and pushes them to Todoist,
    and removes successfully migrated tasks from Google Tasks.
    """
    try:
        tasklists_result = service.tasklists().list().execute()
        tasklists = tasklists_result.get("items", [])

        if not tasklists:
            logger.info("No Google Tasks lists found.")
            return 0

        summary = {
            "created_tasks": [],
            "failed_tasks": [],
            "total": 0,
            "synced": 0,
        }

        for tlist in tasklists:
            list_id = tlist["id"]

            results = service.tasks().list(
                tasklist=list_id,
                showCompleted=False,
                showHidden=True,
            ).execute()

            items = results.get("items", [])
            if not items:
                continue

            tasks_payloads = []
            task_id_map = []

            for item in items:
                title = item.get("title", "").strip()
                if not title:
                    continue

                notes = item.get("notes")
                due = item.get("due")
                parsed_task = parse_google_task(title=title, notes=notes, due=due)

                tasks_payloads.append(parsed_task)
                task_id_map.append(item["id"])
                summary["total"] += 1

            if not tasks_payloads:
                continue

            # Batch transfer to Todoist
            batch_result = todoist_client.create_tasks_batch(tasks_payloads)

            created_list = batch_result.get("created", [])
            failed_list = batch_result.get("failed", [])

            # Delete successfully migrated tasks from Google Tasks
            for created_item in created_list:
                summary["created_tasks"].append(created_item)
                summary["synced"] += 1

                orig = created_item.get("original_task")
                if orig in tasks_payloads:
                    idx = tasks_payloads.index(orig)
                    g_task_id = task_id_map[idx]
                    try:
                        service.tasks().delete(tasklist=list_id, task=g_task_id).execute()
                    except Exception as del_err:
                        logger.error("Failed to delete Google Task (%s): %s", g_task_id, del_err)

            for failed_item in failed_list:
                summary["failed_tasks"].append(failed_item)

        if summary["total"] > 0:
            print_sync_summary(summary)

        return summary["synced"]

    except Exception as e:
        logger.error("Error occurred during synchronization: %s", e)
        return 0


def run_sync(
    credentials_path: str = "credentials.json",
    token_path: str = "token.json",
) -> int:
    """
    Executes a one-shot synchronization run.
    """
    setup_cloud_credentials(credentials_path=credentials_path, token_path=token_path)
    service = get_google_tasks_service(credentials_path=credentials_path, token_path=token_path)
    todoist_client = TodoistClient()
    return sync_tasks(service, todoist_client)


def main_handler(event: Any = None, context: Any = None) -> Dict[str, Any]:
    """
    Serverless entry point suitable for AWS Lambda, Google Cloud Functions, or Cloud Run Jobs.
    """
    try:
        synced_count = run_sync()
        return {
            "statusCode": 200,
            "status": "success",
            "synced_count": synced_count,
        }
    except Exception as e:
        logger.error("Serverless sync handler failed: %s", e)
        return {
            "statusCode": 500,
            "status": "error",
            "error": str(e),
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Worker: Sync tasks from Google Tasks to Todoist with inline tag parsing."
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Run continuously in watcher polling mode.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Polling interval in seconds when --watch is enabled (default: 15).",
    )
    parser.add_argument(
        "--credentials",
        type=str,
        default="credentials.json",
        help="Path to Google OAuth credentials.json (default: credentials.json).",
    )
    parser.add_argument(
        "--token",
        type=str,
        default="token.json",
        help="Path to Google OAuth token.json (default: token.json).",
    )

    args = parser.parse_args()

    # Automatically provision cloud credentials if passed via environment variables
    setup_cloud_credentials(credentials_path=args.credentials, token_path=args.token)

    print(f"{Fore.CYAN}🔌 Initializing Google Tasks OAuth and Todoist Client...{Style.RESET_ALL}")

    try:
        service = get_google_tasks_service(
            credentials_path=args.credentials,
            token_path=args.token,
        )
    except FileNotFoundError as e:
        print(f"\n{Fore.RED}❌ Configuration Error: {e}{Style.RESET_ALL}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Fore.RED}❌ Authentication Error: {e}{Style.RESET_ALL}\n")
        sys.exit(1)

    todoist_client = TodoistClient()
    print(f"{Fore.GREEN}✔ Connected successfully to Google Tasks and Todoist API.{Style.RESET_ALL}")

    if args.watch:
        print(f"\n{Fore.YELLOW}👀 Watcher mode active (polling every {args.interval}s). Press Ctrl+C to stop.{Style.RESET_ALL}\n")
        try:
            while True:
                sync_tasks(service, todoist_client)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print(f"\n{Fore.CYAN}🛑 Watcher stopped by user.{Style.RESET_ALL}")
    else:
        print(f"\n{Fore.CYAN}⚡ Running one-shot synchronization...{Style.RESET_ALL}")
        synced = sync_tasks(service, todoist_client)
        print(f"{Fore.GREEN}✨ Sync complete. Total synced: {synced}{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
