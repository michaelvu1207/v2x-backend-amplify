# V2X Drive

V2X Drive is the CARLA 0.10 driving and V2X dashboard used at Richmond Field Station.
The canonical repository is [`path2v2x/v2x-drive`](https://github.com/path2v2x/v2x-drive).

## Components

| Path | Purpose |
| --- | --- |
| `apps/drive-server` | Python `digital_twin_bridge` WebSocket drive server and CARLA integration |
| `apps/drive-web` | SvelteKit dashboard served at [path2v2x.net](https://path2v2x.net) |
| `apps/dev-console` | Local developer console for the drive WebSocket API |
| `infra/aws-cli` | AWS ingest/read API, state, and video-stream provisioning |
| `infra/amplify` | Amplify hosting and runtime configuration |

## Runtime on path-rfs

The production checkout convention is `/home/path/v2x-drive`. CARLA runs in the
`carla-rr-maps` Docker container. The drive server connects to CARLA on ports
2000-2002 and listens for WebSocket clients on `:8765`; nginx exposes that socket
at `wss://<host>/ws` on `:443`.

systemd supervises CARLA, the drive server, the drive tunnel, and the drive-link
watchdog. The tracked restart timer runs the CARLA/drive restart at 04:00 local
time. See [`docs/deploy-path-rfs.md`](docs/deploy-path-rfs.md) for checkout and
unit path conventions.

## Web hosting

AWS Amplify app `v2x-backend` (app ID `d1ugco1rmb7yjj`) serves
[path2v2x.net](https://path2v2x.net). That live AWS name is intentionally
unchanged. Amplify follows the `main` branch of the fast-forward mirror
[`michaelvu1207/v2x-drive-amplify`](https://github.com/michaelvu1207/v2x-drive-amplify),
which mirrors canonical `path2v2x/v2x-drive`.

## Perception stream interface

Perception is owned by the sibling
[`path2v2x/co-perception`](https://github.com/path2v2x/co-perception) repository
and runs on path-rfs from the local camera sockets. There is no perception app or
perception service definition in this repository.

The dashboard retains the runtime settings `perceptionStreamUrls`,
`perceptionStreamBaseUrl`, and `perceptionStreamPathTemplate` for its annotated
camera feeds. The producer's public stream is
`wss://<host>/perception/ws`. Each binary WebSocket message is one JPEG frame
prefixed by a single channel byte. nginx routes `/perception/ws` to
`127.0.0.1:8766` on path-rfs. Deployment configuration must point the dashboard's
perception stream settings at endpoints produced by `co-perception`.

Live and archived raw video are served locally from path-rfs by the copy-only
MediaMTX relay in `scripts/ops/camera-relay`. Public paths `ch1` through `ch4`
are available as low-latency HLS under
`https://drive.path2v2x.net/camera/`, while the Timeline reads the local
40-hour recording archive under `https://drive.path2v2x.net/archive/`. Set
`liveVideoUrlTemplate` to
`https://drive.path2v2x.net/camera/{camera_id}/index.m3u8` and
`archiveVideoBaseUrl` to `https://drive.path2v2x.net/archive`. Both values are
required for raw video; an empty value makes the corresponding card report
`Video source not configured`. Camera video never leaves path-rfs.

## Local development

```bash
make drive-web-install
make drive-web-dev
```

Run the drive server without CARLA:

```bash
make drive-server-install
make drive-server-dry-run
```

Run the developer console:

```bash
cd apps/dev-console
npm ci
npm run dev
```

To run against CARLA, activate a compatible CARLA Python environment and use:

```bash
./scripts/launch-drive.sh
```

## Related repositories

- [`path2v2x/v2x-digital-twin`](https://github.com/path2v2x/v2x-digital-twin) — standalone digital twin
- [`path2v2x/co-perception`](https://github.com/path2v2x/co-perception) — production multi-camera perception
