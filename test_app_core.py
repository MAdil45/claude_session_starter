#!/usr/bin/env python3

from datetime import date, datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import app_core
import starter


class AppCoreTests(unittest.TestCase):
    def test_next_slot_is_selected_today(self):
        state = app_core.schedule_state(
            "01:00",
            datetime(2026, 8, 24, 5, 45, tzinfo=timezone.utc),
        )
        self.assertEqual(state.slots, ("01:00", "06:00", "11:00", "16:00", "21:00"))
        self.assertEqual(state.next_slot, "06:00")
        self.assertFalse(state.is_tomorrow)

    def test_after_last_slot_selects_tomorrows_first_slot(self):
        state = app_core.schedule_state(
            "01:00",
            datetime(2026, 8, 24, 22, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(state.next_slot, "01:00")
        self.assertTrue(state.is_tomorrow)
        self.assertEqual(state.next_at.date(), date(2026, 8, 25))

    def test_due_slot_remains_selected_during_its_minute(self):
        state = app_core.schedule_state(
            "01:00",
            datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(state.next_slot, "06:00")

    def test_activity_contains_only_selected_local_day_and_is_sorted(self):
        lines = [
            {
                "timestamp": "2026-08-24T16:00:01+00:00",
                "status": "sent",
                "message": "Good afternoon",
                "model": "claude-sonnet-5",
                "effort": "medium",
                "source": "scheduled",
            },
            {
                "timestamp": "2026-08-23T21:00:01+00:00",
                "status": "sent",
                "message": "Old",
                "model": "claude-haiku-4-5",
                "effort": "low",
            },
            {
                "timestamp": "2026-08-24T06:00:01+00:00",
                "status": "blocked",
                "message": "Hello",
                "model": "claude-haiku-4-5",
                "effort": "xhigh",
                "detail": "Network unavailable",
            },
        ]
        with tempfile.TemporaryDirectory() as temporary:
            log_path = Path(temporary) / "events.jsonl"
            log_path.write_text(
                "\n".join(json.dumps(line) for line in lines) + "\n",
                encoding="utf-8",
            )
            activity = app_core.read_activity(log_path, date(2026, 8, 24))
        self.assertEqual(len(activity), 2)
        self.assertEqual(activity[0].message, "Hello")
        self.assertEqual(activity[0].effort, "xhigh")
        self.assertEqual(activity[1].model, "claude-sonnet-5")

    def test_activity_ignores_malformed_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            log_path = Path(temporary) / "events.jsonl"
            log_path.write_text("not-json\n{}\n", encoding="utf-8")
            self.assertEqual(app_core.read_activity(log_path, date.today()), [])

    def test_save_settings_persists_all_user_fields(self):
        original = {
            "prompt": "Hi",
            "model": "claude-haiku-4-5",
            "effort": "low",
            "timeout_seconds": 180,
            "start_time": "01:00",
        }
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "config.json"
            config_path.write_text(json.dumps(original), encoding="utf-8")
            with patch.object(starter, "CONFIG_PATH", config_path):
                saved = app_core.save_settings(
                    "03:30", "claude-sonnet-5", "xhigh", "Good morning"
                )
                persisted = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["start_time"], "03:30")
        self.assertEqual(persisted["model"], "claude-sonnet-5")
        self.assertEqual(persisted["effort"], "xhigh")
        self.assertEqual(persisted["prompt"], "Good morning")

    def test_empty_message_is_rejected(self):
        with self.assertRaises(starter.StarterError):
            app_core.validate_settings("01:00", "claude-haiku-4-5", "low", "  ")

    def test_timer_status_and_stop_use_user_systemd(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        self.assertTrue(app_core.timer_is_active(runner))
        result = app_core.stop_automation(runner)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            calls[-1],
            ["systemctl", "--user", "disable", "--now", "claude-session-starter.timer"],
        )


if __name__ == "__main__":
    unittest.main()
