from __future__ import annotations

from dataclasses import dataclass

SCROLL_DOWN = "SCROLL_DOWN"


@dataclass
class TrackerStatus:
    closed: bool = False
    closed_ms: int = 0
    cooldown_ms: int = 0
    armed: bool = True


class BlinkTracker:
    """Göz kapalı kaldığı süre eşiği geçince anında SCROLL_DOWN üretir.

    Tetikleme göz açılmayı beklemez: gözler kapalıyken `min_closed_ms`
    dolduğu karede kaydırma yapılır. Gözler açılana kadar yeni tetikleme
    olmaz, açıldıktan sonra cooldown bitince tekrar silah kurulur.
    """

    def __init__(
        self,
        threshold: float,
        min_closed_ms: int = 400,
        cooldown_ms: int = 1200,
    ):
        self.threshold = threshold
        self.min_closed_ms = min_closed_ms
        self.cooldown_ms = cooldown_ms

        self._closed_start: float | None = None
        self._cooldown_until: float = 0.0
        self._armed = True
        self._fired = False
        self._last_event: str | None = None

    @property
    def last_event(self) -> str | None:
        return self._last_event

    def status(self, now_ms: float) -> TrackerStatus:
        closed_ms = int(now_ms - self._closed_start) if self._closed_start is not None else 0
        return TrackerStatus(
            closed=self._closed_start is not None,
            closed_ms=max(0, closed_ms),
            cooldown_ms=max(0, int(self._cooldown_until - now_ms)),
            armed=self._armed,
        )

    def _in_cooldown(self, now_ms: float) -> bool:
        return now_ms < self._cooldown_until

    def update(self, now_ms: float, face: bool, ear: float | None) -> list[str]:
        events: list[str] = []
        closed = bool(face) and ear is not None and ear < self.threshold

        if not closed:
            self._closed_start = None
            self._armed = True
            self._fired = False
            return events

        if self._closed_start is None:
            self._closed_start = now_ms

        if (
            not self._fired
            and self._armed
            and not self._in_cooldown(now_ms)
            and now_ms - self._closed_start >= self.min_closed_ms
        ):
            self._fired = True
            self._armed = False
            self._cooldown_until = now_ms + self.cooldown_ms
            self._last_event = SCROLL_DOWN
            events.append(SCROLL_DOWN)

        return events
