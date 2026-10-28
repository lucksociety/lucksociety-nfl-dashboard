#!/usr/bin/env bash
# Start the bot in the background under the restart loop. Needs DISCORD_BOT_TOKEN in the environment.
cd "$(dirname "$0")"
if [ -f supervisor.pid ] && kill -0 "$(cat supervisor.pid)" 2>/dev/null; then echo "already running (supervisor pid $(cat supervisor.pid))"; exit 0; fi
[ -z "$DISCORD_BOT_TOKEN" ] && { echo "DISCORD_BOT_TOKEN is not set" >&2; exit 1; }
[ -d node_modules ] || npm install --omit=dev --silent
rm -f .stop
setsid nohup ./run-loop.sh > /dev/null 2>&1 < /dev/null &
echo $! > supervisor.pid
echo "started (supervisor pid $(cat supervisor.pid)); logs: $(pwd)/bot.log"
