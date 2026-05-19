# Autonomous run — Tesla-style driver dashboard

**Branch:** `dashboard-hud` (off `scenarios`)
**Started:** 2026-05-19 (~03:00 local)
**Ended:** 2026-05-19 (~03:45 local)
**Scope completed:**
1. Camera respawn world-vs-local transform bug (the broken Camera Settings button)
2. Tesla Model 3/Y-style dashboard HUD strip below camera viewport
3. All warnings (V2X zone, EVA firetruck, scenario verdict) routed to the center stack
4. Old popup toasts + bottom HUD speed/gas overlay removed
5. Regression tests added (separated under `tests/dashboard/` for easy deletion)

---

## Commits on `dashboard-hud` (10 total, oldest first)

| # | Commit | Subject |
|---|--------|---------|
| 1 | `4e52b3e` | Fix hood-cam driver POV and aspect-ratio respawn drift |
| 2 | `5c42c08` | Add regression tests for camera respawn local-transform fix |
| 3 | `d1b04ce` | Set up Tesla cluster palette, web test framework, and run notes |
| 4 | `dc0a43a` | Add instrument cluster components (speed, gear, throttle/brake) |
| 5 | `d199d9b` | Add center stack components (vehicle viz + warning stack) |
| 6 | `f1e4af0` | Add DriverDashboard composition root |
| 7 | `e471e9e` | Wire V2X / EVA / scenario verdict warnings into the dashboard |
| 8 | `37118af` | Strip HUD overlay and remove V2xToast — replaced by DriverDashboard |
| 9 | `8d5557a` | Add Tesla dashboard strip below camera viewport in drive page |

Nothing pushed. Inspect via `git log scenarios..dashboard-hud` and `git diff scenarios..dashboard-hud`.

---

## Test results (all green)

| Suite | Count | Result |
|---|---|---|
| Bridge unit (pytest, `apps/bridge/tests/`) | 44 | All passing — includes 3 new `tests/dashboard/test_camera_respawn.py` |
| Web unit (vitest, `apps/web/tests/dashboard/`) | 77 across 10 files | All passing |
| Production build (`npm run build`) | — | Clean |
| `npm run check` (svelte-check) | 56 errors / 7 warnings | Same as the pre-existing baseline — no new errors from this run |

All test files live under `tests/dashboard/` (web) or `tests/dashboard/` (bridge) so you can `rm -rf` either directory to remove every test from this run without touching unrelated tests.

---

## What you need to visually verify (untestable from code)

The big ones — code can't tell whether these "look right":

1. **Does the dashboard strip render at all?** Drive → expect a 200px-tall dark strip below the camera viewport. Speed numeral big on the left, gear column (`P R N [D]`) to its right, steering degrees below the gear row. Right half: top-down vehicle visualization with the ego car as a light-grey sedan in the middle, nearby traffic as darker grey rectangles, and front wheels of the ego rotating with steering input.
2. **Tesla feel.** Inter Display font, weight 500-600 on the speed. Off-black background (`#0A0A0C`). Active gear letter white, others ~25% opacity. The slim red/green LED strips flank the speed numeral and fill from the bottom as you press the pedals.
3. **Warnings into the center stack.** Drive a firetruck-scenario or place a V2X zone you'll enter. Expect: a card slides down from the top of the center stack, severity-coloured left stripe (red for EVA, amber for V2X warning, blue for info), icon from Lucide, message, optional distance on the right. After 1.5s with no update, the card disappears. If more warnings fire than fit, a `+N more` badge appears below the visible ones.
4. **Hood camera POV.** Press `2` (Hood) — the camera should be inside the cabin at the driver's seat (slightly forward of vehicle center, left-of-center, eye height).
5. **Camera Settings button.** Click `Camera` in the bottom action row, then any aspect ratio or FOV preset. The camera resolution / FOV should change without the camera drifting away from the vehicle. Click the same preset again — no movement. Cycle several presets — still snapped to the active view's offset.

Items 1 and 2 are pure CSS / SVG correctness; if anything looks off, tell me and I can tune in-place.

---

## Untouched: pre-existing WIP carried into this branch

These files were already modified on the `scenarios` branch when I started — left in working tree, **not** included in any commit I made:

```
 M apps/bridge/digital_twin_bridge/carla_connection.py
 M apps/bridge/digital_twin_bridge/config.py
 M apps/bridge/digital_twin_bridge/drive_server.py
 M apps/bridge/digital_twin_bridge/openscenario_runner.py
 M apps/bridge/scenarios/firetruck_from_south.xosc
 M apps/web/src/lib/components/V2xToast.svelte
?? apps/bridge/scenarios/patches/atomic_behaviors.diff
?? apps/bridge/scenes/
?? apps/bridge/snapshots/
?? scripts/wait-for-carla.sh
```

`drive_server.py` has substantial pre-existing changes (dynamic actors / geofence work). My `Fix hood-cam …` commit only touches the two hood-cam / respawn-fix hunks — I did a `git reset --soft HEAD~1` after an initial mistake that bundled all of `drive_server.py`'s WIP with my fix, then re-applied only my hunks and restored the WIP to the working tree. `git show 4e52b3e -- apps/bridge/digital_twin_bridge/drive_server.py` shows 11 inserts / 6 deletes — that's the whole scope of my touches.

---

## Blockers & open questions

### Pre-existing svelte-check errors (not caused by this run)
`npm run check` reports **56 errors and 7 warnings** on the clean `dashboard-hud` HEAD before any of my dashboard work. All errors are in `src/routes/drive/+page.svelte` and look like:

```
"Cannot use 'state' as a store. 'state' needs to be an object with
a subscribe method on it."
```

These are Svelte 5 `$state(...)` runes that svelte-check isn't recognizing — likely a project-config / version-sync issue. Verified by `git stash` + re-running check (still 56 errors with my changes hidden), so this is upstream tech debt unrelated to the dashboard work.

This means `npm run check` cannot serve as a clean signal of regression for my changes; I diffed the post-build error count against this baseline (56) and flagged if my work introduced any new ones. **My work introduced none.**

### Things deferred (per the original plan / per your earlier guidance)
- **Speed limit indicator** — Tesla shows a small `35` circle next to the speed. You answered "skip for now."
- **Battery/range indicator** — Tesla always shows it; not applicable in a sim. Left out.
- **3D Three.js scene** — you picked simple SVG over Three.js; that's what was built.
- **xosc event log items** as warnings — only the verdict is surfaced. Showing every SR stdout line as a warning would be noisy; the live event log in the scenario picker is still the place for those. If you want raw SR events in the center stack, that's a small extension to `warnings.ts`.

### Things I didn't touch but you may want to revisit
- `V2xToast.svelte` (pre-existing WIP). I removed the *usage* from `+page.svelte` but the file is still on disk. Other branches may still reference it — your call whether to delete.
- The pre-existing 56 svelte-check errors are worth chasing in a follow-up. Probably a quick fix once you find the right svelte-kit/tsconfig knob.

---

## Live server state on hand-off

- **CARLA:** `carla-custommaps` container, RFS map loaded, ports 2000-2002 published.
- **Bridge:** `python -m digital_twin_bridge.drive_main`, PID `3411339`, listening on `ws://0.0.0.0:8765`. **Loaded with the camera respawn fix** (started after the fix was applied).
- **Vite dev server:** PID `882069`, listening on `http://0.0.0.0:5173`. HMR has been picking up component changes throughout the run. A hard refresh in the browser pulls the latest.

To verify in the browser: open `http://localhost:5173/drive` (or `http://100.72.252.40:5173/drive` from a tailnet client).

---

## Final notes

- All deps installed (`@fontsource-variable/inter`, `lucide-svelte`, `vitest`, `@testing-library/svelte`, `@testing-library/jest-dom`, `jsdom`). `npm install` confirmed clean.
- Tesla palette + Inter Display + `font-tesla` token added to `src/app.css`. Same tokens in both `:root` (raw CSS variable access) and `@theme` (Tailwind utility access).
- DriverDashboard is props-based (testable); DriverDashboardConnected subscribes to stores and feeds it.
- Sleep-pattern: tasks were committed in logical chunks as they completed, so the `dashboard-hud` branch is a clean linear history of small reviewable diffs.
