#!/usr/bin/env bash
# Watchdog for the V2X drive stack.
# Recovers from the two failure modes observed in production:
#   1. CARLA container crashed/exited      -> docker restart policy handles it,
#      but the drive service stays stuck   -> restart drive service once CARLA is back.
#   2. CARLA process hung (container Up but RPC unresponsive) -> restart container.
set -u
CARLA_PYTHON=/home/path/V2XCarla/carla-venv-310/bin/python
CONTAINER=carla-rr-maps
DRIVE_SERVICE=v2x-drive.service
STATE_FILE=/run/v2x-drive-watchdog.failcount

probe_carla() {
    timeout 20 /usr/sbin/runuser -u path -- "$CARLA_PYTHON" - <<'PY' >/dev/null 2>&1
import carla
c = carla.Client("localhost", 2000)
c.set_timeout(10.0)
c.get_world().get_map()
PY
}

container_running() {
    docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -qx true
}

if probe_carla; then
    echo 0 > "$STATE_FILE"
    # CARLA healthy: is the drive service stuck in the tick-failure loop?
    if systemctl is-active --quiet "$DRIVE_SERVICE"; then
        fails=$(journalctl -u "$DRIVE_SERVICE" --since "-2 minutes" --no-pager 2>/dev/null | grep -c 'tick() failed' || true)
        if [ "${fails:-0}" -ge 3 ]; then
            echo "watchdog: CARLA healthy but $DRIVE_SERVICE has $fails tick failures in 2m -> restarting drive service"
            systemctl restart "$DRIVE_SERVICE"
        fi
    fi
    exit 0
fi

# CARLA probe failed
if ! container_running; then
    # Container down: docker restart policy is bringing it back; nothing to do yet.
    echo "watchdog: CARLA container not running; waiting for docker restart policy"
    exit 0
fi

# Container is Up but RPC unresponsive: tolerate transient stalls (map loads),
# act only after 3 consecutive failed probes (~6 minutes).
count=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
count=$((count + 1))
echo "$count" > "$STATE_FILE"
if [ "$count" -ge 3 ]; then
    echo "watchdog: CARLA unresponsive for $count consecutive checks -> restarting container and drive service"
    docker restart "$CONTAINER"
    systemctl restart "$DRIVE_SERVICE"
    echo 0 > "$STATE_FILE"
else
    echo "watchdog: CARLA probe failed (consecutive: $count/3); waiting"
fi
