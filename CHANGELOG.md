# Changelog

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
