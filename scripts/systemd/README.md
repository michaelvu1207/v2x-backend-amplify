# path-rfs systemd units

These files are the tracked definitions for the production V2X Drive stack in
`/home/path/v2x-drive`.

| Unit | Role |
| --- | --- |
| `v2x-drive.service` | Waits for the existing `carla-rr-maps` container, then runs `digital_twin_bridge` on `:8765` |
| `v2x-drive-watchdog.service` / `.timer` | Probes CARLA every two minutes and recovers a hung simulator or drive process |
| `v2x-nightly-restart.service` / `.timer` | Restarts CARLA and the drive service at 04:00 unless a drive session is active |
| `v2x-firewall.service` | Keeps CARLA, drive, and twin backend ports off the public interface |
| `v2x-carla-event-logger.service` | Records CARLA container exit and OOM events |

The CARLA 0.10 container is provisioned separately and is not managed by a
tracked systemd service. Perception is also separate. The production CARLA
Python environment intentionally remains at
`/home/path/V2XCarla/carla-venv-310`; moving the repository does not move or
rebuild that environment.

## Install

Run as root:

```bash
cd /home/path/v2x-drive
install -m 0644 scripts/systemd/* /etc/systemd/system/
chmod +x scripts/ops/*.sh
systemctl daemon-reload
systemctl enable --now \
  v2x-drive.service \
  v2x-drive-watchdog.timer \
  v2x-nightly-restart.timer \
  v2x-firewall.service \
  v2x-carla-event-logger.service
```

The units and operations scripts use absolute paths under
`/home/path/v2x-drive`. Reinstall them after changing the checkout location.
Live credentials and environment overrides belong outside the repository.
