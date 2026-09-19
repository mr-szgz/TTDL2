from playwright.sync_api import Browser, CDPSession, Page
import json
import pytest

from tiktok_downloader.core import Control, Downloader


def test_start_minimizes_real_browser_and_closes_before_downloads(job_factory, server, monkeypatch):
    job = job_factory(headless=False, manual_start=True)
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
            control.save_session.set()
        elif event["type"] == "session_saved":
            assert session_path.is_file()
            control.stop()

    Downloader(job_factory(manual_start=True, session_path=str(session_path)), save, control).scan()
    assert session_path.is_file()
    Downloader(job_factory(restore_session=True, session_path=str(session_path)),
               lambda event: None, Control()).scan()
    assert restored == [["session=secret", "saved-user", "saved-token"]]


@pytest.mark.parametrize("saved", [False, True])
@pytest.mark.parametrize("challenge", [False, True])
def test_check_session_waits_for_challenge_and_reuses_storage(job_factory, tmp_path, monkeypatch, saved, challenge):
    session_path = tmp_path / "browser-session.json"
    job = job_factory(check_session=True, session_path=str(session_path))
    if saved:
        session_path.write_text(json.dumps({"cookies": [], "origins": [{
            "origin": job.site, "localStorage": [{"name": "login", "value": "saved-user"}],
        }]}))
    goto = Page.goto
    pages = []

    def visit(page, url, **kwargs):
        result = goto(page, url, **kwargs)
        pages.append(page)
        assert page.evaluate("localStorage.getItem('login')") == ("saved-user" if saved else None)
        page.evaluate("""challenge => {
            const hidden = document.createElement('div');
            hidden.textContent = 'Drag the slider to fit the puzzle';
            hidden.style.display = 'none'; document.body.append(hidden);
            if (challenge) setTimeout(() => {
                const frame = document.createElement('iframe');
                frame.srcdoc = '<div>Drag the slider to fit the puzzle</div>';
                document.body.append(frame);
            }, 500);
        }""", challenge)
        return result

    monkeypatch.setattr(Page, "goto", visit)
    control = Control()
    events = []

    def checked(event):
        events.append(event)
        if event["type"] == "session_checked":
            assert not control.ready.is_set()
            assert event["challenge"] == challenge
            assert session_path.exists() == (saved or not challenge)
            control.resume()

    links = Downloader(job, checked, control).scan()
    assert len(pages) == 1
    assert len(links) == 2
    assert not any(event["type"] == "manual" for event in events)
