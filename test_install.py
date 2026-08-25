#!/usr/bin/env python3

import unittest

import install


class InstallTests(unittest.TestCase):
    def test_one_am_timer_contains_only_same_day_slots(self):
        timer = install.timer_text("01:00")
        for slot in ("01:00:00", "06:00:00", "11:00:00", "16:00:00", "21:00:00"):
            self.assertIn(f"OnCalendar=*-*-* {slot}", timer)
        self.assertNotIn("02:00:00", timer)
        self.assertIn("Persistent=false", timer)

    def test_desktop_entry_launches_graphical_app(self):
        entry = install.desktop_entry_text()
        self.assertIn("Name=Claude Session Starter", entry)
        self.assertIn("run-app.sh", entry)
        self.assertIn("Terminal=false", entry)
        self.assertIn("claude-session-starter.svg", entry)

    def test_service_uses_current_project_starter(self):
        service = install.service_text()
        self.assertNotIn("__STARTER_PATH__", service)
        self.assertIn("starter.py", service)
        self.assertIn("UnsetEnvironment=ANTHROPIC_API_KEY", service)


if __name__ == "__main__":
    unittest.main()
