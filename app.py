#!/usr/bin/env python3
"""Linen Minimal desktop interface for Claude Session Starter."""

from __future__ import annotations

from datetime import datetime
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

import app_core
import starter


COLORS = {
    "window": "#F2EEE7",
    "sidebar": "#E7E0D4",
    "sidebar_line": "#D8D0C3",
    "surface": "#FBFAF7",
    "surface_alt": "#F5F1EA",
    "text": "#292923",
    "muted": "#7B7469",
    "border": "#DED8CE",
    "primary": "#34483A",
    "primary_hover": "#293A2E",
    "primary_text": "#FFFFFF",
    "success_bg": "#DCE7D7",
    "success_text": "#3E5B38",
    "paused_bg": "#E8DED0",
    "paused_text": "#7B6348",
    "danger_bg": "#FFF7F5",
    "danger_border": "#D2AAA2",
    "danger_text": "#9E4D42",
    "selection": "#2E322C",
    "selection_text": "#FFFFFF",
}

UI_FONT = "texgyreheros"


def select_ui_font(root: tk.Misc) -> str:
    """Choose a scalable sans font that this Tk build can actually render."""
    available = {family.casefold(): family for family in tkfont.families(root)}
    for preferred in (
        "Inter",
        "Noto Sans",
        "DejaVu Sans",
        "Ubuntu",
        "texgyreheros",
        "latin modern sans",
    ):
        if preferred.casefold() in available:
            return available[preferred.casefold()]
    return tkfont.nametofont("TkDefaultFont", root=root).actual("family")


class TimePicker(tk.Frame):
    """Compact 24-hour clock control backed by a HH:MM StringVar."""

    def __init__(
        self,
        parent: tk.Widget,
        value: tk.StringVar,
        command: object,
    ) -> None:
        super().__init__(
            parent,
            bg="#FFFFFF",
            highlightbackground="#D9D2C7",
            highlightcolor=COLORS["primary"],
            highlightthickness=1,
        )
        self.value = value
        self.command = command
        self.syncing = False
        self.hour = tk.StringVar(value="00")
        self.minute = tk.StringVar(value="00")

        clock = tk.Canvas(
            self,
            width=22,
            height=22,
            bg="#FFFFFF",
            highlightthickness=0,
        )
        clock.create_oval(3, 3, 19, 19, outline=COLORS["muted"], width=2)
        clock.create_line(11, 11, 11, 6, fill=COLORS["muted"], width=2)
        clock.create_line(11, 11, 15, 13, fill=COLORS["muted"], width=2)
        clock.pack(side="left", padx=(10, 6), pady=5)
        self.hour_spin = self._selector(self.hour, range(24))
        self.hour_spin.pack(side="left", pady=5)
        tk.Label(
            self,
            text=":",
            bg="#FFFFFF",
            fg=COLORS["text"],
            font=(UI_FONT, 11, "bold"),
        ).pack(side="left", padx=3)
        self.minute_spin = self._selector(self.minute, range(60))
        self.minute_spin.pack(side="left", pady=5)
        tk.Label(
            self,
            text="24-hour",
            bg="#FFFFFF",
            fg="#948B80",
            font=(UI_FONT, 8),
        ).pack(side="left", padx=(8, 10))

        self.hour.trace_add("write", self._parts_changed)
        self.minute.trace_add("write", self._parts_changed)
        self.value.trace_add("write", self._value_changed)
        self._sync_from_value()

    def _selector(self, variable: tk.StringVar, values: range) -> ttk.Combobox:
        selector = ttk.Combobox(
            self,
            width=3,
            textvariable=variable,
            justify="center",
            values=[f"{value:02d}" for value in values],
            state="readonly",
            style="Linen.Time.TCombobox",
        )
        selector.bind("<<ComboboxSelected>>", self._parts_changed)
        return selector

    def _sync_from_value(self) -> None:
        try:
            hour, minute = (int(part) for part in self.value.get().split(":"))
        except (TypeError, ValueError):
            return
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            return
        self.syncing = True
        self.hour.set(f"{hour:02d}")
        self.minute.set(f"{minute:02d}")
        self.syncing = False

    def _value_changed(self, *_args: object) -> None:
        if not self.syncing:
            self._sync_from_value()

    def _parts_changed(self, *_args: object) -> None:
        if self.syncing:
            return
        try:
            hour = int(self.hour.get())
            minute = int(self.minute.get())
        except ValueError:
            return
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            return
        new_value = f"{hour:02d}:{minute:02d}"
        if self.value.get() != new_value:
            self.syncing = True
            self.value.set(new_value)
            self.syncing = False
        self.after_idle(self.command)


class LinenApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        global UI_FONT
        UI_FONT = select_ui_font(self)
        for named_font in (
            "TkDefaultFont",
            "TkTextFont",
            "TkHeadingFont",
            "TkMenuFont",
            "TkTooltipFont",
        ):
            try:
                tkfont.nametofont(named_font, root=self).configure(family=UI_FONT)
            except tk.TclError:
                pass
        self.title("Claude Session Starter")
        self.geometry("1040x690")
        self.minsize(880, 610)
        self.configure(bg=COLORS["window"])
        self.option_add("*Font", f"{{{UI_FONT}}} 10")

        self.model_by_label = dict(app_core.MODEL_CHOICES)
        self.model_label_by_id = {value: label for label, value in app_core.MODEL_CHOICES}
        self.effort_by_label = dict(app_core.EFFORT_CHOICES)
        self.effort_label_by_id = {value: label for label, value in app_core.EFFORT_CHOICES}
        self.slot_labels: dict[str, tk.Label] = {}
        self.pages: dict[str, tk.Frame] = {}
        self.nav_buttons: dict[str, tk.Button] = {}
        self.current_page = "schedule"
        self.timer_active = False
        self.operation_running = False

        self.start_time_var = tk.StringVar()
        self.model_var = tk.StringVar()
        self.effort_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Checking automation…")
        self.next_run_var = tk.StringVar(value="Calculating next run…")
        self.activity_summary_var = tk.StringVar(value="Today")
        self.system_auth_var = tk.StringVar(value="Checking Claude authentication…")
        self.system_timer_var = tk.StringVar(value="Checking timer status…")
        self.config_path_var = tk.StringVar(value=str(starter.CONFIG_PATH))
        self.log_path_var = tk.StringVar(value=str(starter.LOG_PATH))

        self._configure_ttk()
        self._build_shell()
        self._load_configuration()
        self.show_page("schedule")
        self.refresh_all()

    def _configure_ttk(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Linen.TCombobox",
            fieldbackground="#FFFFFF",
            background="#FFFFFF",
            foreground=COLORS["text"],
            bordercolor="#D9D2C7",
            lightcolor="#D9D2C7",
            darkcolor="#D9D2C7",
            arrowcolor=COLORS["muted"],
            padding=8,
        )
        style.map(
            "Linen.TCombobox",
            fieldbackground=[("readonly", "#FFFFFF")],
            selectbackground=[("readonly", "#FFFFFF")],
            selectforeground=[("readonly", COLORS["text"])],
        )
        style.configure(
            "Linen.Time.TCombobox",
            fieldbackground="#FFFFFF",
            background="#EEE9E0",
            foreground=COLORS["text"],
            bordercolor="#D9D2C7",
            lightcolor="#D9D2C7",
            darkcolor="#D9D2C7",
            arrowcolor=COLORS["muted"],
            padding=4,
        )
        style.map(
            "Linen.Time.TCombobox",
            fieldbackground=[("readonly", "#FFFFFF")],
            selectbackground=[("readonly", "#FFFFFF")],
            selectforeground=[("readonly", COLORS["text"])],
        )
        style.configure(
            "Linen.Treeview",
            background=COLORS["surface"],
            fieldbackground=COLORS["surface"],
            foreground=COLORS["text"],
            borderwidth=0,
            rowheight=36,
        )
        style.configure(
            "Linen.Treeview.Heading",
            background=COLORS["surface_alt"],
            foreground=COLORS["muted"],
            relief="flat",
            padding=(8, 10),
            font=(UI_FONT, 9, "bold"),
        )
        style.map("Linen.Treeview", background=[("selected", "#DCE7D7")])

    def _build_shell(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = tk.Frame(
            self,
            width=205,
            bg=COLORS["sidebar"],
            highlightbackground=COLORS["sidebar_line"],
            highlightthickness=1,
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        brand = tk.Frame(sidebar, bg=COLORS["sidebar"])
        brand.pack(fill="x", padx=22, pady=(28, 36))
        tk.Label(
            brand,
            text="SESSION",
            bg=COLORS["sidebar"],
            fg=COLORS["text"],
            font=(UI_FONT, 12, "bold"),
        ).pack(side="left")
        tk.Label(
            brand,
            text=" / STARTER",
            bg=COLORS["sidebar"],
            fg="#7A6B52",
            font=(UI_FONT, 12),
        ).pack(side="left")

        for key, label in (
            ("schedule", "Schedule"),
            ("activity", "Activity"),
            ("system", "System"),
        ):
            button = tk.Button(
                sidebar,
                text=label,
                anchor="w",
                borderwidth=0,
                relief="flat",
                bg=COLORS["sidebar"],
                fg=COLORS["muted"],
                activebackground="#DCD4C7",
                activeforeground=COLORS["text"],
                padx=15,
                pady=11,
                cursor="hand2",
                command=lambda page=key: self.show_page(page),
            )
            button.pack(fill="x", padx=16, pady=2)
            self.nav_buttons[key] = button

        tk.Label(
            sidebar,
            text="Claude.ai Pro\nLocal server automation",
            justify="left",
            bg=COLORS["sidebar"],
            fg="#8B8276",
            font=(UI_FONT, 9),
        ).pack(side="bottom", anchor="w", padx=24, pady=25)

        content = tk.Frame(self, bg=COLORS["window"])
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        self.pages["schedule"] = self._build_schedule_page(content)
        self.pages["activity"] = self._build_activity_page(content)
        self.pages["system"] = self._build_system_page(content)
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

    def _page_header(self, parent: tk.Widget, title: str, subtitle: str) -> tk.Frame:
        header = tk.Frame(parent, bg=COLORS["window"])
        header.pack(fill="x", pady=(0, 22))
        tk.Label(
            header,
            text=title,
            bg=COLORS["window"],
            fg=COLORS["text"],
            font=(UI_FONT, 21, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text=subtitle,
            bg=COLORS["window"],
            fg=COLORS["muted"],
            font=(UI_FONT, 10),
        ).pack(anchor="w", pady=(4, 0))
        return header

    def _build_schedule_page(self, parent: tk.Widget) -> tk.Frame:
        page = tk.Frame(parent, bg=COLORS["window"], padx=32, pady=28)
        self._page_header(page, "Daily schedule", "Quiet, reliable Claude session automation.")

        status_row = tk.Frame(page, bg=COLORS["window"])
        status_row.pack(fill="x", pady=(0, 14))
        self.status_badge = tk.Label(
            status_row,
            textvariable=self.status_var,
            bg=COLORS["paused_bg"],
            fg=COLORS["paused_text"],
            padx=12,
            pady=8,
            font=(UI_FONT, 9, "bold"),
        )
        self.status_badge.pack(side="left")
        tk.Label(
            status_row,
            textvariable=self.next_run_var,
            bg=COLORS["window"],
            fg=COLORS["muted"],
            font=(UI_FONT, 10),
        ).pack(side="right", pady=8)

        surface = tk.Frame(
            page,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=22,
            pady=20,
        )
        surface.pack(fill="both", expand=True)
        surface.grid_columnconfigure(0, weight=1)
        surface.grid_columnconfigure(1, weight=1)

        self._field_label(surface, "Start time", 0, 0)
        self.start_time_picker = TimePicker(
            surface,
            value=self.start_time_var,
            command=self.refresh_schedule,
        )
        self.start_time_picker.grid(row=1, column=0, sticky="ew", padx=(0, 8))

        self._field_label(surface, "Model", 0, 1)
        self.model_combo = ttk.Combobox(
            surface,
            textvariable=self.model_var,
            values=[label for label, _ in app_core.MODEL_CHOICES],
            state="readonly",
            style="Linen.TCombobox",
        )
        self.model_combo.grid(row=1, column=1, sticky="ew", padx=(8, 0))

        self._field_label(surface, "Effort level", 2, 0, columnspan=2, pady=(17, 0))
        self.effort_combo = ttk.Combobox(
            surface,
            textvariable=self.effort_var,
            values=[label for label, _ in app_core.EFFORT_CHOICES],
            state="readonly",
            style="Linen.TCombobox",
        )
        self.effort_combo.grid(row=3, column=0, columnspan=2, sticky="ew")

        self._field_label(surface, "Message", 4, 0, columnspan=2, pady=(17, 0))
        self.message_text = tk.Text(
            surface,
            height=4,
            wrap="word",
            bg="#FFFFFF",
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            highlightbackground="#D9D2C7",
            highlightcolor=COLORS["primary"],
            highlightthickness=1,
            padx=11,
            pady=9,
            font=(UI_FONT, 10),
        )
        self.message_text.grid(row=5, column=0, columnspan=2, sticky="nsew")
        surface.grid_rowconfigure(5, weight=1)

        schedule_header = tk.Frame(surface, bg=COLORS["surface"])
        schedule_header.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(18, 8))
        tk.Label(
            schedule_header,
            text="Today's schedule",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(UI_FONT, 9, "bold"),
        ).pack(side="left")

        self.schedule_slots = tk.Frame(surface, bg=COLORS["surface"])
        self.schedule_slots.grid(row=7, column=0, columnspan=2, sticky="ew")

        footer = tk.Frame(surface, bg=COLORS["surface"])
        footer.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(22, 0))
        self.save_button = self._button(
            footer, "Save settings", self.save_configuration, "secondary"
        )
        self.save_button.pack(side="left")
        self.test_button = self._button(
            footer, "Send test", self.send_test, "secondary"
        )
        self.test_button.pack(side="left", padx=8)
        self.stop_button = self._button(
            footer, "Stop", self.stop_service, "danger"
        )
        self.stop_button.pack(side="right")
        self.start_button = self._button(
            footer, "Start automation", self.start_service, "primary"
        )
        self.start_button.pack(side="right", padx=8)
        return page

    def _build_activity_page(self, parent: tk.Widget) -> tk.Frame:
        page = tk.Frame(parent, bg=COLORS["window"], padx=32, pady=28)
        header = self._page_header(
            page,
            "Activity",
            "Every message attempt recorded during the current local day.",
        )
        tk.Label(
            header,
            textvariable=self.activity_summary_var,
            bg=COLORS["window"],
            fg=COLORS["primary"],
            font=(UI_FONT, 10, "bold"),
        ).pack(side="right", anchor="e")

        table_shell = tk.Frame(
            page,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        table_shell.pack(fill="both", expand=True)
        table_shell.grid_rowconfigure(0, weight=1)
        table_shell.grid_columnconfigure(0, weight=1)

        columns = ("time", "status", "message", "model", "effort")
        self.activity_tree = ttk.Treeview(
            table_shell,
            columns=columns,
            show="headings",
            style="Linen.Treeview",
        )
        self.activity_tree.heading("time", text="Time")
        self.activity_tree.heading("status", text="Status")
        self.activity_tree.heading("message", text="Message")
        self.activity_tree.heading("model", text="Model")
        self.activity_tree.heading("effort", text="Effort")
        self.activity_tree.column("time", width=95, minwidth=80, stretch=False)
        self.activity_tree.column("status", width=105, minwidth=90, stretch=False)
        self.activity_tree.column("message", width=260, minwidth=160, stretch=True)
        self.activity_tree.column("model", width=165, minwidth=130, stretch=False)
        self.activity_tree.column("effort", width=90, minwidth=75, stretch=False)
        self.activity_tree.tag_configure("failed", foreground=COLORS["danger_text"])
        self.activity_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            table_shell, orient="vertical", command=self.activity_tree.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.activity_tree.configure(yscrollcommand=scrollbar.set)

        self.empty_activity = tk.Label(
            table_shell,
            text="No activity recorded today.",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(UI_FONT, 11),
        )
        return page

    def _build_system_page(self, parent: tk.Widget) -> tk.Frame:
        page = tk.Frame(parent, bg=COLORS["window"], padx=32, pady=28)
        self._page_header(
            page,
            "System",
            "Subscription, scheduler, and local storage information.",
        )
        surface = tk.Frame(
            page,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=22,
            pady=20,
        )
        surface.pack(fill="x")
        self._info_row(surface, "Claude authentication", self.system_auth_var, 0)
        self._info_row(surface, "Automation timer", self.system_timer_var, 1)
        self._info_row(surface, "Configuration", self.config_path_var, 2)
        self._info_row(surface, "Activity log", self.log_path_var, 3)
        tk.Label(
            page,
            text=(
                "The graphical app may be closed after automation starts. "
                "The user-level systemd timer continues running independently."
            ),
            wraplength=690,
            justify="left",
            bg=COLORS["window"],
            fg=COLORS["muted"],
            font=(UI_FONT, 10),
        ).pack(anchor="w", pady=(18, 0))
        return page

    def _field_label(
        self,
        parent: tk.Widget,
        text: str,
        row: int,
        column: int,
        columnspan: int = 1,
        pady: tuple[int, int] = (0, 0),
    ) -> None:
        tk.Label(
            parent,
            text=text,
            bg=COLORS["surface"],
            fg="#625E56",
            font=(UI_FONT, 9, "bold"),
        ).grid(
            row=row,
            column=column,
            columnspan=columnspan,
            sticky="w",
            padx=(0, 8) if column == 0 else (8, 0),
            pady=(pady[0], 7),
        )

    def _button(
        self,
        parent: tk.Widget,
        text: str,
        command: object,
        kind: str,
    ) -> tk.Button:
        palette = {
            "primary": (COLORS["primary"], COLORS["primary_text"], COLORS["primary_hover"]),
            "secondary": ("#FFFFFF", COLORS["text"], "#EEE9E0"),
            "danger": (COLORS["danger_bg"], COLORS["danger_text"], "#F7E7E3"),
        }
        background, foreground, active = palette[kind]
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=background,
            fg=foreground,
            activebackground=active,
            activeforeground=foreground,
            borderwidth=1,
            relief="flat",
            highlightbackground=(
                COLORS["danger_border"] if kind == "danger" else COLORS["border"]
            ),
            highlightthickness=1,
            padx=15,
            pady=9,
            cursor="hand2",
            font=(UI_FONT, 9, "bold"),
        )

    def _info_row(self, parent: tk.Widget, label: str, value: tk.StringVar, row: int) -> None:
        if row:
            tk.Frame(parent, height=1, bg="#E4DED4").grid(
                row=row * 2 - 1, column=0, columnspan=2, sticky="ew", pady=14
            )
        tk.Label(
            parent,
            text=label,
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(UI_FONT, 10),
        ).grid(row=row * 2, column=0, sticky="w")
        tk.Label(
            parent,
            textvariable=value,
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=(UI_FONT, 10, "bold"),
            anchor="e",
            justify="right",
            wraplength=570,
        ).grid(row=row * 2, column=1, sticky="e", padx=(25, 0))
        parent.grid_columnconfigure(1, weight=1)

    def _load_configuration(self) -> None:
        try:
            config = starter.load_config()
        except starter.StarterError as exc:
            messagebox.showerror("Configuration error", str(exc), parent=self)
            return
        self.start_time_var.set(str(config["start_time"]))
        self.model_var.set(self.model_label_by_id.get(str(config["model"]), str(config["model"])))
        self.effort_var.set(
            self.effort_label_by_id.get(str(config["effort"]), str(config["effort"]).title())
        )
        self.message_text.delete("1.0", "end")
        self.message_text.insert("1.0", str(config["prompt"]))

    def _settings_from_form(self) -> tuple[str, str, str, str]:
        model_label = self.model_var.get()
        effort_label = self.effort_var.get()
        if model_label not in self.model_by_label:
            raise starter.StarterError("Choose a model")
        if effort_label not in self.effort_by_label:
            raise starter.StarterError("Choose an effort level")
        return (
            self.start_time_var.get().strip(),
            self.model_by_label[model_label],
            self.effort_by_label[effort_label],
            self.message_text.get("1.0", "end").strip(),
        )

    def save_configuration(self, announce: bool = True) -> bool:
        try:
            app_core.save_settings(*self._settings_from_form())
        except (starter.StarterError, OSError) as exc:
            messagebox.showerror("Could not save", str(exc), parent=self)
            return False
        self.refresh_schedule()
        if announce:
            self._toast("Configuration saved.")
        return True

    def start_service(self) -> None:
        if not self.save_configuration(announce=False):
            return
        self._run_operation(
            "Starting automation…",
            app_core.start_automation,
            "Automation started. The timer will continue after this window closes.",
        )

    def stop_service(self) -> None:
        self._run_operation(
            "Stopping automation…",
            app_core.stop_automation,
            "Automation stopped. No future greetings will be sent.",
        )

    def send_test(self) -> None:
        if not self.save_configuration(announce=False):
            return
        if not messagebox.askyesno(
            "Send test greeting",
            "Send the configured message now using your Claude Pro subscription?",
            parent=self,
        ):
            return

        def test_command() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, str(starter.APP_DIR / "starter.py"), "--source", "manual"],
                text=True,
                capture_output=True,
                check=False,
            )

        self._run_operation(
            "Sending test greeting…",
            test_command,
            "Test greeting sent successfully.",
        )

    def _run_operation(self, pending: str, operation: object, success: str) -> None:
        if self.operation_running:
            return
        self.operation_running = True
        self.status_var.set(pending)
        self._set_action_state("disabled")

        def worker() -> None:
            try:
                result = operation()
                if result.returncode != 0:
                    detail = (result.stderr or result.stdout or "Unknown error").strip()
                    raise RuntimeError(detail)
            except Exception as exc:
                self.after(0, lambda: self._finish_operation(error=str(exc)))
            else:
                self.after(0, lambda: self._finish_operation(success=success))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_operation(self, success: str = "", error: str = "") -> None:
        self.operation_running = False
        self._set_action_state("normal")
        self.refresh_schedule()
        self.refresh_service_status()
        self.refresh_activity()
        if error:
            messagebox.showerror("Operation failed", error, parent=self)
        elif success:
            self._toast(success)

    def _set_action_state(self, state: str) -> None:
        for button in (self.save_button, self.test_button, self.start_button, self.stop_button):
            button.configure(state=state)

    def _toast(self, text: str) -> None:
        toast = tk.Toplevel(self)
        toast.overrideredirect(True)
        toast.configure(bg=COLORS["primary"])
        tk.Label(
            toast,
            text=text,
            bg=COLORS["primary"],
            fg="white",
            padx=16,
            pady=10,
            font=(UI_FONT, 9, "bold"),
        ).pack()
        self.update_idletasks()
        x = self.winfo_rootx() + self.winfo_width() - toast.winfo_reqwidth() - 28
        y = self.winfo_rooty() + 28
        toast.geometry(f"+{x}+{y}")
        toast.after(2600, toast.destroy)

    def show_page(self, page_name: str) -> None:
        self.current_page = page_name
        self.pages[page_name].tkraise()
        for key, button in self.nav_buttons.items():
            selected = key == page_name
            button.configure(
                bg=COLORS["selection"] if selected else COLORS["sidebar"],
                fg=COLORS["selection_text"] if selected else COLORS["muted"],
                font=(UI_FONT, 10, "bold" if selected else "normal"),
            )
        if page_name == "activity":
            self.refresh_activity()

    def refresh_schedule(self) -> None:
        try:
            state = app_core.schedule_state(self.start_time_var.get().strip())
        except starter.StarterError:
            return
        for child in self.schedule_slots.winfo_children():
            child.destroy()
        self.slot_labels.clear()
        for slot in state.slots:
            is_next = slot == state.next_slot
            label = tk.Label(
                self.schedule_slots,
                text=slot,
                bg="#E0E6DC" if is_next else "#EEE9E0",
                fg=COLORS["primary"] if is_next else "#70695D",
                padx=11,
                pady=7,
                font=(UI_FONT, 9, "bold" if is_next else "normal"),
            )
            label.pack(side="left", padx=(0, 8))
            self.slot_labels[slot] = label
        day_text = "tomorrow" if state.is_tomorrow else "today"
        self.next_run_var.set(f"Next run {day_text} at {state.next_slot}")

    def refresh_activity(self) -> None:
        events = app_core.read_activity()
        self.activity_tree.delete(*self.activity_tree.get_children())
        for event in events:
            status = "Sent" if event.status == "sent" else event.status.title()
            tag = "" if event.status == "sent" else "failed"
            self.activity_tree.insert(
                "",
                "end",
                values=(
                    event.timestamp.astimezone().strftime("%I:%M:%S %p"),
                    status,
                    event.message or "—",
                    app_core.model_label(event.model) or "—",
                    app_core.effort_label(event.effort).title() if event.effort else "—",
                ),
                tags=(tag,),
            )
        self.activity_summary_var.set(
            f"Today · {len(events)} event{'s' if len(events) != 1 else ''}"
        )
        if events:
            self.empty_activity.place_forget()
        else:
            self.empty_activity.place(relx=0.5, rely=0.5, anchor="center")

    def refresh_service_status(self) -> None:
        try:
            self.timer_active = app_core.timer_is_active()
        except OSError:
            self.timer_active = False
        if self.timer_active:
            self.status_var.set("● Automation running")
            self.status_badge.configure(
                bg=COLORS["success_bg"], fg=COLORS["success_text"]
            )
            self.system_timer_var.set("Active")
        else:
            self.status_var.set("○ Automation stopped")
            self.status_badge.configure(
                bg=COLORS["paused_bg"], fg=COLORS["paused_text"]
            )
            self.system_timer_var.set("Stopped")

    def refresh_auth_status(self) -> None:
        try:
            env = starter.clean_environment()
            claude = starter.find_claude(env)
            status = starter.subscription_status(claude, env)
            self.system_auth_var.set(
                f"{status.get('subscriptionType', '').title()} · claude.ai"
            )
        except starter.StarterError as exc:
            self.system_auth_var.set(f"Attention required · {exc}")

    def refresh_all(self) -> None:
        self.refresh_schedule()
        self.refresh_service_status()
        self.refresh_activity()
        if self.system_auth_var.get().startswith("Checking"):
            self.refresh_auth_status()
        self.after(5000, self.refresh_all)


def main() -> int:
    app = LinenApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
