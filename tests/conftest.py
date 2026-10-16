"""Локальный сервер с проверяемыми страницами."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import pytest


@pytest.fixture
def site():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/blocked":
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Forbidden")
                return
            body = """<!doctype html><html><head><meta charset="utf-8"><title>Проверка</title></head>
            <body><h1>Научные данные</h1><main><p>Проверяемый текст для сбора.</p></main>
            <script>document.querySelector('main').insertAdjacentHTML('beforeend',
            '<p id="dynamic">Динамический фрагмент.</p>');</script></body></html>""".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()
