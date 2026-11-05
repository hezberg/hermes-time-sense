"""time-sense: give a standalone Hermes agent a sense of time.

A single ``pre_llm_call`` hook. On every LLM call the hook reads the
host's system clock (in code, never via the model) and returns one
context line that Hermes appends to the current user turn:

    [time] 2026-11-05 Thu 08:15 Asia/Shanghai

The line never touches the system prompt, so the byte-stable prompt
prefix (SOUL, auto-loaded skills) and its provider prompt-cache hits
are unaffected; history turns are immutable once written, so
incremental history caching is unaffected too.

When the previous human interaction was a while ago -- or on a
different calendar day, the overnight case -- a second line makes
the elapsed time explicit, computed by code rather than left to
the model:

    [time-gap] Last human interaction was 2026-11-04 Wed 23:40, 8h35m ago. A new day has started.

State is one small file (``last_seen.json`` next to this plugin,
git-ignored): the ISO timestamp of the last *human* interaction.
It survives context compression and session restarts, which is
exactly where an in-history [time] line would be lost.

Only human turns read or write that file. Machine-initiated turns
-- cron jobs, subagents, kanban workers -- still receive the
``[time]`` line (their own work often needs the date), but they
never touch the human timestamp: a gateway with a cron job every
few minutes would otherwise keep resetting "last interaction" to
"just now", and the overnight gap would never fire. How a turn is
classified is documented at ``_is_human_turn`` below; the signals
are Hermes' own (the ``platform`` the agent was constructed with,
its session id, its parent session, and the dispatcher's
environment marker), verified against Hermes source.

Configuration is by environment only, both optional:

    HERMES_TIME_TZ           IANA zone name, e.g. Asia/Shanghai.
                             Default: the host's local timezone.
    HERMES_TIME_GAP_SECONDS  Minimum gap that triggers [time-gap].
                             Default: 3600. A calendar-day change
                             always triggers it, however short.

The hook must never break a turn: every failure path returns the
plain [time] line, or None.
"""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except Exception:  # very old Python; plugin degrades to local time
    ZoneInfo = None

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DEFAULT_GAP_SECONDS = 3600
_STATE_NAME = "last_seen.json"


# ---------------------------------------------------------------- time source

def _resolve_now():
    """Return (aware datetime, timezone label) from the system clock.

    The instant always comes from the host OS wall clock; a configured
    zone only changes how that instant is rendered.
    """
    tz_name = os.environ.get("HERMES_TIME_TZ") or ""
    if tz_name and ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(tz_name)), tz_name
        except Exception:
            pass  # bad zone name: fall through to local time
    now = datetime.now().astimezone()
    label = tz_name or (now.tzname() or "local")
    return now, label


def _gap_threshold_seconds():
    raw = os.environ.get("HERMES_TIME_GAP_SECONDS") or ""
    try:
        value = int(raw)
        return value if value >= 0 else _DEFAULT_GAP_SECONDS
    except Exception:
        return _DEFAULT_GAP_SECONDS


# ---------------------------------------------------------------- formatting

def _format_stamp(now):
    """'2026-11-05 Thu 08:15' -- weekday spelled out by code."""
    return "{} {} {}".format(
        now.strftime("%Y-%m-%d"),
        _WEEKDAYS[now.weekday()],
        now.strftime("%H:%M"),
    )


def _format_elapsed(delta):
    """timedelta -> '8h35m' / '2d 3h04m' / '12m'. Code-rendered, minute floor."""
    total_minutes = int(delta.total_seconds() // 60)
    days, rem = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(rem, 60)
    if days:
        return "{}d {}h{:02d}m".format(days, hours, minutes)
    if hours:
        return "{}h{:02d}m".format(hours, minutes)
    return "{}m".format(minutes)


def _build_context(now, tz_label, prev, gap_threshold_seconds):
    lines = ["[time] {} {}".format(_format_stamp(now), tz_label)]
    if prev is not None:
        try:
            delta = now - prev
            day_changed = prev.date() != now.date()
            if delta >= timedelta(seconds=gap_threshold_seconds) or (
                day_changed and delta.total_seconds() >= 0
            ):
                gap = "[time-gap] Last human interaction was {}, {} ago.".format(
                    _format_stamp(prev), _format_elapsed(delta)
                )
                if day_changed:
                    gap += " A new day has started."
                lines.append(gap)
        except Exception:
            pass  # a broken comparison must not lose the [time] line
    return "\n".join(lines)


# ---------------------------------------------------------------- state

def _state_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), _STATE_NAME)


def _load_prev(path=None):
    try:
        with open(path or _state_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        prev = datetime.fromisoformat(data["last_seen"])
        if prev.tzinfo is None:
            prev = prev.replace(tzinfo=timezone.utc)
        return prev
    except Exception:
        return None


def _save_now(now, path=None):
    """Atomic write (temp file + rename) so concurrent calls can't tear it."""
    target = path or _state_path()
    directory = os.path.dirname(target) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".last_seen.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"last_seen": now.isoformat()}, fh)
        os.replace(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass


# ---------------------------------------------------------------- classification

# Platforms whose turns are machine-initiated by construction.
# Verified against Hermes source: cron/scheduler.py builds its agent
# with platform="cron"; delegated children run as platform="subagent".
_MACHINE_PLATFORMS = frozenset({"cron", "subagent"})


def _is_human_turn(kwargs):
    """True unless the turn is provably machine-initiated.

    ``pre_llm_call`` receives (agent/turn_context.py, via
    hermes_cli.lifecycle.invoke_hook): session_id, task_id, turn_id,
    user_message, conversation_history, is_first_turn, model,
    platform, parent_session_id, sender_id. Machine signals, any
    one of which is decisive:

    - platform is "cron" or "subagent" (see above);
    - parent_session_id is set -- a delegated child, not a person;
    - session_id starts with "cron_" -- cron sessions are named
      cron_<job_id>_<timestamp> by cron/scheduler.py;
    - HERMES_KANBAN_TASK is in the process environment -- the
      kanban dispatcher sets it in the worker subprocess it spawns
      (hermes_cli/kanban_db_dispatch.py), whose platform is "cli"
      and would otherwise look human.

    Everything else -- cli, tui, feishu/lark, telegram, api, ... --
    counts as human. Older Hermes versions that pass fewer kwargs
    degrade to the v0.1 behaviour (every turn counts), never to
    silence: a missing signal must not hide a real human gap.
    """
    try:
        platform = str(kwargs.get("platform") or "").strip().lower()
        if platform in _MACHINE_PLATFORMS:
            return False
        if str(kwargs.get("parent_session_id") or "").strip():
            return False
        session_id = str(kwargs.get("session_id") or "")
        if session_id.startswith("cron_"):
            return False
        if os.environ.get("HERMES_KANBAN_TASK"):
            return False
    except Exception:
        pass  # classification trouble must not hide a human turn
    return True


# ---------------------------------------------------------------- hook

def _pre_llm_call(**kwargs):
    try:
        now, tz_label = _resolve_now()
    except Exception:
        return None
    time_line = "[time] {} {}".format(_format_stamp(now), tz_label)
    if not _is_human_turn(kwargs):
        # Machine turns (cron, subagents, kanban workers) get the
        # time line for their own work, but never read or write the
        # human last-seen state, and never see a [time-gap] line --
        # "last human interaction" is not a fact about them.
        return {"context": time_line}
    context = None
    try:
        prev = _load_prev()
        context = _build_context(now, tz_label, prev, _gap_threshold_seconds())
    except Exception:
        context = time_line
    try:
        _save_now(now)
    except Exception:
        pass  # losing state only loses the gap line next time
    return {"context": context}


def register(ctx):
    ctx.register_hook("pre_llm_call", _pre_llm_call)
