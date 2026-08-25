"""Pure application logic shared by the Linen Minimal GUI and its tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import subprocess
from typing import Callable

import starter


MODEL_CHOICES = (
    ("Claude Haiku 4.5", "claude-haiku-4-5"),
    ("Claude Sonnet 5", "claude-sonnet-5"),
    ("Claude Opus 5", "claude-opus-5"),
)
EFFORT_CHOICES = (
    ("Low", "low"),
    ("Medium", "medium"),
    ("High", "high"),
    ("Extra", "xhigh"),
    ("Max", "max"),
)


@dataclass(frozen=True)
class ScheduleState:
    slots: tuple[str, ...]
    next_slot: str
    next_at: datetime
    is_tomorrow: bool


@dataclass(frozen=True)
class ActivityEvent:
    timestamp: datetime
    status: str
    message: str
    model: str
    effort: str
    source: str
    detail: str


def schedule_state(start_time: str, now: datetime | None = None) -> ScheduleState:
    current = now or datetime.now().astimezone()
    current_minute = current.replace(second=0, microsecond=0)
    slots = tuple(starter.daily_schedule(start_time))
    for slot in slots:
        hour, minute = (int(part) for part in slot.split(":"))
        candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate >= current_minute:
            return ScheduleState(slots, slot, candidate, False)

    first_hour, first_minute = (int(part) for part in slots[0].split(":"))
    candidate = (current + timedelta(days=1)).replace(
        hour=first_hour,
        minute=first_minute,
        second=0,
        microsecond=0,
    )
    return ScheduleState(slots, slots[0], candidate, True)


def read_activity(
    log_path: Path = starter.LOG_PATH,
    day: date | None = None,
) -> list[ActivityEvent]:
    selected_day = day or datetime.now().astimezone().date()
    if not log_path.exists():
        return []

    events: list[ActivityEvent] = []
    for raw_line in log_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
            timestamp = datetime.fromisoformat(str(payload["timestamp"]))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        if timestamp.astimezone().date() != selected_day:
            continue
        events.append(
            ActivityEvent(
                timestamp=timestamp,
                status=str(payload.get("status", "unknown")),
                message=str(payload.get("message", "")),
                model=str(payload.get("model", "")),
                effort=str(payload.get("effort", "")),
                source=str(payload.get("source", "scheduled")),
                detail=str(payload.get("detail", "")),
            )
        )
    return sorted(events, key=lambda event: event.timestamp)


def model_label(model_id: str) -> str:
    return next((label for label, value in MODEL_CHOICES if value == model_id), model_id)


def effort_label(effort_id: str) -> str:
    return next((label for label, value in EFFORT_CHOICES if value == effort_id), effort_id)


def validate_settings(start_time: str, model: str, effort: str, message: str) -> None:
    starter.daily_schedule(start_time)
    if model not in {value for _, value in MODEL_CHOICES}:
        raise starter.StarterError("Choose a supported Claude model")
    if effort not in {value for _, value in EFFORT_CHOICES}:
        raise starter.StarterError("Choose a supported effort level")
    if not message.strip():
        raise starter.StarterError("Message cannot be empty")


def save_settings(start_time: str, model: str, effort: str, message: str) -> dict:
    validate_settings(start_time, model, effort, message)
    config = starter.load_config()
    config.update(
        {
            "start_time": start_time,
            "model": model,
            "effort": effort,
            "prompt": message.strip(),
        }
    )
    temporary = starter.CONFIG_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    temporary.replace(starter.CONFIG_PATH)
    return config


def timer_is_active(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> bool:
    result = runner(
        ["systemctl", "--user", "is-active", "--quiet", "claude-session-starter.timer"],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def start_automation(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    return runner(
        ["python3", str(starter.APP_DIR / "install.py")],
        text=True,
        capture_output=True,
        check=False,
    )


def stop_automation(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    return runner(
        ["systemctl", "--user", "disable", "--now", "claude-session-starter.timer"],
        text=True,
        capture_output=True,
        check=False,
    )
