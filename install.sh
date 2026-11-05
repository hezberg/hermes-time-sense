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

One static line still belongs in that profile's SOUL.md (add it once):

  Relative dates follow the latest [time] line. A [time-gap] line means
  the last human interaction was long ago, possibly a new day -- never
  treat it as just now.

Then restart the gateway (or start a new session) so the plugin loads:

  hermes gateway restart
EOF
