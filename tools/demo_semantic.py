"""Проверяемый пример «локальные страницы → парсинг → классификация».

Обучающие строки и страницы синтетические. Качество на реальных данных не оценивается.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
from threading import Thread


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("runs/semantic-demo"))
    parser.add_argument("--backend", choices=["tfidf", "rubert"], default="tfidf")
    parser.add_argument("--with-summary", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    import joblib
    from triage.models import TicketModel
    from web_pipeline.storage import write_xlsx
    import pandas as pd
    rows = [
        {"text": "Моя карта заблокирована", "primary": "card", "secondary": None, "urgency": "high"},
        {"text": "Блокировка банковской карты", "primary": "card", "secondary": None, "urgency": "high"},
        {"text": "Не проходит перевод денег", "primary": "transfer", "secondary": "card", "urgency": "normal"},
        {"text": "Статус денежного перевода", "primary": "transfer", "secondary": None, "urgency": "normal"},
    ]
    write_xlsx(args.output / "synthetic_training.xlsx", {"synthetic": rows})
    model = TicketModel(["card", "transfer"], backend=args.backend).fit(pd.DataFrame(rows))
    model.encoder = None
    model_path = args.output / "synthetic_model.joblib"
    joblib.dump({"model": model, "threshold": 1.01,
                 "categories": {"card": "Карта", "transfer": "Перевод"}}, model_path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            text = "Моя карта заблокирована. Нужна проверка." if self.path == "/card" else "Хочу узнать статус денежного перевода."
            body = f'<html><head><meta charset="utf-8"></head><body><h1>Синтетический пример</h1><main>{text}</main></body></html>'.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = {"engines": ["curl_cffi"], "delay_seconds": 0, "retries": 0,
              "sources": [{"id": name, "url": f"http://127.0.0.1:{server.server_port}/{name}",
                           "title_selector": "h1", "text_selector": "main"} for name in ("card", "transfer")],
              "analysis": {"model_path": model_path.name,
                           "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
                           "chunk_words": 200, "with_summary": args.with_summary}}
    config_path = args.output / "config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, str(root / "run_all.py"), "--config", str(config_path.resolve()),
                                 "--output", str((args.output / "collection").resolve())])
        if result.returncode:
            raise SystemExit(result.returncode)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    print("Синтетический пример завершён. Созданные файлы:")
    for path in sorted(args.output.rglob("*")):
        if path.is_file():
            print(path)


if __name__ == "__main__":
    main()
