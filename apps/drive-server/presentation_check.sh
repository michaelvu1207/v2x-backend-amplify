#!/bin/bash
# V2X Digital Twin — Pre-Presentation Checklist
# Run this before any demo to verify everything works.
set -euo pipefail

echo ""
echo "=== V2X Digital Twin — Pre-Presentation Check ==="
echo ""

PASS=0
FAIL=0

check() {
    local label="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  [PASS] $label"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $label"
        FAIL=$((FAIL + 1))
    fi
}

# 1. CARLA running?
check "CARLA is running on port 2000" \
    python3 -c "import carla; c=carla.Client('localhost',2000); c.set_timeout(3); c.get_world()"

# 2. Python venv has dependencies?
check "Python venv has websockets" \
    python3 -c "import websockets"

check "Python venv has numpy" \
    python3 -c "import numpy"

check "Python venv has PIL" \
    python3 -c "from PIL import Image"

# 3. AWS credentials valid?
check "AWS credentials valid" \
    aws sts get-caller-identity --profile Path-Emerging-Dev-147229569658

# 4. Bridge modules importable?
check "drive_server module imports OK" \
    python3 -c "from digital_twin_bridge.drive_server import DriveSession"

check "scene_reconstructor module imports OK" \
    python3 -c "from digital_twin_bridge.scene_reconstructor import SceneReconstructor"

check "camera_streamer module imports OK" \
    python3 -c "from digital_twin_bridge.camera_streamer import compute_camera_transform"

check "session_recorder module imports OK" \
    python3 -c "from digital_twin_bridge.session_recorder import SessionRecorder"

# 5. Unit tests pass?
check "Unit tests pass (33 tests)" \
    python3 -m pytest tests/ -m unit -q --tb=no

# 6. Frontend build exists?
check "Frontend build exists" \
    test -f ../web/build/index.html

echo ""
echo "──────────────────────────────────"
echo "  PASS: $PASS  |  FAIL: $FAIL"
echo "──────────────────────────────────"

if [ "$FAIL" -eq 0 ]; then
    echo "  ALL CHECKS PASSED — ready to demo!"
else
    echo "  FIX THE FAILURES ABOVE before presenting."
    exit 1
fi
echo ""
