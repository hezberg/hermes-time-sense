# Changelog

## 0.2.2 — 2026-11-05

- The recommended SOUL.md text is now a compact `## Time` section
  (README + install.sh), replacing the single line from 0.2.1. Besides
  the `[time]` / `[time-gap]` rules it adds: present times in the
  user's timezone; an event's date/time comes only from fields
  describing that event, never from message/retrieval timestamps;
  never guess a weekday (today's is in the `[time]` line — verify any
  other date with the system `date` command or omit it); never call
  data live/current/verified unless a tool checked it this
  conversation. The section belongs in SOUL.md, which Hermes loads
  whole — the `§` entry delimiter applies only to MEMORY.md/USER.md.

## 0.2.1 — 2026-11-05

- The recommended SOUL.md line (README + install.sh) is shortened to
  two sentences; semantics unchanged: relative dates resolve against
  the latest `[time]` line, and a `[time-gap]` line means the previous
  interaction was long ago. Repository text is English throughout
  (earlier chat-delivered copies were in Chinese — replace the line in
  your SOUL.md with the new one).

## 0.2.0 — 2026-11-05

- **Cron (and other machine turns) no longer reset the human clock.**
  In v0.1.0 every `pre_llm_call` rewrote `last_seen.json`, so a gateway
  running an agent cron job every few minutes kept the timestamp at
  "just now" and the overnight `[time-gap]` line never fired. Now only
  human turns read or write the state file. Machine turns — cron jobs,
  subagents/delegated children, kanban worker subprocesses — still get
  the `[time]` line for their own work, but no gap line and no state
  write. Classification uses Hermes' own signals, verified against
  Hermes source: the agent's `platform` (`"cron"` / `"subagent"`),
  a set `parent_session_id`, session ids starting with `cron_`, and
  the dispatcher's `HERMES_KANBAN_TASK` environment marker. Older
  Hermes versions passing fewer hook arguments degrade to the v0.1
  behaviour rather than to silence.
- The gap line now reads "Last human interaction was …" — that is what
  it measures.

## 0.1.0 — 2026-11-05

- Initial release: `pre_llm_call` hook appending a code-computed
  `[time]` line to every user turn, plus a `[time-gap]` line when the
  previous interaction was over the threshold (default 1h) ago or on
  a different calendar day. State in a git-ignored `last_seen.json`
  beside the plugin, written atomically; the hook never breaks a turn.
