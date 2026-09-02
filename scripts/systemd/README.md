# path-rfs systemd units

These tracked definitions supervise the V2X Drive stack from
`/home/path/v2x-drive`.

| Unit | Role |
| --- | --- |
| `v2x-carla-rr.service` | Adopts and supervises the pre-provisioned CARLA 0.10 container `carla-rr-maps` |
| `v2x-drive.service` | Starts `digital_twin_bridge` after CARLA is ready |
| `v2x-cloudflared-drive.service` | Publishes the drive WebSocket tunnel |
| `v2x-drive-link-health.service` / `.timer` | Checks the public drive link every five minutes |
| `v2x-hourly-drive-restart.service` / `.timer` | Restarts CARLA and the drive server at 04:00 local time; the legacy filename is retained for in-place updates |
| `v2x-web.service` | Optional path-rfs Vite development server from `apps/drive-web` |

Perception is not part of this unit set. Install it from the separate
`path2v2x/co-perception` checkout.

## Install

```bash
cd /home/path/v2x-drive
sudo install -m 0644 scripts/systemd/*.service scripts/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now \
  v2x-carla-rr.service \
  v2x-drive.service \
  v2x-cloudflared-drive.service \
  v2x-drive-link-health.timer \
  v2x-hourly-drive-restart.timer
```

The units use absolute repository paths. Reinstall every unit listed in
[`../../docs/deploy-path-rfs.md`](../../docs/deploy-path-rfs.md) if the checkout
moves.

The simulator container must already exist unless an operator explicitly enables
the guarded create/recreate flags in `scripts/restart-drive-stack.sh`. Keep live
credentials and environment overrides under `/etc`; do not add them to this tree.
