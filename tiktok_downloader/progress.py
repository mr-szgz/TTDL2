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
        mb_per_second = self.downloaded_bytes / elapsed / 1_000_000 if self.downloaded_bytes else 0.0
        transfer = f"{self.downloaded_bytes:,} bytes downloaded — {mb_per_second:.2f} MB/s"
        if self.completed == 0:
            return f"{transfer} — ETA calculating…"
        rate = self.completed / elapsed
        remaining = ceil((self.total - self.completed) / rate)
        hours, remainder = divmod(remaining, 3600)
        minutes, seconds = divmod(remainder, 60)
        eta = f"{hours:02}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"
        return f"{transfer} — ETA {eta}"
