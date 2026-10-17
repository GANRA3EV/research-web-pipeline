"""Чтение и проверка параметров до начала сетевых запросов."""
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

ENGINES = {"curl_cffi", "patchright", "camoufox", "clearcote"}


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Корень конфигурации должен быть объектом JSON")
    engines = config.get("engines", ["curl_cffi"])
    if not isinstance(engines, list) or not engines or any(
        not isinstance(e, str) or e not in ENGINES for e in engines
    ):
        raise ValueError("Некорректный список engines")
    if len(engines) != len(set(engines)):
        raise ValueError("Повтор загрузчика в engines")
    sources = config.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Нужен непустой список sources")
    ids = set()
    from bs4 import BeautifulSoup
    from soupsieve import SelectorSyntaxError
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("Каждый источник должен быть объектом JSON")
        sid = source.get("id")
        if not isinstance(sid, str) or not sid or sid in ids:
            raise ValueError("Идентификаторы sources должны быть непустыми и уникальными")
        ids.add(sid)
        source_url = source.get("url")
        if not isinstance(source_url, str) or not source_url:
            raise ValueError(f"Нужен строковый URL источника {sid}")
        url = urlsplit(source_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise ValueError(f"Некорректный HTTP URL источника {sid}")
        for key in ("title_selector", "text_selector", "wait_for_selector"):
            selector = source.get(key)
            if selector is not None:
                if not isinstance(selector, str) or not selector.strip():
                    raise ValueError(f"Некорректный селектор {key}")
                try:
                    BeautifulSoup("", "html.parser").select(selector)
                except SelectorSyntaxError as exc:
                    raise ValueError(f"Некорректный CSS-селектор {key}") from exc
    for key, default in (("timeout_seconds", 30), ("delay_seconds", 1), ("retry_delay_seconds", 2)):
        value = config.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Некорректное число {key}")
        if value < 0 or (key == "timeout_seconds" and value == 0):
            raise ValueError(f"Недопустимое значение {key}")
        config[key] = value
    retries = config.get("retries", 1)
    if isinstance(retries, bool) or not isinstance(retries, int) or not 0 <= retries <= 5:
        raise ValueError("retries должен быть целым числом от 0 до 5")
    if not isinstance(config.get("headless", True), bool):
        raise ValueError("headless должен быть логическим значением")
    config.update(engines=engines, retries=retries)
    if "analysis" in config:
        analysis = config["analysis"]
        if not isinstance(analysis, dict):
            raise ValueError("analysis должен быть объектом JSON")
        model = analysis.get("model_path")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Для анализа нужен model_path")
        digest = analysis.get("model_sha256")
        import re
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise ValueError("Для анализа нужен проверенный model_sha256")
        chunk_words = analysis.get("chunk_words", 200)
        if isinstance(chunk_words, bool) or not isinstance(chunk_words, int) or chunk_words < 1:
            raise ValueError("chunk_words должен быть положительным целым числом")
        if not isinstance(analysis.get("with_llm", False), bool):
            raise ValueError("with_llm должен быть логическим значением")
        if not isinstance(analysis.get("with_summary", False), bool):
            raise ValueError("with_summary должен быть логическим значением")
        if "with_summary" in analysis and "with_llm" in analysis and analysis["with_summary"] != analysis["with_llm"]:
            raise ValueError("with_summary и совместимый параметр with_llm противоречат друг другу")
        model_path = Path(model)
        if not model_path.is_absolute():
            model_path = path.resolve().parent / model_path
        config["analysis"] = {**analysis, "model_path": str(model_path.resolve()),
                              "model_sha256": digest.lower(), "chunk_words": chunk_words}
    return config
