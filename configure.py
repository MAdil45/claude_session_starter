#!/usr/bin/env python3
"""Set the daily start time for Claude Session Starter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import starter


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "start_time",
        nargs="?",
        help="daily start time in 24-hour HH:MM format, such as 01:00 or 17:30",
    )
    args = parser.parse_args()
    entered = args.start_time or input("Daily start time (HH:MM): ").strip()

    try:
        schedule = starter.daily_schedule(entered)
        config = starter.load_config()
        config["start_time"] = entered
        # Write atomically so an interruption cannot leave partial JSON.
        temporary = starter.CONFIG_PATH.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        temporary.replace(starter.CONFIG_PATH)
    except (starter.StarterError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Daily start time set to {entered}.")
    print("Schedule: " + " → ".join(schedule) + f" → next day {entered}")
    print("Run ./install.sh to apply this schedule to the system timer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
