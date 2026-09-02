# V2X Drive status

## Production

| Area | Current state |
| --- | --- |
| Site | `path2v2x.net`, served by Amplify app `v2x-backend` (`d1ugco1rmb7yjj`) |
| Source | Canonical `path2v2x/v2x-drive`; Amplify mirror `michaelvu1207/v2x-drive-amplify` |
| Host | path-rfs, checkout `/home/path/v2x-drive` |
| Simulator | CARLA 0.10 in Docker container `carla-rr-maps`, ports 2000-2002 |
| Drive server | `digital_twin_bridge`, WebSocket `:8765`; nginx exposes `:443 /ws` |
| Supervision | systemd services plus the drive-link watchdog and a 04:00 local restart |
| Perception | Separate `path2v2x/co-perception` checkout on path-rfs; nginx `/perception/ws` forwards to `127.0.0.1:8766` |

## Repository scope

- `apps/drive-server`: CARLA drive server, scenarios, tests, and the existing twin panel protocol support.
- `apps/drive-web`: production SvelteKit dashboard.
- `apps/dev-console`: local drive API developer console.
- `infra`: live AWS data-plane and Amplify deployment tooling.

The Kinesis/HLS perception implementation formerly copied into this repository is
retired. Perception code and service deployment now come only from
`path2v2x/co-perception`.

The standalone digital twin is maintained in
[`path2v2x/v2x-digital-twin`](https://github.com/path2v2x/v2x-digital-twin).
The CARLA drive server's existing twin messages and dashboard panel remain in
this repository until their separately planned cutover.

## Deployment notes

Live AWS resource names are intentionally retained.
Repository and checkout paths use `v2x-drive`. Before the next path-rfs deploy,
install the tracked units again so their absolute paths resolve to
`/home/path/v2x-drive`; see `docs/deploy-path-rfs.md`.
