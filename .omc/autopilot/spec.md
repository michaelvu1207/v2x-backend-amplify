# V2X Signal Placer — Spec

## Overview
Add a V2X signal placement system to the driving app, following the same UX pattern as the existing Object Placer. Users can place V2X messages at positions in the CARLA world. When the vehicle drives near a signal, a toast notification appears on screen.

## Requirements

### Backend (drive_server.py on remote server)
1. `DriveSession` gets a `_v2x_signals` list tracking placed signals (id, position, message, signal_type, radius)
2. New WebSocket message types:
   - `place_v2x_signal` → places a signal at vehicle position + forward offset. Fields: `message`, `signal_type` (warning/info/alert), `radius` (trigger distance, default 30m)
   - `remove_v2x_signal` → removes by signal_id
   - `undo_v2x_signal` → removes most recently placed
   - `list_v2x_signals` → returns all placed signals
3. Proximity check in `apply_control()`: after computing telemetry, check distance to all signals. If vehicle is within a signal's radius, include `v2x_alerts` array in the telemetry response with the triggered signal messages.
4. Signals persist in scenario save/load (add to snapshot alongside placed objects).

### Frontend
1. **V2X Signal Placer panel** — toggle with `V` key (like `P` for Object Placer). Contains:
   - Text input for message
   - Signal type selector (Warning / Info / Alert)
   - Radius slider (10-100m, default 30m)
   - "Place Signal" button
   - List of placed signals with remove buttons
   - Undo button
2. **Toast notification system** — top-right overlay showing V2X alerts when vehicle enters a signal's radius. Auto-dismiss after 5 seconds. Color-coded by type (red=warning, blue=info, orange=alert).
3. **driveSocket.ts** — new actions: `placeV2xSignal()`, `removeV2xSignal()`, `undoV2xSignal()`. New store: `v2xSignals` (placed list), `v2xAlerts` (active alerts from telemetry).

## Architecture
- Signals are server-side objects (no CARLA actor needed — just position + metadata)
- Proximity detection happens server-side in the telemetry loop (already runs every frame)
- Frontend only displays what the server tells it
- Same save/load flow as scenarios
