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

The raw Richmond Field Station feeds are copied from the demux Unix sockets
into MediaMTX; the relay never opens a second camera RTSP session. The demux
feeds only local consumers, so camera video never leaves path-rfs. Install or
update the relay as root:

```bash
cd /home/path/v2x-drive
scripts/ops/camera-relay/install.sh
```

MediaMTX binds RTSP to `127.0.0.1:8554`, low-latency HLS to
`127.0.0.1:8888`, and recording playback to `127.0.0.1:9996`. nginx publishes
live HLS as `https://<drive-or-twin-host>/camera/ch1/index.m3u8` through `ch4`
and recording playback as `https://<drive-or-twin-host>/archive/`. The
checked-in firewall drops new external connections to all loopback service
ports. Set `liveVideoUrlTemplate` to
`https://drive.path2v2x.net/camera/{camera_id}/index.m3u8` and
`archiveVideoBaseUrl` to `https://drive.path2v2x.net/archive`. Both values are
required; if either is empty, its video card reports `Video source not
configured`.

Both `/etc/nginx/sites-available/v2x-drive-public` and `v2x-twin` proxy
`/archive/` to `http://127.0.0.1:9996/` with buffering disabled. Their CORS
allow-list includes `https://path2v2x.net`, `https://www.path2v2x.net`,
`https://drive.path2v2x.net`, and `https://twin.path2v2x.net`; archive playback
does not use credentialed cookies.

MediaMTX records 15-minute fMP4 segments beneath
`/mnt/archive/v2x-camera/recordings` on the second NVMe and removes them after
72 hours (3 days). Mount the existing ext4 filesystem before running the camera
installer:

```text
UUID=aa97b6ff-ab06-42e5-a597-7613dae0376f /mnt/archive ext4 defaults,nofail,noatime 0 2
```

Create `/mnt/archive`, add that line to `/etc/fstab`, run `mount -a`, then create
the recordings directory owned by `v2x-camera:v2x-camera` with mode `0750`.
The measured four-camera rate is about 260 GB/day, so 72 hours requires about
780 GB. The `v2x-archive-guard.timer` runs every 10 minutes; if free space on
`/mnt/archive` falls below 60 GB, it deletes the oldest `.mp4` segments across
all channels until 80 GB is free. The guard is restricted to the recordings
directory.

Perception is installed from the separate `path2v2x/co-perception` checkout;
nginx routes `/perception/ws` to its local socket on `127.0.0.1:8766`.
