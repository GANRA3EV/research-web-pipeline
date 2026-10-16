"""Проверка кодов завершения центральной команды."""
import json
import subprocess
import sys
from pathlib import Path


def test_cli_partial_failure_exit_code(site, tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "engines": ["curl_cffi"], "delay_seconds": 0, "retries": 0,
        "sources": [{"id": "blocked", "url": site + "/blocked"}],
    }), encoding="utf-8")
    result = subprocess.run([sys.executable, "run_all.py", "--config", str(config),
                             "--output", str(tmp_path / "result")],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True)
    assert result.returncode == 1
    assert (tmp_path / "result/data/raw.xlsx").exists()


def test_cli_bad_config_exit_code(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"sources": []}', encoding="utf-8")
    result = subprocess.run([sys.executable, "run_all.py", "--config", str(config)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True)
    assert result.returncode == 2
