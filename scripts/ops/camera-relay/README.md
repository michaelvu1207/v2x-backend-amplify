# Richmond Field Station camera relay

This installs MediaMTX **v1.20.1** and four supervised, copy-only H.264 publishers on path-rfs. Each publisher subscribes to `/tmp/camera_demux_ch0.sock` through `ch3`, strips the demux framing, and sends the Annex-B access units to MediaMTX as public path names `ch1` through `ch4`. It never opens another camera RTSP session and does not alter the existing AWS Kinesis Video Streams uploader.

MediaMTX listens only on loopback: RTSP at `127.0.0.1:8554`, low-latency HLS at `127.0.0.1:8888`, and recording playback at `127.0.0.1:9996`. nginx exposes HLS under `/camera/` and archive listing/clips under `/archive/`. WebRTC, RTMP, SRT, MoQ, and the MediaMTX control API are disabled. The adapter and ffmpeg copy the encoded H.264 stream without transcoding.
The production sockets measure 29.97–29.99 access units per second, so the adapter supplies the raw H.264 input to ffmpeg at 30 fps.

Run from the repository checkout on path-rfs:

```sh
sudo scripts/ops/camera-relay/install.sh
```

The installer verifies the pinned linux_amd64 archive SHA-256, creates the unprivileged `v2x-camera` system user, installs configuration and units, and enables `mediamtx.service` plus `v2x-camera-relay@0.service` through `@3.service`. It is safe to rerun after updating the checked-in files.

Recordings are fragmented MP4 under `/var/lib/v2x-camera/recordings/<path>/`. Segments close every 15 minutes and MediaMTX deletes them after 40 hours. At the measured four-camera rate of about 260 GB/day, 40 hours consumes about 433 GB (the operational budget is approximately 430 GB) and leaves headroom on the roughly 620 GB available disk; longer retention requires more disk. Playback is available through `/list?path=ch1&start=<RFC3339>&end=<RFC3339>` and `/get?path=ch1&start=<RFC3339>&duration=<seconds>&format=mp4`. To change retention, edit `recordDeleteAfter` in `mediamtx.yml`, rerun `install.sh`, and restart `mediamtx.service` and the relay units.

Useful checks:

```sh
systemctl is-active mediamtx v2x-camera-relay@{0..3}
ffprobe -v error -rtsp_transport tcp -show_streams rtsp://127.0.0.1:8554/ch1
curl -fsS http://127.0.0.1:8888/ch1/index.m3u8
curl -fsS 'http://127.0.0.1:9996/list?path=ch1'
journalctl -u 'v2x-camera-relay@*' --since '5 minutes ago'
```
