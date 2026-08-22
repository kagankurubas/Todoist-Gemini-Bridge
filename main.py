import argparse
import logging
import sys
from typing import Dict, List, Optional
from colorama import Fore, Style, init as colorama_init
from models import TaskPayload
from parser import TaskParseError, parse_tasks_from_json
from todoist_client import TodoistAPIError, TodoistClient

# Initialize colorama for cross-platform color support
colorama_init(autoreset=True)

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bridge_main")


def build_project_map(client: TodoistClient) -> Dict[str, str]:
    """
    Fetches all projects from Todoist and builds a lookup mapping of {normalized_name: project_id}.
    """
    try:
        raw_projects = client.get_projects()
        project_map: Dict[str, str] = {}
        for p in raw_projects:
            name = p.get("name", "").strip()
            p_id = str(p.get("id"))
            if name:
                project_map[name.lower()] = p_id
        return project_map
    except Exception as e:
        logger.warning(f"Could not retrieve project list: {e}. Will create tasks in Inbox.")
        return {}


def resolve_project_id(project_name: Optional[str], project_map: Dict[str, str]) -> Optional[str]:
    """
    Resolves project name to project ID using exact or case-insensitive matching.
    """
    if not project_name:
        return None

    normalized = project_name.strip().lower()
    return project_map.get(normalized)


def process_and_create_tasks(tasks: List[TaskPayload], client: TodoistClient) -> None:
    """
    Processes a list of TaskPayloads, resolves their project IDs, creates them in Todoist,
    and prints a formatted summary table.
    """
    if not tasks:
        print(f"{Fore.YELLOW}⚠ No tasks found to process.{Style.RESET_ALL}")
        return

    print(f"\n{Fore.CYAN}🚀 Connecting to Todoist and fetching project mapping...{Style.RESET_ALL}")
    project_map = build_project_map(client)

    successful_tasks = []
    failed_tasks = []

    print(f"{Fore.CYAN}📋 Creating {len(tasks)} task(s) in Todoist...{Style.RESET_ALL}\n")

    for idx, task in enumerate(tasks, start=1):
        target_project_id = resolve_project_id(task.project_name, project_map)

        if task.project_name and not target_project_id:
            print(
                f"{Fore.YELLOW}⚠ Project '{task.project_name}' not found. "
                f"Task '{task.content}' will be created in default Inbox.{Style.RESET_ALL}"
            )

        try:
            created_task = client.create_task(
                content=task.content,
                project_id=target_project_id,
                due_string=task.due_string,
                priority=task.priority,
                description=task.description or "",
            )

            task_id = created_task.get("id", "N/A")
            task_url = created_task.get("url") or f"https://app.todoist.com/app/task/{task_id}"

            successful_tasks.append({
                "index": idx,
                "content": task.content,
                "project": task.project_name if target_project_id else "Inbox",
                "due": task.due_string or "-",
                "priority": f"p{task.priority}",
                "url": task_url,
            })
            print(f"  {Fore.GREEN}✔ [{idx}/{len(tasks)}] Created: {task.content}{Style.RESET_ALL}")

        except TodoistAPIError as e:
            print(f"  {Fore.RED}✘ [{idx}/{len(tasks)}] Failed: {task.content} -> {e}{Style.RESET_ALL}")
            failed_tasks.append({"task": task, "error": str(e)})

    # Summary Display
    print("\n" + "=" * 80)
    print(f"{Fore.LIGHTCYAN_EX}✨ TODOIST SYNC SUMMARY ✨{Style.RESET_ALL}".center(88))
    print("=" * 80)

    if successful_tasks:
        print(f"\n{Fore.GREEN}✅ Successfully Created Tasks ({len(successful_tasks)}/{len(tasks)}):{Style.RESET_ALL}\n")
        # Table Header
        header = f"{'#':<3} | {'Task Name':<30} | {'Project':<16} | {'Due Date':<15} | {'Priority':<8} | {'Todoist Link'}"
        print(Fore.LIGHTBLACK_EX + header)
        print("-" * len(header) + Style.RESET_ALL)

        for item in successful_tasks:
            name_truncated = (item["content"][:27] + "...") if len(item["content"]) > 30 else item["content"]
            row = (
                f"{item['index']:<3} | "
                f"{Fore.WHITE}{name_truncated:<30}{Style.RESET_ALL} | "
                f"{Fore.YELLOW}{item['project']:<16}{Style.RESET_ALL} | "
                f"{Fore.CYAN}{item['due']:<15}{Style.RESET_ALL} | "
                f"{Fore.MAGENTA}{item['priority']:<8}{Style.RESET_ALL} | "
                f"{Fore.BLUE}{item['url']}{Style.RESET_ALL}"
            )
            print(row)

    if failed_tasks:
        print(f"\n{Fore.RED}❌ Failed Tasks ({len(failed_tasks)}):{Style.RESET_ALL}")
        for item in failed_tasks:
            print(f"  - {item['task'].content} ({item['error']})")

    print("\n" + "=" * 80 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Todoist Gemini Bridge: Parse JSON and batch create tasks in Todoist."
    )
    parser.add_argument(
        "--json",
        "-j",
        type=str,
        help="JSON string of task(s) or batch tasks.",
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        help="Path to a file containing JSON task payload.",
    )

    args = parser.parse_args()

    raw_input_text = ""

    if args.json:
        raw_input_text = args.json
    elif args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                raw_input_text = f.read()
        except FileNotFoundError:
            print(f"{Fore.RED}Error: File not found at '{args.file}'.{Style.RESET_ALL}")
            sys.exit(1)
    else:
        # Check if piped through stdin
        if not sys.stdin.isatty():
            raw_input_text = sys.stdin.read()
        else:
            print(f"{Fore.CYAN}💡 No input argument provided.{Style.RESET_ALL}")
            print("Please enter or paste your JSON task string below (Press Ctrl+Z or Ctrl+D on a new line when done):\n")
            try:
                raw_input_text = sys.stdin.read()
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
                sys.exit(0)

    if not raw_input_text or not raw_input_text.strip():
        print(f"{Fore.RED}Error: No task data provided.{Style.RESET_ALL}")
        sys.exit(1)

    try:
        tasks = parse_tasks_from_json(raw_input_text)
    except TaskParseError as e:
        print(f"{Fore.RED}❌ JSON Parsing Error: {e}{Style.RESET_ALL}")
        sys.exit(1)

    client = TodoistClient()
    process_and_create_tasks(tasks, client)


if __name__ == "__main__":
    main()
