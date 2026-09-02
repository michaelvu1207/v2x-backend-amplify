"""
Entry point for the Digital Twin Bridge.

Run with:  python -m digital_twin_bridge

This delegates to the unified server in drive_main.py, which combines
the drive WebSocket server with V2X observation (object spawning,
state publishing, map export).
"""

import asyncio

from digital_twin_bridge.drive_main import main

if __name__ == "__main__":
    asyncio.run(main())
