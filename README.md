# hermes-time-sense

A tiny standalone plugin that gives a Hermes agent a sense of time. No framework, no profiles of its own — it works with a plain Hermes install.

## What it does

On every LLM call, a `pre_llm_call` hook reads the host system clock in code and appends one line to the current user turn:

```
[time] 2026-11-05 Thu 08:15 Asia/Shanghai
```

If the previous human interaction was a while ago — or on a different calendar day, e.g. you arranged work at night and resume the conversation the next morning — a second line makes the elapsed time explicit:

```
[time-gap] Last human interaction was 2026-11-04 Wed 23:40, 8h35m ago. A new day has started.
```

Design points:

- **Placement is the whole design.** The context slot rides the current user turn; it never touches the system prompt. The prompt prefix (SOUL, auto-loaded skills) stays byte-stable, so provider prompt-prefix caching is unaffected, and immutable history turns keep incremental history caching intact. Cost is ~20 tokens per turn.
- **Weekday and elapsed time are computed by code**, never derived by the model (models derive weekday from date unreliably, and arithmetic on elapsed time likewise).
- **The gap survives compression and restarts.** The previous timestamp lives in a small state file (`last_seen.json` next to the plugin), not in the conversation history that compression can summarise away.
- **Only human turns move the human clock.** Cron jobs, subagents and kanban workers also trigger `pre_llm_call` — on a busy gateway, a cron job every few minutes would keep resetting "last interaction" to "just now" and the overnight gap would never fire. Machine turns still receive the `[time]` line for their own work, but they never read or write the human timestamp and never get a `[time-gap]` line. Classification uses Hermes' own signals: the agent's `platform` (`cron` / `subagent`), a set `parent_session_id`, session ids starting with `cron_`, and the dispatcher's `HERMES_KANBAN_TASK` environment marker.
- **It never breaks a turn.** Every failure path returns the plain `[time]` line, or nothing.
- The hook is passive: it fires when you send a message. It does not wake the agent up in the morning — that is a cron/scheduler's job.

## Install

```bash
git clone https://github.com/hezberg/hermes-time-sense.git ~/.hermes/plugins/time-sense
hermes plugins enable time-sense
hermes gateway restart
```

Or clone anywhere and run `./install.sh` (respects `HERMES_HOME`, so it also works for a named profile: `HERMES_HOME=~/.hermes/profiles/<name> ./install.sh`). Enablement is per profile — install it into each profile home that should have time sense.

One static section belongs in that profile's `SOUL.md` (static text lives in the cached prefix; it costs nothing per turn). Either let the script do it — `./install.sh --with-soul` backs the current SOUL.md up to `SOUL.md.bak-<timestamp>` first, then appends the section or replaces an existing `## Time` section in place (idempotent) — or paste it manually; in manual mode the script never touches SOUL.md and prints the section inside a loud ACTION REQUIRED block so it is hard to miss. SOUL.md is loaded whole — no special entry marker is needed, unlike MEMORY.md/USER.md whose entries are delimited by a lone `§` line:

```markdown
## Time

The [time] line on the current turn is the authoritative "now"; relative dates follow the latest [time] line. A [time-gap] line means the last human interaction was long ago, possibly a new day — reinterpret "yesterday" and "just now" by that gap, not as if they just happened.

Present times in the user's timezone, converting when the source gives enough to convert. An event's date and time come only from fields that describe that event — never from message, record, or retrieval timestamps.

Never guess a weekday: today's is given in the [time] line; for any other date, verify with the system `date` command before stating one, or omit it. Never call data live, current, fresh, or verified unless a tool in this conversation checked it; even a page fetched today may be stale — judge by the published/updated dates the page itself shows.
```

## Configuration

Environment only, both optional:

| Variable | Default | Meaning |
|---|---|---|
| `HERMES_TIME_TZ` | host local timezone | IANA zone name to render in, e.g. `Asia/Shanghai`. Set it when the host's own timezone is wrong or unset (containers, VMs). |
| `HERMES_TIME_GAP_SECONDS` | `3600` | Minimum gap that triggers the `[time-gap]` line. A calendar-day change always triggers it, however short. |

The time itself comes from the host OS wall clock — the same clock `date` shows. If it is wrong, the plugin is wrong; check the host's clock/timezone before debugging the plugin.

## Verify

1. Ask the agent: "What time is it now? What day of the week? What date is tomorrow?" — answers should match `date "+%F %a %T %Z"` on the host.
2. Leave the conversation for over an hour (or set `HERMES_TIME_GAP_SECONDS=0`), then send any message and ask how long since the last interaction — the `[time-gap]` line should have been attached and the answer should use it.
3. Overnight test: arrange something in the evening, resume in the morning with just "how did it go?" — the agent should recognise it is a new day before reporting.

## Uninstall

```bash
hermes plugins disable time-sense   # or remove it from plugins.enabled
rm -rf ~/.hermes/plugins/time-sense
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## License

MIT
