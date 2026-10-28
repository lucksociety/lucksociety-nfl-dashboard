#!/usr/bin/env bash
# Supervisor: restarts the bot if it exits. Logs go to bot.log (the bot redacts any token-like string).
cd "$(dirname "$0")"
while true; do
  node bot.js >> bot.log 2>&1
  code=$?
  echo "$(date -u +%FT%TZ) SUPERVISOR bot exited code=$code; restarting in 10s" >> bot.log
  [ "$code" = "78" ] && sleep 60   # missing token: back off
  [ -f .stop ] && { echo "$(date -u +%FT%TZ) SUPERVISOR stop flag found, exiting" >> bot.log; rm -f .stop; exit 0; }
  sleep 10
done
