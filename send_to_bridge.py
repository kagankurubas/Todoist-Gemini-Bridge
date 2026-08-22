import argparse
import json
import logging
import sys
from typing import Any, Dict, List
import requests
from colorama import Fore, Style, init as colorama_init
from config import settings
from parser import TaskParseError, parse_tasks_from_json

# Initialize colorama
colorama_init(autoreset=True)

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("send_to_bridge")


def print_response_summary(data: Dict[str, Any]) -> None:
    """
    Renders a formatted colorama table summarizing the API response.
    """
    created_tasks: List[Dict[str, Any]] = data.get("created_tasks", [])
    failed_tasks: List[Dict[str, Any]] = data.get("failed_tasks", [])
    total: int = data.get("total", len(created_tasks) + len(failed_tasks))
    created_count: int = data.get("created_count", len(created_tasks))

    print("\n" + "=" * 80)
    print(f"{Fore.LIGHTCYAN_EX}✨ FASTAPI WEBHOOK SYNC SUMMARY ✨{Style.RESET_ALL}".center(88))
    print("=" * 80)

    if created_tasks:
        print(f"\n{Fore.GREEN}✅ Successfully Created Tasks ({created_count}/{total}):{Style.RESET_ALL}\n")
        header = f"{'#':<3} | {'Task Name':<30} | {'Project':<16} | {'Due Date':<15} | {'Priority':<8} | {'Todoist Link'}"
        print(Fore.LIGHTBLACK_EX + header)
        print("-" * len(header) + Style.RESET_ALL)

        for idx, item in enumerate(created_tasks, start=1):
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

    if failed_tasks:
        print(f"\n{Fore.RED}❌ Failed Tasks ({len(failed_tasks)}):{Style.RESET_ALL}")
        for item in failed_tasks:
            print(f"  - {Fore.YELLOW}{item.get('content')}{Style.RESET_ALL} (Project: {item.get('project_name')}) -> Error: {item.get('error')}")

    print("\n" + "=" * 80 + "\n")


def send_tasks(url: str, token: str, payload_data: List[Dict[str, Any]]) -> None:
    """
    Sends tasks payload to the FastAPI bridge service.
    """
    headers = {
        "Content-Type": "application/json",
        "X-Bridge-Token": token,
    }

    print(f"\n{Fore.CYAN}📡 Sending {len(payload_data)} task(s) to Bridge at {Fore.YELLOW}{url}{Style.RESET_ALL}...")

    try:
        response = requests.post(url, json=payload_data, headers=headers, timeout=30)
    except requests.ConnectionError:
        print(f"\n{Fore.RED}❌ Connection Error: Could not connect to FastAPI server at '{url}'.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}💡 Tip: Ensure the server is running with 'uvicorn app:app --reload --port 8000'{Style.RESET_ALL}\n")
        sys.exit(1)
    except requests.Timeout:
        print(f"\n{Fore.RED}❌ Timeout Error: Request to '{url}' timed out.{Style.RESET_ALL}\n")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"\n{Fore.RED}❌ Request Error: {e}{Style.RESET_ALL}\n")
        sys.exit(1)

    status_code = response.status_code

    if response.ok:
        try:
            data = response.json()
            print(f"{Fore.GREEN}✔ Server responded with HTTP {status_code} OK.{Style.RESET_ALL}")
            print_response_summary(data)
        except ValueError:
            print(f"{Fore.GREEN}✔ Success:{Style.RESET_ALL} {response.text}")
    elif status_code == 401:
        print(f"\n{Fore.RED}❌ HTTP 401 Unauthorized:{Style.RESET_ALL} Invalid or missing X-Bridge-Token.")
        print(f"Response: {response.text}\n")
    elif status_code == 422:
        print(f"\n{Fore.RED}❌ HTTP 422 Unprocessable Entity (Validation Error):{Style.RESET_ALL}")
        try:
            errors = response.json().get("detail", response.text)
            print(json.dumps(errors, indent=2, ensure_ascii=False))
        except Exception:
            print(response.text)
        print()
    elif 500 <= status_code < 600:
        print(f"\n{Fore.RED}❌ HTTP {status_code} Server Error:{Style.RESET_ALL} Todoist Bridge encountered an error.")
        print(f"Response: {response.text}\n")
    else:
        print(f"\n{Fore.RED}❌ HTTP {status_code} Error:{Style.RESET_ALL} {response.text}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send-To-Bridge: CLI client to transmit task payloads to Todoist FastAPI Bridge."
    )
    parser.add_argument(
        "--json",
        "-j",
        type=str,
        help="JSON string or markdown JSON block of tasks.",
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        help="Path to a JSON file containing task payloads.",
    )
    parser.add_argument(
        "--url",
        "-u",
        type=str,
        default="http://127.0.0.1:8000/tasks",
        help="FastAPI /tasks webhook endpoint URL (default: http://127.0.0.1:8000/tasks).",
    )
    parser.add_argument(
        "--token",
        "-t",
        type=str,
        default=settings.WEBHOOK_SECRET_TOKEN,
        help="Secret token for X-Bridge-Token header (defaults to WEBHOOK_SECRET_TOKEN in config.py).",
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
        print(f"{Fore.RED}❌ Task Parsing / Validation Error: {e}{Style.RESET_ALL}")
        sys.exit(1)

    payload_data = [t.model_dump() for t in tasks]
    send_tasks(url=args.url, token=args.token, payload_data=payload_data)


if __name__ == "__main__":
    main()
