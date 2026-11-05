#!/bin/sh
# Install hermes-time-sense into a Hermes profile home.
#
# Usage:
#   ./install.sh                      # into ~/.hermes
#   ./install.sh --with-soul          # also update SOUL.md (see below)
#   HERMES_HOME=~/.hermes/profiles/x ./install.sh
#
# Copies the plugin into $HERMES_HOME/plugins/time-sense and enables
# it in that profile's config if the `hermes` CLI is available.
# Existing installs are updated in place; last_seen.json is kept.
#
# The ## Time section for SOUL.md is handled in one of two ways:
#   default       printed at the end inside a loud ACTION REQUIRED
#                 block, for you to paste into SOUL.md manually;
#                 SOUL.md itself is never touched.
#   --with-soul   the script does it: the current SOUL.md is first
#                 backed up to SOUL.md.bak-<timestamp>, then the
#                 ## Time section is appended, or replaced in place
#                 if one already exists (idempotent — re-running
#                 never stacks a second copy).
set -eu

WITH_SOUL=0
for arg in "$@"; do
    case "$arg" in
        --with-soul) WITH_SOUL=1 ;;
        *) echo "Unknown argument: $arg (only --with-soul is supported)" >&2; exit 2 ;;
    esac
done

SRC_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
DEST="$HERMES_HOME/plugins/time-sense"
SOUL="$HERMES_HOME/SOUL.md"

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

SECTION_FILE=$(mktemp)
cat > "$SECTION_FILE" <<'SECTION_EOF'
## Time

The [time] line on the current turn is the authoritative "now"; relative dates follow the latest [time] line. A [time-gap] line means the last human interaction was long ago, possibly a new day — reinterpret "yesterday" and "just now" by that gap, not as if they just happened.

Present times in the user's timezone, converting when the source gives enough to convert. An event's date and time come only from fields that describe that event — never from message, record, or retrieval timestamps.

Never guess a weekday: today's is given in the [time] line; for any other date, verify with the system `date` command before stating one, or omit it. Never call data live, current, fresh, or verified unless a tool in this conversation checked it; even a page fetched today may be stale — judge by the published/updated dates the page itself shows.
SECTION_EOF

if [ "$WITH_SOUL" -eq 1 ]; then
    if [ -f "$SOUL" ]; then
        TS=$(date +%Y%m%d-%H%M%S)
        BAK="$SOUL.bak-$TS"
        n=2
        while [ -e "$BAK" ]; do
            BAK="$SOUL.bak-$TS-$n"
            n=$((n + 1))
        done
        cp "$SOUL" "$BAK"
        echo "Backed up existing SOUL.md to $BAK"
        TMP_FILE=$(mktemp)
        awk '/^## Time[[:space:]]*$/ {insec=1; next} insec && /^## / {insec=0} !insec {print}' "$SOUL" > "$TMP_FILE"
        cat "$TMP_FILE" > "$SOUL"
        rm -f "$TMP_FILE"
        if [ -s "$SOUL" ]; then
            # Ensure the file ends with a newline, then a blank separator line.
            if [ "$(tail -c 1 "$SOUL" | wc -l)" -eq 0 ]; then
                echo "" >> "$SOUL"
            fi
            echo "" >> "$SOUL"
        fi
        cat "$SECTION_FILE" >> "$SOUL"
        echo "Updated the ## Time section in $SOUL (appended, or replaced in place if one existed)."
    else
        mkdir -p "$HERMES_HOME"
        cp "$SECTION_FILE" "$SOUL"
        echo "Created $SOUL containing the ## Time section (there was no existing SOUL.md to back up)."
    fi
    echo ""
    echo "Then restart the gateway (or start a new session) so everything loads:"
    echo "  hermes gateway restart"
else
    echo ""
    echo "================================================================"
    echo "  !! ACTION REQUIRED - MANUAL STEP, DO NOT SKIP !!"
    echo ""
    echo "  The install is NOT complete yet. Paste the section between"
    echo "  the BEGIN/END markers below into:"
    echo "    $SOUL"
    echo "  Add it once. If a ## Time section is already in there,"
    echo "  replace it with this version."
    echo "  (Or skip the manual step next time: ./install.sh --with-soul"
    echo "   backs up SOUL.md and does this for you.)"
    echo "================================================================"
    echo "---- BEGIN: paste into SOUL.md ----"
    cat "$SECTION_FILE"
    echo "---- END: paste into SOUL.md ----"
    echo "================================================================"
    echo "  Reminder: without this section in SOUL.md the agent still"
    echo "  sees the [time] lines, but has no standing rule for using"
    echo "  them. After pasting, restart the gateway:"
    echo "    hermes gateway restart"
    echo "================================================================"
fi

rm -f "$SECTION_FILE"
