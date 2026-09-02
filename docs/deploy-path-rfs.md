# Deploying V2X Drive on path-rfs

## Production layout

The production checkout is `/home/path/v2x-drive`. The existing CARLA 0.10
container remains `carla-rr-maps`; this deployment does not create, replace, or
reconfigure it. Its Python environment intentionally remains at
`/home/path/V2XCarla/carla-venv-310`.

| Unit | Repository path used |
| --- | --- |
| `v2x-drive.service` | repository root, `scripts/wait-for-carla.sh`, and `scripts/launch-drive.sh` |
| `v2x-drive-watchdog.service` / `.timer` | `scripts/ops/v2x-drive-watchdog.sh` |
| `v2x-nightly-restart.service` / `.timer` | `scripts/ops/v2x-nightly-restart.sh` |
| `v2x-firewall.service` | `scripts/ops/v2x-firewall.sh` |
| `v2x-carla-event-logger.service` | `scripts/ops/v2x-carla-event-logger.sh` |

`v2x-drive-watchdog.timer` runs every two minutes. The nightly timer runs at
04:00 local time and skips its restart while a client is connected to `:8765`.

## Install

Run as root after updating the checkout:

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

The drive WebSocket listens on `:8765`; the firewall blocks direct public
access and nginx publishes it as `wss://drive.path2v2x.net/ws`. Build
`apps/drive-web`, copy its `build/` contents to `/var/www/v2x-drive`, and
supply both `cloudflareDriveWsUrl` and `tailscaleDriveWsUrl` in
`/var/www/v2x-drive/config.json`. The browser does not load a secondary
endpoint overlay.

Perception is installed from the separate `path2v2x/co-perception` checkout;
nginx routes `/perception/ws` to its local socket on `127.0.0.1:8766`.
