from math import ceil
from time import monotonic


class DownloadProgress:
    """Batch transfer rate and post-based ETA, excluding pauses."""

    def __init__(self, total):
        self.total = total
        self.completed = 0
        self.downloaded_bytes = 0
        self.started = monotonic()
        self.paused_at = None
        self.paused_seconds = 0.0

    def pause(self):
        self.paused_at = monotonic()

    def resume(self):
        self.paused_seconds += monotonic() - self.paused_at
        self.paused_at = None

    def summary(self):
        now = monotonic() if self.paused_at is None else self.paused_at
        elapsed = now - self.started - self.paused_seconds
        percentage = round(self.completed / self.total * 100) if self.total else 0
        if self.completed == 0:
            return f"{percentage}% — 0.00 items/s — ETA calculating…"
        rate = self.completed / elapsed
        remaining = ceil((self.total - self.completed) / rate)
        hours, remainder = divmod(remaining, 3600)
        minutes, seconds = divmod(remainder, 60)
        eta = f"{hours:02}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"
        return f"{percentage}% — {rate:.2f} items/s — ETA {eta}"
