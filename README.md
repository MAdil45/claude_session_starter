# Claude Session Starter

Claude Session Starter is a Linen Minimal desktop application for scheduling a
small Claude greeting through a Claude.ai Pro subscription. It runs the actual
schedule through a user-level systemd timer, so the graphical window can be
closed while the Ubuntu server continues operating 24/7.

## Graphical application

Launch the app from this directory:

```bash
./run-app.sh
```

The launcher uses Ubuntu's system Python/Tk so installed TrueType fonts are
rendered with normal desktop anti-aliasing, including when a Conda environment
is active in the shell.

The application provides three views:

- **Schedule:** choose the daily start time with a constrained 24-hour clock,
  plus the Claude model, effort level, and message. The displayed run times
  update immediately and the next five-hour slot is bold. Save settings, send
  a live test, start automation, or stop it.
- **Activity:** shows every event from the current local day, including the
  send time, status, complete message, model, and effort level.
- **System:** shows Claude subscription authentication, timer state,
  configuration location, and activity-log location.

Supported effort choices are Low, Medium, High, Extra (`xhigh` in Claude CLI),
and Max.

## Starting and stopping

Press **Start automation** in the application. This saves the current settings,
installs the calculated systemd timer, starts it, and adds Claude Session Starter
to the Ubuntu application menu.

Press **Stop** to disable the timer immediately. No future greetings will be
sent until Start automation is pressed again. The equivalent terminal command
is:

```bash
systemctl --user disable --now claude-session-starter.timer
```

## Daily schedule behavior

The chosen time is the start of each new calendar day's schedule. Five-hour
increments are added only while they remain within that day. For example:

```text
01:00 → 06:00 → 11:00 → 16:00 → 21:00 → next day 01:00
```

The server must be awake at the scheduled time. Late catch-up runs are disabled
so a missed event cannot shift the daily anchor.

## Billing safeguards

- Each run requires `authMethod: claude.ai` and a Pro subscription.
- API-key and third-party-provider environment variables are removed.
- The scheduler refuses to send if authentication changes instead of falling
  back to separately billed API usage.
- The selected message, model, and effort are recorded in the local Activity
  log after each attempt.

Disabling usage credits in Claude remains a useful account-level safeguard.

## Server operation

A user-level systemd timer normally runs while the user has an active login
session. For a server that must operate before login or after logout, enable
systemd user lingering once:

```bash
loginctl enable-linger "$USER"
```

Whether this command requires administrator authorization depends on the
server's configuration.

## Tests

Run the complete automated suite with:

```bash
python3 -m unittest -v
```

## Project files

- `app.py`: Linen Minimal Tkinter desktop application.
- `app_core.py`: schedule, activity, configuration, and service-control logic.
- `starter.py`: guarded Claude subscription invocation and event logging.
- `install.py`: systemd timer and desktop-menu installation.
- `config.json`: saved user configuration.
- `run-app.sh`: graphical application launcher.
- `test_app_core.py` and `test_starter.py`: automated coverage.
