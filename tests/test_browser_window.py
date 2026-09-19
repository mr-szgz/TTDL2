import json

from playwright.sync_api import Browser, CDPSession, Page

from tiktok_downloader.core import Control, Downloader


def test_start_minimizes_real_browser_and_closes_before_downloads(job_factory, server, monkeypatch, tmp_path):
    job = job_factory(headless=False, manual_start=True, session_path=str(tmp_path / "browser-session.json"))
    control = Control()
    states = []
    closed = []
    send = CDPSession.send
    close = Browser.close

    def observe_send(session, method, params=None):
        result = send(session, method, params)
        if method == "Browser.getWindowForTarget":
            states.append(result["bounds"]["windowState"])
        elif method == "Browser.setWindowBounds":
            states.append(send(session, "Browser.getWindowBounds", {
                "windowId": params["windowId"],
            })["bounds"]["windowState"])
        return result

    def observe_close(browser, **kwargs):
        assert server[1]["/api/hd"] == 0
        close(browser, **kwargs)
        closed.append(not browser.is_connected())

    def start(event):
        if event["type"] == "manual":
            assert states == []
            assert server[1]["/indexing"] == 0
            control.resume()

    monkeypatch.setattr(CDPSession, "send", observe_send)
    monkeypatch.setattr(Browser, "close", observe_close)
    downloader = Downloader(job, start, control)
    links = downloader.scan()
    assert server[1]["/api/hd"] == 0
    downloader.run(links)

    assert states == ["normal", "minimized"]
    assert closed == [True]
    assert server[1]["/indexing"] > 0
    assert server[1]["/api/hd"] == 2


def test_save_and_restore_browser_storage(job_factory, tmp_path, monkeypatch):
    session_path = tmp_path / "browser-session.json"
    goto = Page.goto
    restored = []

    def visit(page, url, **kwargs):
        result = goto(page, url, **kwargs)
        if session_path.exists():
            restored.append(page.evaluate("""async () => {
                const db = await new Promise(resolve => {
                    const request = indexedDB.open('auth');
                    request.onsuccess = () => resolve(request.result);
                });
                const token = await new Promise(resolve => {
                    const request = db.transaction('tokens').objectStore('tokens').get('login');
                    request.onsuccess = () => resolve(request.result);
                });
                db.close();
                return [document.cookie, localStorage.getItem('login'), token];
            }"""))
        else:
            page.evaluate("""async () => {
                document.cookie = 'session=secret; path=/';
                localStorage.setItem('login', 'saved-user');
                const db = await new Promise(resolve => {
                    const request = indexedDB.open('auth', 1);
                    request.onupgradeneeded = () => request.result.createObjectStore('tokens');
                    request.onsuccess = () => resolve(request.result);
                });
                await new Promise(resolve => {
                    const transaction = db.transaction('tokens', 'readwrite');
                    transaction.objectStore('tokens').put('saved-token', 'login');
                    transaction.oncomplete = resolve;
                });
                db.close();
            }""")
        return result

    monkeypatch.setattr(Page, "goto", visit)
    control = Control()

    def save(event):
        if event["type"] == "manual":
            control.resume()
        elif event["type"] == "session_saved":
            assert session_path.is_file()
            control.stop()

    Downloader(job_factory(manual_start=True, session_path=str(session_path)), save, control).scan()
    assert session_path.is_file()
    Downloader(job_factory(session_path=str(session_path)),
               lambda event: None, Control()).scan()
    assert restored == [["session=secret", "saved-user", "saved-token"]]


def test_new_session_starts_empty_and_stop_saves_login(job_factory, tmp_path, monkeypatch):
    session_path = tmp_path / "browser-session.json"
    session_path.write_text(json.dumps({"cookies": [], "origins": [{
        "origin": job_factory().site,
        "localStorage": [{"name": "login", "value": "old-user"}],
    }]}))
    goto = Page.goto
    pages = []

    def visit(page, url, **kwargs):
        result = goto(page, url, **kwargs)
        assert page.evaluate("localStorage.getItem('login')") is None
        pages.append(page)
        return result

    monkeypatch.setattr(Page, "goto", visit)
    control = Control()

    def login_and_stop(event):
        if event["type"] == "manual":
            pages[0].evaluate("localStorage.setItem('login', 'new-user')")
            control.stop()

    Downloader(job_factory(new_session=True, manual_start=True), login_and_stop, control).scan()
    state = json.loads(session_path.read_text())
    assert state["origins"][0]["localStorage"] == [{"name": "login", "value": "new-user"}]
