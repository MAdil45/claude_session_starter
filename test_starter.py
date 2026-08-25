#!/usr/bin/env python3

import os
from pathlib import Path
import unittest
from unittest.mock import patch
import subprocess

import starter


class StarterTests(unittest.TestCase):
    def test_clean_environment_removes_paid_credentials(self):
        injected = {key: "secret" for key in starter.BLOCKED_ENV_VARS}
        with patch.dict(os.environ, injected, clear=True):
            cleaned = starter.clean_environment()
        for key in starter.BLOCKED_ENV_VARS:
            self.assertNotIn(key, cleaned)

    def test_command_is_minimal_and_nonpersistent(self):
        config = {
            "prompt": "Hi",
            "model": "claude-haiku-4-5",
            "effort": "low",
            "timeout_seconds": 180,
        }
        command = starter.greeting_command("/path/to/claude", config)
        self.assertIn("--no-session-persistence", command)
        self.assertIn("--safe-mode", command)
        self.assertEqual(command[command.index("--effort") + 1], "low")
        self.assertEqual(command[command.index("--tools") + 1], "")

    def test_current_config_is_valid(self):
        config = starter.load_config()
        self.assertEqual(config["start_time"], "01:00")
        self.assertEqual(config["model"], "claude-haiku-4-5")

    def test_one_am_schedule_restarts_daily(self):
        self.assertEqual(
            starter.daily_schedule("01:00"),
            ["01:00", "06:00", "11:00", "16:00", "21:00"],
        )

    def test_minutes_are_preserved(self):
        self.assertEqual(
            starter.daily_schedule("03:37"),
            ["03:37", "08:37", "13:37", "18:37", "23:37"],
        )

    def test_late_start_does_not_roll_into_next_day(self):
        self.assertEqual(starter.daily_schedule("21:00"), ["21:00"])

    def test_invalid_time_is_rejected(self):
        with self.assertRaises(starter.StarterError):
            starter.daily_schedule("25:00")

    def test_success_event_logs_message_model_effort_and_source(self):
        config = {
            "prompt": "Good morning",
            "model": "claude-haiku-4-5",
            "effort": "xhigh",
            "timeout_seconds": 180,
        }
        result = subprocess.CompletedProcess(
            ["claude"],
            0,
            '{"is_error":false,"duration_ms":10,"session_id":"test"}',
            "",
        )
        with patch.object(starter, "run_process", return_value=result), patch.object(
            starter, "write_event"
        ) as write_event:
            starter.send_greeting("claude", {}, config, source="manual")
        write_event.assert_called_once()
        _, kwargs = write_event.call_args
        self.assertEqual(kwargs["message"], "Good morning")
        self.assertEqual(kwargs["model"], "claude-haiku-4-5")
        self.assertEqual(kwargs["effort"], "xhigh")
        self.assertEqual(kwargs["source"], "manual")


if __name__ == "__main__":
    unittest.main()
