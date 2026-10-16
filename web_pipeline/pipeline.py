"""Последовательный сбор, контроль качества и сохранение каждого шага."""
import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from .backends import fetch
from .extract import extract
from .storage import write_xlsx


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def run(config: dict, output: Path, fetcher=fetch) -> dict:
    # Каждый запуск получает отдельную папку; существующие результаты не перезаписываются.
    output.mkdir(parents=True, exist_ok=False)
    data = output / "data"
    logs = output / "logs"
    data.mkdir()
    logs.mkdir()
    versions = {}
    for package in ("curl_cffi", "patchright", "camoufox", "clearcote", "beautifulsoup4", "openpyxl", "playwright"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    manifest = {"started_utc": utc_now(), "python": platform.python_version(),
                "os": platform.platform(), "packages": versions, "config": config}
    manifest["installed_distributions"] = dict(sorted(
        (dist.metadata["Name"], dist.version) for dist in importlib.metadata.distributions()
        if dist.metadata["Name"]
    ))
    try:
        manifest["git_revision"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent.parent,
            capture_output=True, text=True, timeout=5, check=True
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        manifest["git_revision"] = None
    save_json(logs / "manifest.json", manifest)
    raw, processed, attempts = [], [], []
    seen = {}
    for source in config["sources"]:
        for engine in config["engines"]:
            for attempt in range(1, config["retries"] + 2):
                start = time.monotonic()
                event = {"source_id": source["id"], "engine": engine, "attempt": attempt,
                         "started_utc": utc_now(), "status": None, "error_type": "", "outcome": "error"}
                retry = False
                try:
                    result = fetcher(engine, source, config)
                    event["status"] = result.status
                    rid = f"{source['id']}:{engine}:{attempt}"
                    raw.append({"record_id": rid, "source_id": source["id"], "engine": engine,
                                "requested_url": source["url"], "final_url": result.url,
                                "fetched_utc": utc_now(), "status": result.status,
                                "browser_version": result.browser_version,
                                "html_sha256": hashlib.sha256(result.html.encode("utf-8")).hexdigest(),
                                "html": result.html})
                    if result.status == 200:
                        extracted = extract(result.html, source)
                        duplicate = seen.get(extracted["text_sha256"], "") if extracted["text"] else ""
                        record = {"record_id": rid, "source_id": source["id"], "engine": engine,
                                  "url": result.url, **extracted, "duplicate_of": duplicate}
                        processed.append(record)
                        if extracted["text"] and not duplicate:
                            seen[extracted["text_sha256"]] = rid
                        event["outcome"] = extracted["quality"]
                    else:
                        event["outcome"] = "http_error"
                        retry = result.status in {500, 502, 503, 504}
                except Exception as exc:
                    # В журнал не помещаются тексты исключений с потенциальными секретами URL.
                    event["error_type"] = type(exc).__name__
                    retry = isinstance(exc, (TimeoutError, ConnectionError)) or "Timeout" in type(exc).__name__
                event["elapsed_seconds"] = round(time.monotonic() - start, 3)
                attempts.append(event)
                save_json(logs / "attempts.json", attempts)
                write_xlsx(data / "raw.xlsx", {"raw": raw})
                write_xlsx(data / "processed.xlsx", {"records": processed})
                print(f"{source['id']} / {engine} / {attempt}: {event['outcome']} {event['error_type']}")
                if not retry or attempt > config["retries"]:
                    break
                time.sleep(config["retry_delay_seconds"])
            time.sleep(config["delay_seconds"])
    terminal = {(e["source_id"], e["engine"]): e for e in attempts}
    valid = [r for r in processed if r["quality"] == "ok" and not r["duplicate_of"]]
    diagnostics = {
        "expected_source_engine_pairs": len(config["sources"]) * len(config["engines"]),
        "successful_pairs": sum(e["outcome"] == "ok" for e in terminal.values()),
        "failed_pairs": sum(e["outcome"] != "ok" for e in terminal.values()),
        "raw_records": len(raw), "extracted_records": len(processed), "unique_nonempty_records": len(valid),
        "duplicate_records": sum(bool(r["duplicate_of"]) for r in processed),
        "missing_title": sum(not r["title"] for r in processed),
        "empty_text": sum(not r["text"] for r in processed),
        "variables": {"title": "text", "text": "text", "word_count": "integer", "url": "text"},
        "word_count_min": min((r["word_count"] for r in valid), default=None),
        "word_count_max": max((r["word_count"] for r in valid), default=None),
        "limitations": ["Корреляции и моделирование не выполняются для текстового реестра без заданных исследовательских переменных.",
                         "Сетевое содержимое может меняться между запусками; сохранены исходный HTML и его SHA-256."],
    }
    save_json(logs / "diagnostics.json", diagnostics)
    counts = [{"source_id": r["source_id"], "engine": r["engine"], "words": r["word_count"]} for r in processed]
    save_json(logs / "word_count_report.json", {"records": counts, "unique_total": sum(r["word_count"] for r in valid)})
    words = re.findall(r"[а-яёa-z]+", " ".join(r["text"] for r in valid).lower())
    save_json(logs / "word_frequency_report.json", Counter(words).most_common(50))
    manifest.update(finished_utc=utc_now(), diagnostics=diagnostics)
    manifest["artifacts"] = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted(output.rglob("*")) if p.is_file() and p.name != "manifest.json"}
    save_json(logs / "manifest.json", manifest)
    print("Созданные файлы:")
    for path in sorted(output.rglob("*")):
        if path.is_file():
            print(path)
    return diagnostics
