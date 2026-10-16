"""Сквозные проверки реального классификатора и связи с источниками."""
import hashlib
import json
from pathlib import Path
import pytest

pytest.importorskip("triage")
import joblib
import pandas as pd
from openpyxl import load_workbook
from triage.models import TicketModel
from web_pipeline.analysis import analyze, load_analyzer
from web_pipeline.config import load_config
from web_pipeline.pipeline import run
from test_pipeline import config as collection_config


@pytest.fixture
def analysis_config(tmp_path):
    data = pd.DataFrame({"text": ["карта заблокирована", "блокировка карты", "перевод денег", "денежный перевод"],
                         "primary": ["card", "card", "transfer", "transfer"],
                         "secondary": [None, None, None, "card"], "urgency": ["high", "high", "normal", "normal"]})
    model = TicketModel(["card", "transfer"]).fit(data)
    path = tmp_path / "model.joblib"
    joblib.dump({"model": model, "threshold": 1.01,
                 "categories": {"card": "Карта", "transfer": "Перевод"}}, path)
    return {"model_path": str(path), "model_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "chunk_words": 200, "with_llm": False}


def sheet_rows(path, sheet):
    book = load_workbook(path)
    rows = list(book[sheet].values)
    return [dict(zip(rows[0], row)) for row in rows[1:]]


def test_real_http_to_classifier(site, analysis_config, tmp_path):
    config = collection_config(site)
    config["analysis"] = analysis_config
    config["sources"].append({**config["sources"][0], "id": "duplicate_url"})
    output = tmp_path / "run"
    result = run(config, output)
    assert result["analysis_status"] == "ok"
    book = output / "data/analysis.xlsx"
    provenance = sheet_rows(book, "provenance")
    predictions = sheet_rows(book, "predictions")
    assert len(provenance) == 2 and len(predictions) == 1
    assert {r["url"] for r in provenance} == {site + "/"}
    assert {r["source_id"] for r in provenance} == {"local", "duplicate_url"}
    assert {r["analysis_id"] for r in provenance} == {predictions[0]["analysis_id"]}
    assert predictions[0]["operator_review"]
    manifest = json.loads((output / "logs/manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["data/analysis.xlsx"]


def test_model_hash_checked_before_requests(site, analysis_config, tmp_path):
    config = collection_config(site)
    config["analysis"] = {**analysis_config, "model_sha256": "0" * 64}
    calls = []
    with pytest.raises(ValueError, match="SHA-256"):
        run(config, tmp_path / "run", lambda *a: calls.append(a))
    assert not calls and not (tmp_path / "run").exists()


def test_cleaned_duplicates_and_chunks(analysis_config, tmp_path):
    cfg = {**analysis_config, "chunk_words": 2}
    bundle = load_analyzer(cfg)
    output = tmp_path / "run"
    (output / "logs").mkdir(parents=True)
    records = [{"record_id": str(i), "quality": "ok", "source_id": str(i), "engine": "curl_cffi",
                "url": f"https://example.com/{i}", "title": "Карта", "text_sha256": str(i),
                "text": f"Карта заблокирована адрес {email}"}
               for i, email in enumerate(["a@example.com", "b@example.com"])]
    report = analyze(records, cfg, bundle, output)
    assert report["unique_documents"] == 1
    assert report["provenance_rows"] == 2
    assert report["chunks"] == 2
    documents = sheet_rows(output / "data/analysis.xlsx", "documents")
    assert "example.com" not in documents[0]["text"]


def test_inference_error_preserves_collection(site, analysis_config, tmp_path, monkeypatch):
    def failure(*args, **kwargs):
        raise RuntimeError("private details")
    monkeypatch.setattr(TicketModel, "predict", failure)
    cfg = collection_config(site)
    cfg["analysis"] = analysis_config
    result = run(cfg, tmp_path / "run")
    assert result["analysis_status"] == "error"
    assert (tmp_path / "run/data/raw.xlsx").exists()
    report = (tmp_path / "run/logs/analysis_report.json").read_text()
    assert "RuntimeError" in report and "private details" not in report


def test_relative_model_path_resolved_from_config(site, analysis_config, tmp_path):
    cfg = collection_config(site)
    cfg["analysis"] = {**analysis_config, "model_path": "model.joblib"}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    assert load_config(path)["analysis"]["model_path"] == analysis_config["model_path"]


def test_optional_summary_is_linked_to_chunk(site, analysis_config, tmp_path, monkeypatch):
    import triage.llm
    calls = []
    def summarize(text, categories):
        calls.append(text)
        return {"status": "draft", "result": {"summary": "Проверка", "evidence": [text]},
                "operator_review": True}
    monkeypatch.setattr(triage.llm, "summarize", summarize)
    cfg = collection_config(site)
    cfg["analysis"] = {**analysis_config, "with_llm": True}
    output = tmp_path / "run"
    assert run(cfg, output)["analysis_status"] == "ok"
    predictions = sheet_rows(output / "data/analysis.xlsx", "predictions")
    assert predictions[0]["draft_status"] == "draft"
    assert len(calls) == 1
    assert json.loads(predictions[0]["draft_json"])["result"]["evidence"] == calls
