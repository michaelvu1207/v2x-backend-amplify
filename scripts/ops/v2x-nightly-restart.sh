#!/usr/bin/env bash
# Nightly preventive restart of the V2X drive stack (guards against slow
# degradation in long-running UE5/CARLA sessions). Skipped if a drive
# session is currently connected.
set -u
if ss -Htn state established '( sport = :8765 )' | grep -q .; then
    echo "nightly-restart: active drive session detected; skipping restart"
    exit 0
fi
echo "nightly-restart: restarting CARLA container and drive service"
docker restart carla-rr-maps
systemctl restart v2x-drive.service
