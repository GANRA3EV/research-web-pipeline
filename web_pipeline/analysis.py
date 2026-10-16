"""Связь текстов страниц с классификатором из fintech-triage."""
import hashlib
import json
import math
from pathlib import Path
from .storage import write_xlsx

TRIAGE_REVISION = "7e4868d00dfea39a08d211405cb86f11c2bb8263"


def load_analyzer(config):
    try:
        import joblib
        from triage.models import TicketModel
    except ImportError as exc:
        raise ValueError("Установите зависимости: pip install -e '.[analysis]'") from exc
    path = Path(config["model_path"])
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != config["model_sha256"]:
        raise ValueError("SHA-256 модели не совпадает с конфигурацией")
    # Читаются те же байты, для которых проверена контрольная сумма.
    from io import BytesIO
    try:
        bundle = joblib.load(BytesIO(content))
    except Exception as exc:
        raise ValueError("Не удалось прочитать доверенный файл модели fintech-triage") from exc
    if not isinstance(bundle, dict) or not isinstance(bundle.get("model"), TicketModel):
        raise ValueError("Ожидалась модель TicketModel из fintech-triage")
    threshold = bundle.get("threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0 <= threshold <= 1.01:
        raise ValueError("Некорректный порог в файле модели")
    if not isinstance(bundle.get("categories"), dict) or set(bundle["categories"]) != set(bundle["model"].categories):
        raise ValueError("Категории файла модели не согласованы с классификатором")
    return bundle


def analyze(records, config, bundle, output):
    from triage.preprocessing import clean_text
    from triage.llm import summarize
    documents, provenance, chunks, predictions = [], [], [], []
    seen = {}
    skipped = 0
    for record in records:
        if record["quality"] != "ok":
            skipped += 1
            continue
        cleaned = clean_text(record["text"])
        if not cleaned:
            skipped += 1
            provenance.append({"record_id": record["record_id"], "url": record["url"],
                               "source_id": record["source_id"], "engine": record["engine"],
                               "analysis_id": "", "status": "empty_after_cleaning"})
            continue
        aid = hashlib.sha256(cleaned.casefold().encode("utf-8")).hexdigest()
        provenance.append({"record_id": record["record_id"], "url": record["url"],
                           "source_id": record["source_id"], "engine": record["engine"],
                           "title": record["title"], "source_text_sha256": record["text_sha256"],
                           "analysis_id": aid, "status": "duplicate" if aid in seen else "analyzed"})
        if aid in seen:
            continue
        seen[aid] = record["record_id"]
        documents.append({"analysis_id": aid, "canonical_record_id": record["record_id"],
                          "text": cleaned, "word_count": len(cleaned.split())})
        words = cleaned.split()
        for index, start in enumerate(range(0, len(words), config["chunk_words"]), 1):
            chunks.append({"analysis_id": aid, "chunk_id": f"{aid}:{index}",
                           "chunk_index": index, "text": " ".join(words[start:start + config["chunk_words"]])})
    target = output / "data" / "analysis.xlsx"
    def checkpoint():
        write_xlsx(target, {"documents": documents, "provenance": provenance,
                            "chunks": chunks, "predictions": predictions})
    checkpoint()
    for chunk in chunks:
        result = bundle["model"].predict([chunk["text"]], threshold=bundle["threshold"])[0]
        result = {key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                  for key, value in result.items()}
        prediction = {"analysis_id": chunk["analysis_id"], "chunk_id": chunk["chunk_id"], **result}
        if config.get("with_llm", False):
            draft = summarize(chunk["text"], bundle["categories"])
            prediction["draft_status"] = draft["status"]
            prediction["draft_json"] = json.dumps(draft, ensure_ascii=False)
        predictions.append(prediction)
        checkpoint()
    report = {"input_records": len(records), "unique_documents": len(documents),
              "provenance_rows": len(provenance), "skipped_records": skipped,
              "chunks": len(chunks), "predictions": len(predictions),
              "operator_review_chunks": sum(bool(p["operator_review"]) for p in predictions),
              "model_sha256": config["model_sha256"], "triage_revision": TRIAGE_REVISION,
              "backend": bundle["model"].backend, "threshold": bundle["threshold"],
              "categories": bundle["categories"], "encoder_name": bundle["model"].encoder_name,
              "chunk_words": config["chunk_words"], "with_llm": config.get("with_llm", False),
              "status": "ok" if predictions else "no_analyzable_text",
              "limitations": ["Прогноз относится к фрагменту, метки целого документа не агрегируются.",
                              "Число слов не гарантирует соответствия пределу токенов e5; возможное усечение нужно оценить отдельно.",
                              "Качество на веб-страницах без предметной разметки не оценено."]}
    (output / "logs" / "analysis_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
