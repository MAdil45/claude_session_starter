#!/usr/bin/env python3
"""Send a minimal Claude greeting using Claude.ai subscription authentication."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone


APP_NAME = "claude-session-starter"
APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
STATE_DIR = Path(
    os.environ.get(
        "CLAUDE_SESSION_STARTER_STATE_DIR",
        str(Path.home() / ".local" / "state" / APP_NAME),
    )
)
LOG_PATH = STATE_DIR / "events.jsonl"
LOCK_PATH = STATE_DIR / "run.lock"

# Removing these prevents an API key or third-party provider setting in the
# service environment from silently turning a subscription run into paid usage.
BLOCKED_ENV_VARS = {
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
}

SUPPORTED_EFFORTS = {"low", "medium", "high", "xhigh", "max"}


class StarterError(RuntimeError):
    pass


def clean_environment() -> dict[str, str]:
    env = os.environ.copy()
    for key in BLOCKED_ENV_VARS:
        env.pop(key, None)
    # User services often receive a shorter PATH than interactive shells.
    additions = [str(Path.home() / ".local" / "bin"), "/usr/local/bin"]
    current = env.get("PATH", "/usr/bin:/bin")
    env["PATH"] = os.pathsep.join(additions + [current])
    return env


def load_config() -> dict:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StarterError(f"Cannot read {CONFIG_PATH}: {exc}") from exc

    required = {"prompt", "model", "effort", "timeout_seconds", "start_time"}
    missing = sorted(required - config.keys())
    if missing:
        raise StarterError(f"Missing config values: {', '.join(missing)}")
    daily_schedule(str(config["start_time"]))
    if str(config["effort"]) not in SUPPORTED_EFFORTS:
        raise StarterError(
            "effort must be one of: low, medium, high, xhigh, max"
        )
    if not str(config["prompt"]).strip():
        raise StarterError("prompt cannot be empty")
    if not str(config["model"]).strip():
        raise StarterError("model cannot be empty")
    return config


def daily_schedule(start_time: str) -> list[str]:
    """Return five-hour anchors that remain within one calendar day."""
    try:
        start = datetime.strptime(start_time, "%H:%M")
    except ValueError as exc:
        raise StarterError("start_time must use 24-hour HH:MM format") from exc

    start_minutes = start.hour * 60 + start.minute
    return [
        f"{minutes // 60:02d}:{minutes % 60:02d}"
        for minutes in range(start_minutes, 24 * 60, 5 * 60)
    ]


def systemd_calendar_values(start_time: str) -> list[str]:
    return [f"*-*-* {value}:00" for value in daily_schedule(start_time)]


def find_claude(env: dict[str, str]) -> str:
    configured = os.environ.get("CLAUDE_SESSION_STARTER_CLI")
    executable = configured or shutil.which("claude", path=env["PATH"])
    if not executable:
        raise StarterError("Claude CLI was not found in PATH")
    return executable


def run_process(command: list[str], env: dict[str, str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=APP_DIR,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise StarterError(f"Command timed out after {timeout} seconds") from exc


def subscription_status(claude: str, env: dict[str, str]) -> dict:
    result = run_process([claude, "auth", "status", "--json"], env)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise StarterError(f"Could not check Claude authentication: {detail}")
    try:
        status = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise StarterError("Claude returned an unreadable authentication status") from exc

    if not status.get("loggedIn"):
        raise StarterError("Claude is not logged in; run `claude auth login`")
    if status.get("authMethod") != "claude.ai":
        raise StarterError(
            "Refusing to send: Claude is not authenticated through claude.ai "
            f"(detected {status.get('authMethod')!r})"
        )
    if status.get("subscriptionType") != "pro":
        raise StarterError(
            "Refusing to send: expected a Pro subscription "
            f"(detected {status.get('subscriptionType')!r})"
        )
    return status


def greeting_command(claude: str, config: dict) -> list[str]:
    return [
        claude,
        "-p",
        str(config["prompt"]),
        "--model",
        str(config["model"]),
        "--effort",
        str(config["effort"]),
        "--tools",
        "",
        "--safe-mode",
        "--no-session-persistence",
        "--system-prompt",
        "Reply with only: Hi",
        "--output-format",
        "json",
    ]


def write_event(status: str, **details: object) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "status": status,
        **details,
    }
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, separators=(",", ":")) + "\n")


def send_greeting(
    claude: str,
    env: dict[str, str],
    config: dict,
    source: str = "scheduled",
) -> None:
    result = run_process(
        greeting_command(claude, config),
        env,
        timeout=int(config["timeout_seconds"]),
    )
    metadata: dict[str, object] = {}
    payload: dict[str, object] = {}
    try:
        payload = json.loads(result.stdout)
        for key in ("duration_ms", "duration_api_ms", "num_turns", "is_error", "session_id"):
            if key in payload:
                metadata[key] = payload[key]
    except json.JSONDecodeError:
        metadata["response_format"] = "non-json"

    if result.returncode != 0 or payload.get("is_error"):
        detail = (result.stderr or result.stdout).strip()[-1000:]
        raise StarterError(f"Claude greeting failed: {detail}")
    write_event(
        "sent",
        message=config["prompt"],
        model=config["model"],
        effort=config["effort"],
        source=source,
        **metadata,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify configuration and Pro authentication without sending",
    )
    parser.add_argument(
        "--show-command",
        action="store_true",
        help="display the command after validating authentication; do not send",
    )
    parser.add_argument(
        "--show-schedule",
        action="store_true",
        help="display the calculated daily schedule without authenticating or sending",
    )
    parser.add_argument(
        "--source",
        choices=("scheduled", "manual"),
        default="scheduled",
        help="identify whether the invocation came from the timer or the GUI",
    )
    args = parser.parse_args()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with LOCK_PATH.open("w", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            env = clean_environment()
            config = load_config()
            if args.show_schedule:
                print(" → ".join(daily_schedule(str(config["start_time"]))))
                return 0

            claude = find_claude(env)
            status = subscription_status(claude, env)

            if args.check:
                print(
                    "Ready: Claude CLI is authenticated through claude.ai "
                    f"with a {status['subscriptionType']} subscription."
                )
                return 0
            if args.show_command:
                print(json.dumps(greeting_command(claude, config)))
                return 0

            send_greeting(claude, env, config, source=args.source)
            print(
                f"Greeting sent with {config['model']} "
                f"at {config['effort']} effort."
            )
            return 0
    except BlockingIOError:
        print("Another greeting attempt is already running; skipped.", file=sys.stderr)
        return 0
    except StarterError as exc:
        try:
            failure_config = locals().get("config", {})
            write_event(
                "blocked",
                message=failure_config.get("prompt", ""),
                model=failure_config.get("model", ""),
                effort=failure_config.get("effort", ""),
                source=args.source,
                detail=str(exc),
            )
        except OSError:
            pass
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
