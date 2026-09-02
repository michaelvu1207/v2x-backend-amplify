#!/usr/bin/env bash
LOG=/var/log/v2x-carla-events.log
docker events \
  --filter container=carla-rr-maps \
  --filter event=die \
  --filter event=oom \
  --format '{{.Time}} {{.Action}} exitCode={{index .Actor.Attributes "exitCode"}}' \
| while read -r line; do
    {
      echo "$(date -Is) EVENT: $line"
      echo "---- container log tail at event ----"
      docker logs --tail 120 carla-rr-maps 2>&1
      echo "---- end event ----"
    } >> "$LOG"
  done
