from __future__ import annotations


class ChromeError(RuntimeError):
    pass


class ChromeController:
    def __init__(
        self,
        port: int = 9222,
        scroll_down_key: str = "PageDown",
        scroll_up_key: str = "PageUp",
        timeout_s: int = 10,
    ):
        self.port = port
        self.scroll_down_key = scroll_down_key
        self.scroll_up_key = scroll_up_key
        self.timeout_s = timeout_s
        self._pw = None
        self._browser = None
        self._page = None
        self.last_scroll_method: str | None = None

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ChromeError(
                "playwright is not installed. Run: pip install playwright; playwright install chromium"
            ) from exc

        self._sync_playwright = sync_playwright
        self._connect()

    def _connect(self) -> None:
        self._pw = self._sync_playwright().start()
        endpoint = f"http://127.0.0.1:{self.port}"
        try:
            self._browser = self._pw.chromium.connect_over_cdp(endpoint, timeout=self.timeout_s * 1000)
        except Exception as exc:  # noqa: BLE001
            self.close()
            raise ChromeError(
                f"could not attach to Chrome on port {self.port}. "
                f"Start it with: .\\start_chrome.ps1 -Port {self.port}  ({exc})"
            ) from exc
        self._page = self._pick_page()
        if self._page is None:
            self.close()
            raise ChromeError("Chrome is reachable but exposes no open tab")

    def _pick_page(self):
        pages = []
        for context in self._browser.contexts:
            pages.extend(context.pages)
        if not pages:
            return None
        for page in pages:
            try:
                if "youtube.com" in (page.url or ""):
                    return page
            except Exception:  # noqa: BLE001
                continue
        return pages[-1]

    @property
    def url(self) -> str:
        try:
            return self._page.url or ""
        except Exception:  # noqa: BLE001
            return ""

    def focus(self) -> None:
        try:
            self._page.bring_to_front()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._page.evaluate(
                "() => { const el = document.querySelector('video'); "
                "if (el) { el.focus({ preventScroll: true }); } }"
            )
        except Exception:  # noqa: BLE001
            pass

    def _scroll_y(self) -> float | None:
        try:
            return float(self._page.evaluate("() => window.scrollY"))
        except Exception:  # noqa: BLE001
            return None

    def _viewport_height(self) -> float:
        try:
            return float(self._page.evaluate("() => window.innerHeight")) or 800.0
        except Exception:  # noqa: BLE001
            return 800.0

    def _moved(self, before: float | None) -> bool:
        after = self._scroll_y()
        return before is not None and after is not None and after != before

    def _scroll(self, key: str, direction: int) -> str:
        """Tuşla kaydır; sayfa kaymadıysa tekerlek ve JS ile dene."""
        before = self._scroll_y()

        try:
            self._page.keyboard.press(key)
        except Exception:  # noqa: BLE001
            pass
        self._page.wait_for_timeout(120)
        if self._moved(before):
            return "key"

        delta = direction * self._viewport_height() * 0.85
        try:
            self._page.mouse.wheel(0, delta)
        except Exception:  # noqa: BLE001
            pass
        self._page.wait_for_timeout(120)
        if self._moved(before):
            return "wheel"

        try:
            self._page.evaluate("(dy) => window.scrollBy(0, dy)", delta)
        except Exception:  # noqa: BLE001
            pass
        self._page.wait_for_timeout(60)
        return "js" if self._moved(before) else "none"

    def page_down(self) -> str:
        return self._scroll(self.scroll_down_key, 1)

    def page_up(self) -> str:
        return self._scroll(self.scroll_up_key, -1)

    def scroll(self, direction: str) -> str:
        self.last_scroll_method = (
            self.page_up() if direction == "SCROLL_UP" else self.page_down()
        )
        return self.last_scroll_method

    def close(self) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:  # noqa: BLE001
            pass
        self._browser = None
        self._pw = None
        self._page = None

    def __enter__(self) -> "ChromeController":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
