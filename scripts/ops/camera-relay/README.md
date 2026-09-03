# Richmond Field Station camera relay

This installs MediaMTX **v1.20.1** and four supervised, copy-only H.264 publishers on path-rfs. Each publisher subscribes to `/tmp/camera_demux_ch0.sock` through `ch3`, strips the demux framing, and sends the Annex-B access units to MediaMTX as public path names `ch1` through `ch4`. It never opens another camera RTSP session. Camera video remains on path-rfs; the demux feeds only local perception, relay, and recording consumers.

MediaMTX listens only on loopback: RTSP at `127.0.0.1:8554`, low-latency HLS at `127.0.0.1:8888`, and recording playback at `127.0.0.1:9996`. nginx exposes HLS under `/camera/` and archive listing/clips under `/archive/`. WebRTC, RTMP, SRT, MoQ, and the MediaMTX control API are disabled. The adapter and ffmpeg copy the encoded H.264 stream without transcoding.
The production sockets measure 29.97–29.99 access units per second, so the adapter supplies the raw H.264 input to ffmpeg at 30 fps.

Run from the repository checkout on path-rfs:

```sh
sudo scripts/ops/camera-relay/install.sh
```

The installer verifies the pinned linux_amd64 archive SHA-256, creates the unprivileged `v2x-camera` system user, installs configuration and units, and enables `mediamtx.service`, `v2x-camera-relay@0.service` through `@3.service`, and `v2x-archive-guard.timer`. It requires the archive volume to be mounted at `/mnt/archive` and is safe to rerun after updating the checked-in files.

Recordings are fragmented MP4 under `/mnt/archive/v2x-camera/recordings/<path>/` on the second NVMe. Segments close every 15 minutes and MediaMTX deletes them after 72 hours (3 days). At the measured four-camera rate of about 260 GB/day, 72 hours consumes about 780 GB. Every 10 minutes the archive guard checks the `/mnt/archive` filesystem; if free space falls below 60 GB, it removes the oldest `.mp4` segments across all channels until at least 80 GB is free. It never removes files outside the recordings directory. Playback is available through `/list?path=ch1&start=<RFC3339>&end=<RFC3339>` and `/get?path=ch1&start=<RFC3339>&duration=<seconds>&format=mp4`.

Useful checks:

```sh
systemctl is-active mediamtx v2x-camera-relay@{0..3} v2x-archive-guard.timer
ffprobe -v error -rtsp_transport tcp -show_streams rtsp://127.0.0.1:8554/ch1
curl -fsS http://127.0.0.1:8888/ch1/index.m3u8
curl -fsS 'http://127.0.0.1:9996/list?path=ch1'
journalctl -t v2x-archive-guard --since '15 minutes ago'
journalctl -u 'v2x-camera-relay@*' --since '5 minutes ago'
```
