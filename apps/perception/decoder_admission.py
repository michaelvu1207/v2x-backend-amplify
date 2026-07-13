"""Priority-aware admission for temporary perception GPU decoders."""

from __future__ import annotations

import threading


class AuxiliaryDecoderLease:
    """One idempotently releasable admission permit."""

    def __init__(self, admission):
        self._admission = admission
        self._lock = threading.Lock()
        self._released = False

    def release(self):
        with self._lock:
            if self._released:
                return
            self._released = True
        self._admission._release()


class UrgentDecoderWindow:
    """Keep normal auxiliary work out of a bounded terminal recovery window."""

    def __init__(self, admission):
        self._admission = admission
        self._lock = threading.Lock()
        self._released = False

    def release(self):
        with self._lock:
            if self._released:
                return
            self._released = True
        self._admission._end_urgent_window()


class PriorityDecoderAdmission:
    """Bound auxiliary decoders while admitting terminal work first."""

    def __init__(self, capacity):
        capacity = int(capacity)
        if capacity < 1:
            raise ValueError("decoder admission capacity must be positive")
        self._capacity = capacity
        self._condition = threading.Condition()
        self._in_use = 0
        self._urgent_waiters = 0
        self._urgent_windows = 0

    def begin_urgent_window(self):
        """Reserve scheduling priority across a multi-step terminal recovery."""
        with self._condition:
            self._urgent_windows += 1
            self._condition.notify_all()
        return UrgentDecoderWindow(self)

    def acquire(self, *, urgent=False, cancelled=None):
        urgent = bool(urgent)
        acquired = False
        with self._condition:
            if urgent:
                self._urgent_waiters += 1
            try:
                while True:
                    if cancelled is not None and cancelled():
                        raise RuntimeError("auxiliary decoder admission cancelled")
                    if (
                        self._in_use < self._capacity
                        and (
                            urgent
                            or (
                                self._urgent_waiters == 0
                                and self._urgent_windows == 0
                            )
                        )
                    ):
                        self._in_use += 1
                        acquired = True
                        return AuxiliaryDecoderLease(self)
                    self._condition.wait(timeout=0.05)
            finally:
                if urgent:
                    self._urgent_waiters -= 1
                    if not acquired:
                        self._condition.notify_all()

    def _release(self):
        with self._condition:
            if self._in_use < 1:
                raise RuntimeError("auxiliary decoder admission underflow")
            self._in_use -= 1
            self._condition.notify_all()

    def _end_urgent_window(self):
        with self._condition:
            if self._urgent_windows < 1:
                raise RuntimeError("urgent decoder window underflow")
            self._urgent_windows -= 1
            self._condition.notify_all()

    def snapshot(self):
        with self._condition:
            return {
                "capacity": self._capacity,
                "in_use": self._in_use,
                "urgent_waiters": self._urgent_waiters,
                "urgent_windows": self._urgent_windows,
            }


AUXILIARY_DECODER_ADMISSION = PriorityDecoderAdmission(capacity=2)


def acquire_auxiliary_decoder_slot(*, urgent=False, cancelled=None):
    return AUXILIARY_DECODER_ADMISSION.acquire(
        urgent=urgent,
        cancelled=cancelled,
    )


def begin_urgent_decoder_window():
    return AUXILIARY_DECODER_ADMISSION.begin_urgent_window()
