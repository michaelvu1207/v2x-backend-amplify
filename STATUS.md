# Autonomous run — Tesla-style driver dashboard

**Branch:** `dashboard-hud` (off `scenarios`)
**Started:** 2026-05-19
**Scope:**
1. Fix camera respawn bug (CARLA child-attached respawn uses world-space transform → cumulative drift)
2. Build Tesla Model 3/Y-style dashboard HUD strip below camera viewport
3. Wire all warnings (V2X zone, EVA firetruck, scenario events, scenario verdict) to center stack
4. Remove old popup toasts + speed/gas HUD overlay
5. Add tests where possible (separate dirs so user can delete later)

**Pre-existing work-in-progress carried into this branch (not authored by me this run):**
- `apps/bridge/digital_twin_bridge/carla_connection.py` (map auto-load)
- `apps/bridge/digital_twin_bridge/config.py`
- `apps/bridge/digital_twin_bridge/openscenario_runner.py`
- `apps/bridge/scenarios/firetruck_from_south.xosc`
- `apps/web/src/lib/components/V2xToast.svelte`
- Untracked: `apps/bridge/scenarios/patches/atomic_behaviors.diff`, `apps/bridge/scenes/`, `apps/bridge/snapshots/`, `scripts/wait-for-carla.sh`

I authored earlier today (also pre-existing on this branch):
- `apps/bridge/digital_twin_bridge/camera_streamer.py` — hood-cam coords (driver-seat POV)
- `apps/bridge/digital_twin_bridge/drive_server.py` — hood-cam coords (driver-seat POV) — this file will be further modified for the camera respawn bug

---

## Conventions during this run
- **Commits:** incremental on `dashboard-hud` with clean messages, no AI trailers, never pushed.
- **Tests separate:** any new tests live under `apps/web/tests/dashboard/` and `apps/bridge/tests/dashboard/` — easy to find and delete later.
- **If blocked:** documented in the "Blockers" section below, then I move on.

---

## Blockers & open questions

### Pre-existing svelte-check errors (not caused by this run)
`npm run check` reports **56 errors and 7 warnings** on the clean `dashboard-hud` HEAD before any of my dashboard work. All errors are in `src/routes/drive/+page.svelte` and look like:

```
"Cannot use 'state' as a store. 'state' needs to be an object with
a subscribe method on it."
```

These are Svelte 5 `$state(...)` runes that svelte-check isn't recognizing — likely a project-config / version-sync issue. Verified by `git stash` + re-running check (still 56 errors with my changes hidden), so this is upstream tech debt unrelated to the dashboard work.

This means `npm run check` cannot serve as a clean signal of regression for my changes; I'll diff the post-build error count against this baseline (56) instead and flag if my work introduces any new ones.

---

## Final notes
*(written at the end of the run)*
