#!/usr/bin/env python3
"""Install and enable the per-user systemd service and calculated timer."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

import starter


def timer_text(start_time: str) -> str:
    calendar = "\n".join(
        f"OnCalendar={value}" for value in starter.systemd_calendar_values(start_time)
    )
    return f"""[Unit]
Description=Send Claude Pro greetings from a configurable daily anchor

[Timer]
{calendar}
AccuracySec=5s
RandomizedDelaySec=0
Persistent=false
Unit=claude-session-starter.service

[Install]
WantedBy=timers.target
"""


def service_text() -> str:
    template = (
        starter.APP_DIR / "systemd" / "claude-session-starter.service.in"
    ).read_text(encoding="utf-8")
    return template.replace("__STARTER_PATH__", str(starter.APP_DIR / "starter.py"))


def desktop_entry_text() -> str:
    return f"""[Desktop Entry]
Type=Application
Name=Claude Session Starter
Comment=Manage daily Claude Pro session anchors
Exec={starter.APP_DIR / 'run-app.sh'}
Icon={starter.APP_DIR / 'assets' / 'claude-session-starter.svg'}
Terminal=false
Categories=Utility;
StartupNotify=true
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show the calculated schedule without installing anything",
    )
    args = parser.parse_args()

    try:
        config = starter.load_config()
        schedule = starter.daily_schedule(str(config["start_time"]))
        if args.dry_run:
            print("Schedule: " + " → ".join(schedule))
            print(timer_text(str(config["start_time"])))
            return 0

        unit_dir = Path.home() / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "claude-session-starter.service").write_text(
            service_text(), encoding="utf-8"
        )
        (unit_dir / "claude-session-starter.timer").write_text(
            timer_text(str(config["start_time"])), encoding="utf-8"
        )
        applications_dir = Path.home() / ".local" / "share" / "applications"
        applications_dir.mkdir(parents=True, exist_ok=True)
        (applications_dir / "claude-session-starter.desktop").write_text(
            desktop_entry_text(), encoding="utf-8"
        )
        (starter.APP_DIR / "starter.py").chmod(0o775)
        (starter.APP_DIR / "app.py").chmod(0o775)
        (starter.APP_DIR / "run-app.sh").chmod(0o775)

        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", "claude-session-starter.timer"],
            check=True,
        )
        subprocess.run(
            [
                "systemctl",
                "--user",
                "list-timers",
                "claude-session-starter.timer",
                "--no-pager",
            ],
            check=True,
        )
    except (OSError, starter.StarterError, subprocess.CalledProcessError) as exc:
        print(f"Installation failed: {exc}", file=sys.stderr)
        return 1

    print("Installed schedule: " + " → ".join(schedule))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
