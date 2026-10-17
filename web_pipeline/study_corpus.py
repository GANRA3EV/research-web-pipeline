from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

CASES = [
    {'id': 'static', 'kind': 'static', 'title': 'Статическая страница',
     'expected': 'Карта заблокирована. Клиент просит проверить операцию.', 'delay': None, 'noise': False},
    {'id': 'noise', 'kind': 'static_noise', 'title': 'Страница с навигацией',
     'expected': 'Перевод задержан. Нужно проверить статус платежа.', 'delay': None, 'noise': True},
    {'id': 'dynamic', 'kind': 'javascript', 'title': 'Динамическая страница',
     'expected': 'Данные загружены скриптом. Отображён статус обращения.', 'delay': 0, 'noise': False},
    {'id': 'delayed', 'kind': 'delayed_javascript', 'title': 'Отложенная загрузка',
     'expected': 'Ответ появился после задержки. Статус проверки обновлён.', 'delay': 150, 'noise': False},
]


def page(case):
    import html
    import json
    text = html.escape(case['expected'])
    content = f'<article id="content">{text}</article>' if case['delay'] is None else ''
    script = '' if case['delay'] is None else (
        '<script>setTimeout(() => {const p=document.createElement("article");'
        'p.id="content";p.textContent=' + json.dumps(case['expected'], ensure_ascii=False) +
        ';document.body.appendChild(p);},' + str(case['delay']) + ');</script>')
    noise = '<nav>Главная Каталог Контакты</nav><footer>Служебная информация</footer>' if case['noise'] else ''
    return f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>{case["title"]}</title></head><body>{noise}{content}{script}</body></html>'


@contextmanager
def corpus_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            case = next((c for c in CASES if self.path == '/' + c['id']), None)
            if case is None:
                self.send_error(404)
                return
            payload = page(case).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
