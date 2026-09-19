from playwright.sync_api import Browser, CDPSession

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
