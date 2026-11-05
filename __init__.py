"""time-sense: give a standalone Hermes agent a sense of time.

A single ``pre_llm_call`` hook. On every LLM call the hook reads the
host's system clock (in code, never via the model) and returns one
context line that Hermes appends to the current user turn:

    [time] 2026-11-05 Thu 08:15 Asia/Shanghai

The line never touches the system prompt, so the byte-stable prompt
prefix (SOUL, auto-loaded skills) and its provider prompt-cache hits
are unaffected; history turns are immutable once written, so
incremental history caching is unaffected too.

When the previous interaction was a while ago -- or on a different
calendar day, the overnight case -- a second line makes the elapsed
time explicit, computed by code rather than left to the model:

    [time-gap] Last interaction was 2026-11-04 Wed 23:40, 8h35m ago. A new day has started.

State is one small file (``last_seen.json`` next to this plugin,
git-ignored): the ISO timestamp of the previous hook call. It
survives context compression and session restarts, which is exactly
where an in-history [time] line would be lost.

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
                gap = "[time-gap] Last interaction was {}, {} ago.".format(
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


# ---------------------------------------------------------------- hook

def _pre_llm_call(**kwargs):
    try:
        now, tz_label = _resolve_now()
    except Exception:
        return None
    context = None
    try:
        prev = _load_prev()
        context = _build_context(now, tz_label, prev, _gap_threshold_seconds())
    except Exception:
        context = "[time] {} {}".format(_format_stamp(now), tz_label)
    try:
        _save_now(now)
    except Exception:
        pass  # losing state only loses the gap line next time
    return {"context": context}


def register(ctx):
    ctx.register_hook("pre_llm_call", _pre_llm_call)
