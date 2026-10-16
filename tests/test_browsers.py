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


@pytest.mark.browser
@pytest.mark.skipif(os.name != "nt", reason="Ошибка чтения Unicode-путей относится к Windows")
def test_windows_unicode_compressed_file(tmp_path):
    if os.environ.get("TEST_BROWSERS") != "1":
        pytest.skip("Для браузерных проверок задайте TEST_BROWSERS=1")
    from web_pipeline.compatibility import windows_fpgen_paths
    import zstandard
    path = tmp_path / "русская_папка"
    path.mkdir()
    archive = path / "values.dat.zst"
    content = "Проверка чтения Unicode-пути".encode("utf-8")
    archive.write_bytes(zstandard.ZstdCompressor().compress(content))
    with windows_fpgen_paths():
        from fpgen import unpacker
        with unpacker.IndexedZstdFile(str(archive)) as source:
            assert source.read() == content
