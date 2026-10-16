"""Интеграционные проверки установленных браузеров; включаются явно."""
import os
import pytest
from web_pipeline.backends import fetch
from test_pipeline import config


@pytest.mark.browser
@pytest.mark.parametrize("engine", ["patchright", "camoufox", "clearcote"])
def test_browser_javascript(site, engine):
    if os.environ.get("TEST_BROWSERS") != "1":
        pytest.skip("Для браузерных проверок задайте TEST_BROWSERS=1")
    source = {"url": site, "wait_for_selector": "#dynamic"}
    result = fetch(engine, source, config(site))
    assert result.status == 200
    assert 'id="dynamic"' in result.html
    assert "Динамический фрагмент." in result.html
    assert result.browser_version
