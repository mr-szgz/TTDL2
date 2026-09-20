import json
from pathlib import Path
import threading
from requests.exceptions import HTTPError
import pytest
from tiktok_downloader.core import Control, Downloader, filename_component, post_parts, profile_name, read_links

@pytest.mark.parametrize(("video_dir", "image_dir"), [("video", "photo"), ("Videos", "Images")])
def test_hd_mass_download(job_factory, server, video_dir, image_dir):
    job = job_factory(download_logs=True, video_dir=video_dir, image_dir=image_dir)
    events = []
    downloader = Downloader(job, events.append, Control())
    downloader.run(downloader.scan())
    root = Path(job.folder) / "alice"
    assert (root / video_dir / "123_HD.mp4").read_bytes() == b"fixture-media:/media/hd.mp4"
    for i in (1, 2):
        assert (root / image_dir / f"456_{i}.jpg").read_bytes() == f"fixture-media:/media/{i}.jpg".encode()
    assert (Path(job.scan_dir) / "alice_combined_links.txt").read_text().splitlines() == [
        server[0] + "/@alice/video/123", server[0] + "/@alice/photo/456"]
    assert not list(Path(job.folder).glob("*_combined_links.txt"))
    assert (root / "Data" / "json" / "123_HD.json").exists()
    assert (root / "Data" / "json" / "456_HD.json").exists()
    assert not (root / "123_HD.json").exists()
    assert not (root / "alice_index.txt").exists()
    assert (Path(job.index_dir) / "alice_index.txt").read_text().splitlines() == ["123_HD", "456_1.jpg", "456_2.jpg"]
    assert events[-1] == {"type": "done", "stopped": False}
    transferred = sum(event["bytes"] for event in events if event["type"] == "transfer")
    assert transferred == sum(path.stat().st_size for path in root.rglob("*") if path.suffix in (".mp4", ".jpg"))
    indexing = [event for event in events if event["type"] == "indexing"]
    assert [(event["total"], event["added"]) for event in indexing] == [(1, 1), (2, 1)]
    assert [event for event in events if event["type"] == "log"
            and event["message"].startswith("Scan delay:")] == [
        {"type": "log", "message": "Scan delay: 0.15 sec"},
    ]
    assert all(set(event) == {"type", "total", "added"} for event in indexing)
    assert [event for event in events if event["type"] == "downloading"] == [
        {"type": "downloading", "current": 1, "total": 2},
        {"type": "downloading", "current": 2, "total": 2},
    ]
    assert [event for event in events if event["type"] == "api_usage"][:2] == [
        {"type": "api_usage", "remaining": "4321", "reset_seconds": "3600", "message": "success"},
        {"type": "api_usage", "remaining": "4321", "reset_seconds": "3600", "message": "success"},
    ]
    assert server[1]["/api/standard"] == 0
    assert server[1]["/media/watermark.mp4"] == 0
    assert server[1]["/@alice/video/123"] == 0
    before = sum(v for k,v in server[1].items() if k.startswith("/media/"))
    downloader = Downloader(job, events.append, Control())
    downloader.run(downloader.scan())
    assert sum(v for k,v in server[1].items() if k.startswith("/media/")) == before
    assert sum(event["bytes"] for event in events if event["type"] == "transfer") == transferred

def test_images_only(job_factory):
    job = job_factory(images_only=True)
    downloader = Downloader(job, lambda _: None, Control())
    downloader.run(downloader.scan())
    assert not list(Path(job.folder).rglob("*.mp4"))
    assert len(list(Path(job.folder).rglob("*.jpg"))) == 2


def test_tiktok_direct_downloads_highest_resolution_video_and_photos(job_factory, server):
    job = job_factory(api_method="tiktok_direct", tiktok_cookie="sessionid=direct-cookie")
    events = []

    Downloader(job, events.append, Control()).run([
        server[0] + "/@alice/video/123",
        server[0] + "/@alice/photo/456",
    ])

    root = Path(job.folder) / "alice"
    assert (root / "video" / "123_HD.mp4").read_bytes() == b"fixture-media:/media/direct-hd.mp4"
    assert not server[1]["/media/low.mp4"]
    for index in (1, 2):
        assert (root / "photo" / f"456_{index}.jpg").read_bytes() == \
            f"fixture-media:/media/{index}.jpg".encode()
    assert (root / "Data" / "json" / "123_DIRECT.json").exists()
    assert (root / "Data" / "json" / "456_DIRECT.json").exists()
    assert server[1]["/api/hd"] == 0
    assert server[1]["direct-cookie"] == 2
    assert not [event for event in events if event["type"] in ("api_usage", "api_error")]
    assert events[-1] == {"type": "done", "stopped": False}


def test_scan_continues_when_profile_navigates_after_dom_loaded(job_factory, server):
    job = job_factory(site=server[0] + "/navigating")

    links = Downloader(job, lambda _: None, Control()).scan()

    assert links == [
        server[0] + "/@alice/video/123",
        server[0] + "/@alice/photo/456",
    ]
    assert server[1]["/navigating/@alice"] == 2

def test_stop_during_download(job_factory):
    job = job_factory()
    control = Control()
    events = []
    def emit(event):
        events.append(event)
        if event["type"] == "log" and "/video/" in event["message"].replace("\\", "/") and event["message"].startswith("Saved"):
            control.stop()
    downloader = Downloader(job, emit, control)
    downloader.run(downloader.scan())
    assert events[-1] == {"type": "done", "stopped": True}
    assert len(list(Path(job.folder).rglob("*.mp4"))) == 1
    assert not list(Path(job.folder).rglob("*.jpg"))

def test_pause_resume():
    control = Control()
    control.pause()
    entered, done = threading.Event(), threading.Event()
    def work():
        entered.set()
        control.checkpoint()
        done.set()
    thread = threading.Thread(target=work)
    thread.start()
    assert entered.wait(1)
    assert not done.wait(0.1)
    control.resume()
    assert done.wait(1)
    thread.join()

@pytest.mark.parametrize("path,error", [("/unavailable", HTTPError), ("/bad-json", json.JSONDecodeError)])
def test_original_hd_provider_failure_is_not_replaced(path, error, job_factory, server):
    job = job_factory(hd_api=server[0] + path)
    with pytest.raises(error):
        downloader = Downloader(job, lambda _: None, Control())
        downloader.run(downloader.scan())
    assert server[1][path] == 1
    assert not list(Path(job.folder).rglob("*.mp4"))

def test_missing_media_is_skipped_and_batch_continues(job_factory, server):
    job = job_factory(hd_api=server[0] + "/api/hd-missing")
    events = []
    Downloader(job, events.append, Control()).run([
        server[0] + "/@alice/video/123",
        server[0] + "/@alice/video/789",
    ])
    root = Path(job.folder) / "alice" / "video"
    assert not (root / "123_HD.mp4").exists()
    assert not (root / "123_HD.mp4.part").exists()
    assert (root / "789_HD.mp4").read_bytes() == b"fixture-media:/media/hd.mp4"
    assert {"type": "log", "message": "Skipped unavailable media: 123_HD.mp4 (HTTP 404)"} in events
    assert events[-1] == {"type": "done", "stopped": False}


def test_api_limit_is_saved_and_reported_without_crashing(job_factory, server):
    job = job_factory(hd_api=server[0] + "/api/limit")
    events = []
    Downloader(job, events.append, Control()).run([server[0] + "/@alice/video/123"])

    response_path = Path(job.folder) / "alice" / "Data" / "json" / "123_HD.json"
    assert json.loads(response_path.read_text()) == {
        "code": -1, "msg": "Free Api Limit: 10000 request/ 1 day."
    }
    assert {"type": "api_usage", "remaining": "4321", "reset_seconds": "3600",
            "message": "Free Api Limit: 10000 request/ 1 day."} in events
    assert {"type": "api_error", "media_id": "123", "status_code": 200,
            "request_url": server[0] + "/api/limit?url=123&hd=1", "remaining": "4321",
            "reset_seconds": "3600",
            "response": {"code": -1, "msg": "Free Api Limit: 10000 request/ 1 day."},
            "response_body": '{"code": -1, "msg": "Free Api Limit: 10000 request/ 1 day."}',
            "response_path": str(response_path)} in events
    assert events[-1] == {"type": "done", "stopped": False, "failed": True}
    assert not list(Path(job.folder).rglob("*.mp4"))

def test_parsing(tmp_path):
    assert post_parts("https://www.tiktok.com/@a.b/photo/123/?x=1") == ("a.b", "photo", "123")
    assert profile_name("https://www.tiktok.com/@a.b/?lang=en") == "a.b"
    assert post_parts("https://www.tiktok.com/@ayvah%2Enizzari/photo/123") == ("ayvah.nizzari", "photo", "123")
    assert profile_name("https://www.tiktok.com/@ayvah%2Enizzari/") == "ayvah.nizzari"
    assert filename_component("ayvah.nizzari") == "ayvah.nizzari"
    assert filename_component("../../name") == "..%2F..%2Fname"
    with pytest.raises(FileNotFoundError):
        read_links(tmp_path / "missing.txt")


def test_downloads_reuse_connection_without_per_file_wait(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from time import monotonic
    from tiktok_downloader.core import Job

    connections = []
    metadata_times = []
    payload = b"media-bytes" * 30000

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            pass

        def do_GET(self):
            connections.append(self.client_address)
            if self.path.startswith("/api/"):
                metadata_times.append(monotonic())
                origin = f"http://127.0.0.1:{self.server.server_port}"
                body = json.dumps({"code": 0, "msg": "success",
                    "data": {"author": {"unique_id": "ayvah.nizzari"},
                    "hdplay": origin + "/video", "images": [origin + "/1", origin + "/2"]}}).encode()
            else:
                body = payload
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as http:
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{http.server_port}"
        job = Job(source="@ayvah.nizzari", folder=str(tmp_path), hd_api=origin + "/api/",
                  index_dir=str(tmp_path / "app-data" / "indexes"))
        events = []
        started = monotonic()
        Downloader(job, events.append, Control()).run([
            origin + "/@ayvah%2Enizzari/video/123", origin + "/@ayvah%2Enizzari/photo/456"])
        Downloader(job, events.append, Control()).run([origin + "/@ayvah%2Enizzari/video/123"])
        elapsed = monotonic() - started
        http.shutdown()
        thread.join()

    assert len(connections) == 5
    assert len(set(connections)) == 1
    assert metadata_times[1] - metadata_times[0] >= 1.0
    assert elapsed < 3  # The old 1.9-second delay alone took 5.7 seconds.
    assert (tmp_path / "ayvah.nizzari" / "video" / "123_HD.mp4").read_bytes() == payload
    for i in (1, 2):
        assert (tmp_path / "ayvah.nizzari" / "photo" / f"456_{i}.jpg").read_bytes() == payload
    assert sum(event["bytes"] for event in events if event["type"] == "transfer") == 3 * len(payload)
