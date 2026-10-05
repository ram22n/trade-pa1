#!/bin/bash
# Wrapper: keeps Mac awake while trading and alerts on crash

DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$DIR/.venv/bin/python"
SCRIPT="$DIR/scripts/run_live.py"
LOG="$DIR/reports/live_$(date +%Y%m%d).log"

mkdir -p "$DIR/reports"

notify() {
    osascript -e "display notification \"$1\" with title \"Trade Bot\""
}

echo "=== Trading session started $(date) ===" >> "$LOG"
notify "Trading bot started"

# caffeinate -s keeps the Mac awake even with lid closed (AC power only)
caffeinate -s -w $$ &
CAFF_PID=$!

cd "$DIR" && PYTHONPATH="$DIR" "$PYTHON" "$SCRIPT" >> "$LOG" 2>&1
EXIT_CODE=$?

kill $CAFF_PID 2>/dev/null

if [ $EXIT_CODE -ne 0 ]; then
    notify "CRASH — exit code $EXIT_CODE — check reports/live_$(date +%Y%m%d).log"
    echo "=== CRASHED with exit code $EXIT_CODE at $(date) ===" >> "$LOG"
else
    notify "Trading session ended cleanly"
    echo "=== Session ended cleanly at $(date) ===" >> "$LOG"
fi
