from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import parse_qs, urlsplit
import pytest

@pytest.fixture
def server():
    counts = Counter()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_OPTIONS(self):
            self.do_GET()

        def do_GET(self):
            parsed = urlsplit(self.path)
            counts[parsed.path] += 1
            if (parsed.path.startswith("/@alice/")
                    and "sessionid=direct-cookie" in self.headers.get("Cookie", "")):
                counts["direct-cookie"] += 1
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if parsed.path == "/api/standard":
                media_id = parse_qs(parsed.query)["aweme_id"][0]
                self.send_json({"aweme_list": [{
                    "aweme_id": media_id,
                    "author": {"unique_id": "alice",
                               "avatar_medium": {"url_list": [origin + "/media/avatar.jpg"]},
                               "video_icon": {"url_list": [origin + "/media/avatar.gif"]}},
                    "video": {"play_addr": {"url_list": [origin + "/media/video.mp4"]},
                              "download_addr": {"url_list": [origin + "/media/watermark.mp4"]}},
                    "image_post_info": {"images": [
                        {"display_image": {"url_list": [origin + "/media/1.jpg"]}},
                        {"display_image": {"url_list": [origin + "/media/2.jpg"]}},
                    ]},
                }]})
            elif parsed.path == "/api/hd":
                assert parse_qs(parsed.query)["hd"] == ["1"]
                assert parse_qs(parsed.query)["url"][0].isdigit()
                self.send_json({"code": 0, "msg": "success", "data": {
                    "author": {"unique_id": "alice"}, "hdplay": origin + "/media/hd.mp4",
                    "images": [origin + "/media/1.jpg", origin + "/media/2.jpg"],
                }})
            elif parsed.path == "/api/hd-missing":
                media_id = parse_qs(parsed.query)["url"][0]
                media_path = "/media/missing.mp4" if media_id == "123" else "/media/hd.mp4"
                self.send_json({"code": 0, "msg": "success", "data": {
                    "author": {"unique_id": "alice"}, "hdplay": origin + media_path,
                    "images": [origin + "/media/1.jpg", origin + "/media/2.jpg"],
                }})
            elif parsed.path == "/api/limit":
                self.send_json({"code": -1, "msg": "Free Api Limit: 10000 request/ 1 day."})
            elif parsed.path == "/api/item/detail/":
                assert parse_qs(parsed.query)["itemId"] == ["456"]
                self.send_json({"itemInfo": {"itemStruct": {
                    "author": {"uniqueId": "alice"},
                    "imagePost": {"images": [
                        {"imageURL": {"urlList": [origin + "/media/1.jpg"]}},
                        {"imageURL": {"urlList": [origin + "/media/2.jpg"]}},
                    ]},
                }}})
            elif parsed.path == "/@alice":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b'''<!doctype html><html><body style="height:2000px">
                    <a href="/@alice/video/123?share=1">Video</a>
                    <a href="/@alice/video/123">Duplicate</a>
                    <a href="/@other/video/999">Other user</a>
                    <script>window.addEventListener('scroll', () => {
                        fetch('/indexing');
                        if (!document.querySelector('#photo')) {
                            const a = document.createElement('a'); a.id = 'photo';
                            a.href = '/@alice/photo/456'; a.textContent = 'Photo';
                            document.body.append(a);
                        }
                    });</script></body></html>''')
            elif parsed.path == "/navigating/@alice":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                if parse_qs(parsed.query).get("stable") == ["1"]:
                    self.wfile.write(b'''<!doctype html><html><body>
                        <a href="/@alice/video/123">Video</a>
                        <a href="/@alice/photo/456">Photo</a>
                        </body></html>''')
                else:
                    self.wfile.write(b'''<!doctype html><html><body><script>
                        document.addEventListener('DOMContentLoaded', () => {
                            location.replace('/navigating/@alice?stable=1');
                        });
                        </script></body></html>''')
            elif parsed.path == "/indexing":
                self.send_response(204)
                self.end_headers()
            elif parsed.path == "/t/short":
                self.send_response(302)
                self.send_header("Location", origin + "/@alice/video/123")
                self.end_headers()
            elif parsed.path == "/@alice/video/123":
                self.send_tiktok_item({
                    "author": {"uniqueId": "alice"},
                    "video": {"bitrateInfo": [
                        {"Bitrate": 400000, "PlayAddr": {
                            "Width": 640, "Height": 360, "DataSize": "1000",
                            "UrlList": [origin + "/media/low.mp4"],
                        }},
                        {"Bitrate": 2000000, "PlayAddr": {
                            "Width": 1920, "Height": 1080, "DataSize": "5000",
                            "UrlList": [origin + "/media/direct-hd.mp4"],
                        }},
                    ]},
                })
            elif parsed.path == "/@alice/photo/456":
                body = b'''<!doctype html><html><body><script>
                    fetch('/api/item/detail/?itemId=456');
                    </script></body></html>'''
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif parsed.path == "/media/missing.mp4":
                self.send_response(404)
                self.end_headers()
            elif parsed.path.startswith("/media/"):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"fixture-media:" + parsed.path.encode())
            elif parsed.path.startswith("/@alice/"):
                self.send_response(200)
                self.end_headers()
            elif parsed.path == "/bad-json":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"not JSON")
            else:
                self.send_response(503)
                self.end_headers()

        def send_json(self, data):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Limit-Request-Remaining", "4321")
            self.send_header("X-Limit-Request-Reset", "3600")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        def send_tiktok_item(self, item):
            raw = {"__DEFAULT_SCOPE__": {"webapp.video-detail": {
                "itemInfo": {"itemStruct": item},
            }}}
            body = ("<!doctype html><html><body><script "
                    "id=\"__UNIVERSAL_DATA_FOR_REHYDRATION__\" type=\"application/json\">"
                    + json.dumps(raw) + "</script></body></html>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{http.server_port}", counts
    http.shutdown()
    http.server_close()
    thread.join()

@pytest.fixture
def job_factory(server, tmp_path):
    from tiktok_downloader.core import Job
    origin, _ = server
    def make(**kwargs):
        options = dict(source="@alice", folder=str(tmp_path / "downloads"),
                       session_path=str(tmp_path / "browser-session.json"),
                       scan_dir=str(tmp_path / "config" / "scans"),
                       index_dir=str(tmp_path / "config" / "indexes"),
                       site=origin, hd_api=origin + "/api/hd",
                       browser="chromium", headless=True, manual_start=False, scroll_ms=150)
        options.update(kwargs)
        return Job(**options)
    return make
