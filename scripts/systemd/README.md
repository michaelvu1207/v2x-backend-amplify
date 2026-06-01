# Path PC Systemd Services

These units keep the Path PC drive stack alive across boot and process crashes.

- `carla-custommaps` is the CARLA Docker container. Set Docker restart policy with:
  `docker update --restart unless-stopped carla-custommaps`
- `v2x-drive.service` runs `scripts/launch-drive.sh` after Docker and CARLA are reachable.
- `scripts/wait-for-carla.sh` is used by `v2x-drive.service` to wait for the existing CARLA container and RPC server.
- `v2x-cloudflared-drive.service` runs the current quick Cloudflare tunnel command for `localhost:8765`.
- `v2x-hourly-drive-restart.timer` runs `scripts/restart-drive-stack.sh` at the top of each hour.

Install on the Path PC:

```bash
sudo install -m 0644 scripts/systemd/v2x-drive.service /etc/systemd/system/v2x-drive.service
sudo install -m 0644 scripts/systemd/v2x-cloudflared-drive.service /etc/systemd/system/v2x-cloudflared-drive.service
sudo install -m 0644 scripts/systemd/v2x-hourly-drive-restart.service /etc/systemd/system/v2x-hourly-drive-restart.service
sudo install -m 0644 scripts/systemd/v2x-hourly-drive-restart.timer /etc/systemd/system/v2x-hourly-drive-restart.timer
sudo systemctl daemon-reload
docker update --restart unless-stopped carla-custommaps
sudo systemctl enable --now v2x-drive.service v2x-cloudflared-drive.service v2x-hourly-drive-restart.timer
```

The Cloudflare unit uses an account-less quick tunnel. It restarts automatically, but Cloudflare can assign a new `trycloudflare.com` URL after reboot or restart. A stable public URL requires a named Cloudflare tunnel and hostname.
