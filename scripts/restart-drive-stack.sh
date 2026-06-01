#!/usr/bin/env bash
set -euo pipefail

# Restart the Path PC CARLA simulator container and the drive bridge service.
# Intended to be run by systemd as root, but safe to run manually with sudo.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CARLA_CONTAINER="${CARLA_CONTAINER:-carla-custommaps}"
DRIVE_SERVICE="${DRIVE_SERVICE:-v2x-drive.service}"
WAIT_SCRIPT="${WAIT_SCRIPT:-${REPO_ROOT}/scripts/wait-for-carla.sh}"
CARLA_WAIT_TIMEOUT="${CARLA_WAIT_TIMEOUT:-600}"
CARLA_WAIT_USER="${CARLA_WAIT_USER:-path}"

log() {
    printf '%s %s\n' "$(date -Is)" "$*"
}

if ! command -v docker >/dev/null 2>&1; then
    log "ERROR: docker is not available."
    exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
    log "ERROR: systemctl is not available."
    exit 1
fi

if ! docker inspect "$CARLA_CONTAINER" >/dev/null 2>&1; then
    log "ERROR: CARLA container '$CARLA_CONTAINER' does not exist."
    exit 1
fi

log "Stopping drive service: $DRIVE_SERVICE"
systemctl stop "$DRIVE_SERVICE" || true

# Clean up manually-started bridge processes so the service can bind :8765.
if pgrep -f 'python -m digital_twin_bridge.drive_main' >/dev/null 2>&1; then
    log "Stopping unmanaged drive_main process(es)"
    pkill -TERM -f 'python -m digital_twin_bridge.drive_main' || true
    sleep 3
    pkill -KILL -f 'python -m digital_twin_bridge.drive_main' || true
fi

if docker inspect -f '{{.State.Running}}' "$CARLA_CONTAINER" 2>/dev/null | grep -qx true; then
    log "Restarting CARLA container: $CARLA_CONTAINER"
    docker restart "$CARLA_CONTAINER" >/dev/null
else
    log "Starting CARLA container: $CARLA_CONTAINER"
    docker start "$CARLA_CONTAINER" >/dev/null
fi

log "Waiting for CARLA RPC readiness"
if [ "$(id -u)" -eq 0 ] && id "$CARLA_WAIT_USER" >/dev/null 2>&1; then
    runuser -u "$CARLA_WAIT_USER" -- env \
        CARLA_CONTAINER="$CARLA_CONTAINER" \
        CARLA_WAIT_TIMEOUT="$CARLA_WAIT_TIMEOUT" \
        "$WAIT_SCRIPT"
else
    CARLA_CONTAINER="$CARLA_CONTAINER" \
    CARLA_WAIT_TIMEOUT="$CARLA_WAIT_TIMEOUT" \
    "$WAIT_SCRIPT"
fi

log "Starting drive service: $DRIVE_SERVICE"
systemctl reset-failed "$DRIVE_SERVICE" || true
systemctl start "$DRIVE_SERVICE"

log "Drive stack restart complete"
