#!/bin/sh
# Install hermes-time-sense into a Hermes profile home.
#
# Usage:
#   ./install.sh                      # into ~/.hermes
#   HERMES_HOME=~/.hermes/profiles/x ./install.sh
#
# Copies the plugin into $HERMES_HOME/plugins/time-sense and enables
# it in that profile's config if the `hermes` CLI is available.
# Existing installs are updated in place; last_seen.json is kept.
set -eu

SRC_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
DEST="$HERMES_HOME/plugins/time-sense"

mkdir -p "$DEST"
for f in __init__.py plugin.yaml; do
    cp "$SRC_DIR/$f" "$DEST/$f"
done

echo "Installed plugin files to $DEST"

if command -v hermes >/dev/null 2>&1; then
    hermes plugins enable time-sense || \
        echo "Note: 'hermes plugins enable time-sense' failed; add time-sense to plugins.enabled in $HERMES_HOME/config.yaml manually."
else
    echo "Note: hermes CLI not on PATH; add time-sense to plugins.enabled in $HERMES_HOME/config.yaml manually."
fi

cat <<'EOF'

One static section still belongs in that profile's SOUL.md (add it once;
SOUL.md is loaded whole, no entry marker needed):

  ## Time

  The [time] line on the current turn is the authoritative "now";
  relative dates follow the latest [time] line. A [time-gap] line means
  the last human interaction was long ago, possibly a new day --
  reinterpret "yesterday" and "just now" by that gap, not as if they
  just happened.

  Present times in the user's timezone, converting when the source
  gives enough to convert. An event's date and time come only from
  fields that describe that event -- never from message, record, or
  retrieval timestamps.

  Never guess a weekday: today's is given in the [time] line; for any
  other date, verify with the system `date` command before stating
  one, or omit it. Never call data live, current, fresh, or verified
  unless a tool in this conversation checked it; even a page fetched
  today may be stale -- judge by the published/updated dates the page
  itself shows.

Then restart the gateway (or start a new session) so the plugin loads:

  hermes gateway restart
EOF
