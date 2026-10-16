"""Независимые загрузчики с общим форматом ответа."""
from dataclasses import dataclass


@dataclass
class FetchResult:
    url: str
    status: int
    html: str
    browser_version: str = ""


def browser_page(browser, source, timeout):
    page = browser.new_page()
    try:
        response = page.goto(source["url"], wait_until="domcontentloaded", timeout=timeout * 1000)
        status = response.status if response is not None else 0
        if status == 200 and source.get("wait_for_selector"):
            page.locator(source["wait_for_selector"]).first.wait_for(
                state="attached", timeout=timeout * 1000
            )
        # Clearcote может возвращать BrowserContext вместо Browser.
        owner = getattr(browser, "browser", None)
        version = getattr(browser, "version", None) or getattr(owner, "version", "")
        return FetchResult(page.url, status, page.content(), version)
    finally:
        page.close()


def fetch(engine: str, source: dict, config: dict) -> FetchResult:
    timeout = config["timeout_seconds"]
    headless = config.get("headless", True)
    if engine == "curl_cffi":
        from curl_cffi import requests
        try:
            with requests.Session(impersonate="chrome") as session:
                response = session.get(source["url"], timeout=timeout, allow_redirects=True)
                return FetchResult(str(response.url), response.status_code, response.text)
        except requests.exceptions.Timeout as exc:
            raise TimeoutError("Истекло время HTTP-запроса") from exc
        except requests.exceptions.ConnectionError as exc:
            raise ConnectionError("Ошибка HTTP-соединения") from exc
    if engine == "patchright":
        from patchright.sync_api import sync_playwright
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=headless, timeout=timeout * 1000)
            try:
                return browser_page(browser, source, timeout)
            finally:
                browser.close()
    if engine == "camoufox":
        from camoufox.sync_api import Camoufox
        with Camoufox(headless=headless, timeout=timeout * 1000) as browser:
            return browser_page(browser, source, timeout)
    if engine == "clearcote":
        from clearcote import launch
        browser = launch(headless=headless, timeout=timeout * 1000)
        try:
            return browser_page(browser, source, timeout)
        finally:
            browser.close()
    raise ValueError(f"Неизвестный загрузчик: {engine}")
