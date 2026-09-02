# Deploying V2X Drive on path-rfs

## Checkout convention

Keep the production checkout at:

```text
/home/path/v2x-drive
```

The shell launchers derive the repository root from their own location. The
systemd units use absolute paths so startup does not depend on a login shell or
its current directory.

## Units with checkout paths

Reinstall these units whenever the checkout moves:

| Unit | Repository path used |
| --- | --- |
| `v2x-carla-rr.service` | `scripts/run-carla-rr.sh` |
| `v2x-cloudflared-drive.service` | `scripts/launch-cloudflared-drive-tunnel.sh` |
| `v2x-drive-link-health.service` | repository root and `scripts/check-drive-frontend-link.sh` / `scripts/publish-drive-tunnel-config.sh` |
| `v2x-drive.service` | repository root and `scripts/wait-for-carla.sh` / `scripts/launch-drive.sh` |
| `v2x-hourly-drive-restart.service` | repository root and `scripts/restart-drive-stack.sh` / `scripts/publish-drive-tunnel-config.sh` |
| `v2x-web.service` | `apps/drive-web` |

Install the tracked definitions and reload systemd:

```bash
cd /home/path/v2x-drive
sudo install -m 0644 scripts/systemd/*.service scripts/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

The legacy unit filename `v2x-hourly-drive-restart.timer` is retained so an
existing installation updates in place; its tracked schedule is 04:00 local
time, not hourly.

The drive WebSocket listens on `:8765`. nginx owns public TLS and routes `/ws` to
that local socket. Perception is installed from the separate
`path2v2x/co-perception` checkout; nginx routes `/perception/ws` to its local
socket on `127.0.0.1:8766`.
