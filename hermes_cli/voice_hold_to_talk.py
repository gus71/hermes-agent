"""Optional Windows hold-to-talk key for the classic Hermes CLI.

A terminal keybinding only sees key presses, not releases.  Polling the Win32
keyboard state lets us send one recording per physical hold without requiring
a global keyboard-hook dependency.  This feature is opt-in via voice.hold_key.
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Callable

logger = logging.getLogger(__name__)

# Function keys are unlikely to collide with text entry or system shortcuts.
_KEYS = {"f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B}


def normalize_hold_key(value: object) -> str | None:
    """Only supported standalone function keys can enable hold-to-talk."""
    if not isinstance(value, str):
        return None
    key = value.strip().lower()
    return key if key in _KEYS else None


def windows_key_is_down(key: str) -> bool:
    """Read the current physical key state (high bit = held)."""
    if sys.platform != "win32":
        return False
    import ctypes
    return bool(ctypes.windll.user32.GetAsyncKeyState(_KEYS[key]) & 0x8000)


class WindowsHoldToTalk:
    """State machine for physical press/release edges; no auto-restart."""

    def __init__(
        self,
        key: str,
        *,
        enabled: Callable[[], bool],
        on_press: Callable[[], bool],
        on_release: Callable[[], None],
        is_down: Callable[[str], bool] = windows_key_is_down,
        poll_seconds: float = 0.025,
    ) -> None:
        if normalize_hold_key(key) != key:
            raise ValueError(f"Unsupported hold-to-talk key: {key}")
        self.key = key
        self._enabled = enabled
        self._on_press = on_press
        self._on_release = on_release
        self._is_down = is_down
        self._poll_seconds = poll_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._was_down = False
        self._owns_recording = False

    def process_key_state(self, down: bool) -> None:
        """One physical press starts, one release sends; repeats do nothing."""
        previous = self._was_down
        self._was_down = bool(down)
        if down and not previous and self._enabled():
            try:
                self._owns_recording = bool(self._on_press())
            except Exception:
                logger.exception("Hold-to-talk recording could not start")
                self._owns_recording = False
        elif not down and previous and self._owns_recording:
            self._owns_recording = False
            try:
                self._on_release()
            except Exception:
                logger.exception("Hold-to-talk recording could not stop")

    def _run(self) -> None:
        # An already-held key at startup is ignored until released and pressed anew.
        try:
            self._was_down = bool(self._is_down(self.key))
            while not self._stop_event.is_set():
                self.process_key_state(bool(self._is_down(self.key)))
                self._stop_event.wait(self._poll_seconds)
        except Exception:
            logger.exception("Hold-to-talk keyboard polling failed")

    def start(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Hold-to-talk keyboard polling requires Windows")
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="hermes-hold-to-talk"
        )
        self._thread.start()

    def stop(self) -> None:
        # The voice-mode shutdown owns cancelling any active audio recording.
        self._stop_event.set()
