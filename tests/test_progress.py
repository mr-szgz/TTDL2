import pytest

from tiktok_downloader import progress


@pytest.fixture
def clock(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(progress, "monotonic", lambda: now[0])
    return now


def test_rate_eta_and_completion(clock):
    stats = progress.DownloadProgress(8)
    assert stats.summary() == "0.00 items/sec — ETA calculating…"
    clock[0] += 4
    stats.completed = 2
    assert stats.summary() == "0.50 items/sec — ETA 00:12"
    clock[0] += 4
    assert stats.summary() == "0.25 items/sec — ETA 00:24"
    stats.completed = 8
    assert stats.summary() == "1.00 items/sec — ETA 00:00"


def test_pause_time_is_excluded(clock):
    stats = progress.DownloadProgress(8)
    clock[0] += 4
    stats.completed = 2
    stats.pause()
    clock[0] += 100
    assert stats.summary() == "0.50 items/sec — ETA 00:12"
    stats.resume()
    assert stats.summary() == "0.50 items/sec — ETA 00:12"
    clock[0] += 4
    assert stats.summary() == "0.25 items/sec — ETA 00:24"


def test_hour_eta_and_new_batch(clock):
    stats = progress.DownloadProgress(3602)
    clock[0] += 1
    stats.completed = 1
    assert stats.summary() == "1.00 items/sec — ETA 01:00:01"
    new_batch = progress.DownloadProgress(3)
    assert new_batch.summary() == "0.00 items/sec — ETA calculating…"
