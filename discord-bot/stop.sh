#!/usr/bin/env bash
cd "$(dirname "$0")"
touch .stop
if [ -f supervisor.pid ]; then pid=$(cat supervisor.pid); kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null; rm -f supervisor.pid; fi
pkill -f "node bot.js" 2>/dev/null; rm -f .stop
echo stopped
