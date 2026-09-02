#!/usr/bin/env python3
"""Publish H.264 access units from a camera demux socket to MediaMTX."""

from __future__ import annotations

import argparse
import logging
import os
import queue
import signal
import socket
import struct
import subprocess
import threading
import time
from dataclasses import dataclass

MSG_VIDEO = 1
MSG_SESSION_RESET = 4
HEADER_SIZE = 5
VIDEO_METADATA_SIZE = 12
MAX_PAYLOAD_SIZE = 32 * 1024 * 1024
QUEUE_SIZE = 120


@dataclass(frozen=True)
class ReaderEvent:
    kind: str
    value: bytes | str | None = None


class Relay:
    def __init__(self, socket_path: str, rtsp_url: str, frame_rate: float) -> None:
        self.socket_path = socket_path
        self.rtsp_url = rtsp_url
        self.frame_rate = frame_rate
        self.stop = threading.Event()
        self.sock: socket.socket | None = None
        self.ffmpeg: subprocess.Popen[bytes] | None = None

    def request_stop(self, _signum: int, _frame: object) -> None:
        self.stop.set()
        self.close_socket()
        self.stop_ffmpeg()

    def close_socket(self) -> None:
        sock, self.sock = self.sock, None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    def stop_ffmpeg(self) -> None:
        process, self.ffmpeg = self.ffmpeg, None
        if process is None:
            return
        if process.stdin:
            try:
                process.stdin.close()
            except OSError:
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    def start_ffmpeg(self) -> subprocess.Popen[bytes]:
        process = subprocess.Popen(
            [
                "/usr/bin/ffmpeg",
                "-hide_banner",
                "-loglevel",
                "warning",
                "-f",
                "h264",
                "-framerate",
                str(self.frame_rate),
                "-i",
                "pipe:0",
                "-an",
                "-c:v",
                "copy",
                "-f",
                "rtsp",
                "-rtsp_transport",
                "tcp",
                self.rtsp_url,
            ],
            stdin=subprocess.PIPE,
        )
        self.ffmpeg = process
        return process

    @staticmethod
    def recv_exact(sock: socket.socket, size: int) -> bytes:
        chunks = bytearray(size)
        view = memoryview(chunks)
        received = 0
        while received < size:
            count = sock.recv_into(view[received:])
            if count == 0:
                raise EOFError("demux socket closed")
            received += count
        return bytes(chunks)

    @staticmethod
    def put_event(events: queue.Queue[ReaderEvent], event: ReaderEvent) -> None:
        while True:
            try:
                events.put_nowait(event)
                return
            except queue.Full:
                try:
                    events.get_nowait()
                except queue.Empty:
                    pass

    def read_socket(self, sock: socket.socket, events: queue.Queue[ReaderEvent]) -> None:
        au_count = 0
        rate_started = time.monotonic()
        try:
            while not self.stop.is_set():
                header = self.recv_exact(sock, HEADER_SIZE)
                msg_type, payload_size = struct.unpack(">BI", header)
                if payload_size > MAX_PAYLOAD_SIZE:
                    raise ValueError(f"invalid payload size {payload_size}")
                payload = self.recv_exact(sock, payload_size)
                if msg_type == MSG_VIDEO:
                    if payload_size < VIDEO_METADATA_SIZE:
                        raise ValueError("short video payload")
                    self.put_event(events, ReaderEvent("au", payload[VIDEO_METADATA_SIZE:]))
                    au_count += 1
                    elapsed = time.monotonic() - rate_started
                    if elapsed >= 60:
                        logging.info("AU rate %.2f fps (%d AUs in %.1f s)", au_count / elapsed, au_count, elapsed)
                        au_count = 0
                        rate_started = time.monotonic()
                elif msg_type == MSG_SESSION_RESET:
                    self.put_event(events, ReaderEvent("reset"))
                    return
        except (EOFError, OSError, ValueError) as exc:
            if not self.stop.is_set():
                self.put_event(events, ReaderEvent("error", str(exc)))

    def run_subscription(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self.socket_path)
        self.sock = sock
        logging.info("subscribed to %s", self.socket_path)

        events: queue.Queue[ReaderEvent] = queue.Queue(maxsize=QUEUE_SIZE)
        reader = threading.Thread(target=self.read_socket, args=(sock, events), daemon=True)
        reader.start()
        process = self.start_ffmpeg()
        first_au = True

        try:
            while not self.stop.is_set():
                return_code = process.poll()
                if return_code is not None:
                    logging.warning("ffmpeg exited with code %d", return_code)
                    return
                try:
                    event = events.get(timeout=0.5)
                except queue.Empty:
                    continue
                if event.kind == "reset":
                    logging.info("session reset")
                    return
                if event.kind == "error":
                    logging.warning("subscription ended: %s", event.value)
                    return
                if first_au:
                    logging.info("received first AU")
                    first_au = False
                try:
                    assert process.stdin is not None
                    process.stdin.write(event.value if isinstance(event.value, bytes) else b"")
                    process.stdin.flush()
                except (BrokenPipeError, OSError):
                    return_code = process.poll()
                    logging.warning("ffmpeg pipe closed%s", f" with code {return_code}" if return_code is not None else "")
                    return
        finally:
            self.close_socket()
            self.stop_ffmpeg()
            reader.join(timeout=1)

    def run(self) -> None:
        backoff = 1
        while not self.stop.is_set():
            try:
                self.run_subscription()
                backoff = 1
            except OSError as exc:
                if not self.stop.is_set():
                    logging.warning("subscribe failed: %s", exc)
            if self.stop.wait(backoff):
                break
            backoff = min(backoff * 2, 10)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", type=int, required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--rtsp", required=True)
    parser.add_argument("--framerate", type=float, default=30.0)
    args = parser.parse_args()
    if args.channel not in range(4):
        parser.error("--channel must be 0..3")
    expected_path = f"ch{args.channel + 1}"
    if args.path != expected_path:
        parser.error(f"--path must be {expected_path} for channel {args.channel}")
    if args.socket != f"/tmp/camera_demux_ch{args.channel}.sock":
        parser.error("--socket does not match --channel")
    if args.rtsp != f"rtsp://127.0.0.1:8554/{args.path}":
        parser.error("--rtsp does not match --path")
    return args


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    relay = Relay(args.socket, args.rtsp, args.framerate)
    signal.signal(signal.SIGTERM, relay.request_stop)
    signal.signal(signal.SIGINT, relay.request_stop)
    relay.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
