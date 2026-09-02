# Amplify hosting

The SvelteKit dashboard in `apps/drive-web` is built with `buildspec.yml` and
served at `path2v2x.net` by Amplify app `v2x-backend` (ID
`d1ugco1rmb7yjj`). The app name is a live AWS identifier and remains unchanged.

Production follows the `main` branch of the owner-controlled fast-forward mirror
`michaelvu1207/v2x-drive-amplify`. The workflow in that mirror fetches canonical
`path2v2x/v2x-drive` and refuses to rewrite a diverged mirror.

## Build configuration

The buildspec uses `appRoot: apps/drive-web`, runs `npm ci` and `npm run build`,
and writes runtime configuration into the static build output. The default API is
`https://w0j9m7dgpg.execute-api.us-west-1.amazonaws.com`.

The dashboard's annotated-camera settings (`PERCEPTION_STREAM_URLS`,
`PERCEPTION_STREAM_BASE_URL`, and `PERCEPTION_STREAM_PATH_TEMPLATE`) describe
feeds produced by the separate `path2v2x/co-perception` deployment on path-rfs.
That producer exposes binary JPEG frames, each prefixed by one channel byte, at
`wss://<host>/perception/ws`; nginx forwards `/perception/ws` to
`127.0.0.1:8766`.

## Deployment helpers

Run plans before applying changes:

```bash
cd /home/path/v2x-drive/infra/amplify
./deploy.sh
./reconcile-repository.sh
```

`deploy.sh` provisions or updates the live Amplify app. Repository reconciliation
is separately gated because changing the connected repository requires fresh
GitHub authorization. Recovery snapshots default to `/home/path/v2x-drive-backups`.
Never place repository tokens or AWS credentials in this tree.
