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
| `mediamtx.service` / `v2x-camera-relay@.service` | `scripts/ops/camera-relay/` |

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

## Camera relay

The raw Richmond Field Station feeds are copied from the existing demux Unix
sockets into MediaMTX; the relay never opens a second camera RTSP session and
does not change the parallel AWS Kinesis uploader. Install or update it as root:

```bash
cd /home/path/v2x-drive
scripts/ops/camera-relay/install.sh
```

MediaMTX binds RTSP to `127.0.0.1:8554` and low-latency HLS to
`127.0.0.1:8888`. nginx publishes HLS as
`https://<drive-or-twin-host>/camera/ch1/index.m3u8` through `ch4`. The checked-in
firewall also drops new external connections to both loopback service ports.
The dashboard runtime config key `liveVideoUrlTemplate` should be
`https://drive.path2v2x.net/camera/{camera_id}/index.m3u8`; when it is empty the
existing Kinesis browser-session API remains the fallback.

MediaMTX records 15-minute fMP4 segments beneath
`/var/lib/v2x-camera/recordings` and removes them after seven days. Change
`recordDeleteAfter` in `scripts/ops/camera-relay/mediamtx.yml`, rerun the
installer, and restart the MediaMTX and relay units to change retention.

Perception is installed from the separate `path2v2x/co-perception` checkout;
nginx routes `/perception/ws` to its local socket on `127.0.0.1:8766`.
