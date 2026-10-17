from collections import Counter
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import random
import re
import statistics
import time
import os
import subprocess
import sys
import tempfile

from .backends import fetch, FetchResult
from .config import ENGINES
from .extract import extract
from .pipeline import save_json
from .storage import write_xlsx
from .study_corpus import CASES, corpus_server, page


def text_metrics(actual, expected):
    tokens = lambda value: re.findall(r'\w+', value.casefold())
    actual_tokens, expected_tokens = Counter(tokens(actual)), Counter(tokens(expected))
    overlap = sum((actual_tokens & expected_tokens).values())
    precision = overlap / sum(actual_tokens.values()) if actual_tokens else 0.
    recall = overlap / sum(expected_tokens.values()) if expected_tokens else 0.
    return {'token_precision': precision, 'token_recall': recall,
            'token_f1': 2 * precision * recall / (precision + recall) if precision + recall else 0.,
            'exact_text': ' '.join(actual.split()) == ' '.join(expected.split())}


def isolated_fetch(engine, source, timeout, log_path):
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / 'result.json'
        command = [sys.executable, '-m', 'web_pipeline.study_fetch', '--engine', engine,
                   '--url', source['url'], '--timeout', str(timeout), '--output', str(target)]
        started = time.perf_counter()
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace',
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, timeout=timeout + 60,
            cwd=Path(__file__).resolve().parents[1])
        log_path.write_text(result.stdout + result.stderr, encoding='utf-8')
        if result.returncode or not target.exists():
            raise RuntimeError('Изолированный процесс загрузчика завершился без результата')
        record = json.loads(target.read_text(encoding='utf-8'))
        record['process_seconds'] = time.perf_counter() - started
        return record


def summarize(rows):
    result = []
    groups = sorted({(r['engine'], r['kind']) for r in rows})
    for engine, kind in groups:
        subset = [r for r in rows if (r['engine'], r['kind']) == (engine, kind)]
        successes = [r for r in subset if r['http_status'] == 200]
        times = sorted(r['fetch_seconds'] for r in successes if r['fetch_seconds'] is not None)
        result.append({'engine': engine, 'kind': kind, 'attempts': len(subset),
            'http_success_fraction': len(successes) / len(subset),
            'nonempty_fraction': sum(r['nonempty'] for r in subset) / len(subset),
            'mean_token_f1_all_attempts': statistics.mean(r['token_f1'] for r in subset),
            'exact_fraction': sum(r['exact_text'] for r in subset) / len(subset),
            'median_fetch_seconds_http200': statistics.median(times) if times else None,
            'min_fetch_seconds_http200': min(times) if times else None,
            'max_fetch_seconds_http200': max(times) if times else None})
    return result


def new_output(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    for name in ('article', 'data', 'tables', 'figures', 'code', 'references', 'logs', 'kb_context'):
        (output / name).mkdir()
    (output / 'data' / 'snapshots').mkdir()
    return output


def save_results(root, rows, protocol):
    summary = summarize(rows)
    write_xlsx(root / 'tables' / 'benchmark.xlsx', {'attempts': rows, 'summary': summary})
    save_json(root / 'data' / 'records.json', rows)
    save_json(root / 'logs' / 'protocol.json', protocol)
    write_xlsx(root / 'tables' / 'coverage.xlsx', {'coverage': [
        {'component': 'Данные', 'evidence': 'data/corpus.json', 'limitation': 'Локальные синтетические страницы'},
        {'component': 'Методы', 'evidence': 'logs/protocol.json', 'limitation': 'Один селектор и фиксированный набор случаев'},
        {'component': 'Результаты', 'evidence': 'tables/benchmark.xlsx', 'limitation': 'Не характеризуют внешние сайты'},
        {'component': 'Источники', 'evidence': 'logs/protocol.json', 'limitation': 'Библиографический обзор не выполнялся'}]})
    report = '\n'.join(['# Проверка извлечения текста', '',
        'В табл. 1 файла tables/benchmark.xlsx приведены результаты повторных запусков.',
        'Точность и полнота рассчитаны по мультимножествам слов; порядок слов не учитывается.',
        'Пустой результат и ошибка загрузчика получают нулевой F1.',
        'Время включает запуск браузера и ожидание селектора. Первая загрузка может включать скачивание браузера.',
        'Сохранены минимум, медиана и максимум длительности успешных HTTP-запросов.',
        'Локальный синтетический корпус не подтверждает качество и скорость на внешних сайтах.',
        'Повторное извлечение из снимков DOM не повторяет исполнение JavaScript.', ''])
    (root / 'article' / 'report.md').write_text(report, encoding='utf-8')
    save_json(root / 'logs' / 'word_count_report.json', {'report_words': len(report.split())})
    save_json(root / 'logs' / 'artifacts.json', {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob('*') if p.is_file()})
    print('Созданные файлы:')
    for path in sorted(root.rglob('*')):
        if path.is_file():
            print(path)


def run_benchmark(config_path, output, fetcher=fetch):
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    engines, repeats = config['engines'], config.get('repetitions', 3)
    if not engines or len(engines) != len(set(engines)) or set(engines) - ENGINES:
        raise ValueError('Нужен непустой список уникальных загрузчиков')
    if not isinstance(repeats, int) or not 2 <= repeats <= 20:
        raise ValueError('Число повторений должно находиться между 2 и 20')
    timeout = config.get('timeout_seconds', 15)
    if not isinstance(timeout, (float, int)) or not 0 < timeout <= 120:
        raise ValueError('Время ожидания должно находиться между 0 и 120 секундами')
    root = new_output(output)
    save_json(root / 'data' / 'corpus.json', CASES)
    save_json(root / 'code' / 'config.json', config)
    for case in CASES:
        (root / 'data' / f"{case['id']}_source.html").write_text(page(case), encoding='utf-8')
    jobs = [(repeat, case, engine) for repeat in range(1, repeats + 1) for case in CASES for engine in engines]
    random.Random(config.get('seed', 42)).shuffle(jobs)
    rows = []
    with corpus_server() as base:
        for position, (repeat, case, engine) in enumerate(jobs, 1):
            source = {'url': base + '/' + case['id'], 'text_selector': '#content',
                      'title_selector': 'title', 'wait_for_selector': '#content'}
            row = {'order': position, 'repeat': repeat, 'case_id': case['id'], 'kind': case['kind'],
                   'engine': engine, 'url': source['url'], 'http_status': None, 'error_type': '',
                   'snapshot': '', 'html_sha256': '', 'browser_version': '',
                   'fetch_seconds': None, 'process_seconds': None, 'extraction_seconds': None, 'nonempty': False,
                   'expected': case['expected'], 'text': '', 'title_correct': False,
                   **text_metrics('', case['expected'])}
            start = time.perf_counter()
            try:
                if fetcher is fetch:
                    isolated = isolated_fetch(engine, source, timeout, root / 'logs' / f'fetch_{position:04d}.log')
                    row.update(fetch_seconds=isolated['fetch_seconds'], process_seconds=isolated['process_seconds'])
                    if isolated['error_type']:
                        row.update(error_type=isolated['error_type'])
                        (root / 'logs' / f'error_{position:04d}.txt').write_text(isolated.get('error_message', ''), encoding='utf-8')
                        rows.append(row)
                        save_json(root / 'data' / 'records.json', rows)
                        print(f"{position}/{len(jobs)}: {engine} / {case['id']} / {row['error_type']}", flush=True)
                        continue
                    result = FetchResult(**isolated['result'])
                else:
                    result = fetcher(engine, source, {'timeout_seconds': timeout, 'headless': True})
                    row['fetch_seconds'] = time.perf_counter() - start
                row.update(http_status=result.status,
                           browser_version=result.browser_version)
                snapshot = f'data/snapshots/{position:04d}.html'
                (root / snapshot).write_text(result.html, encoding='utf-8')
                row.update(snapshot=snapshot, html_sha256=hashlib.sha256((root / snapshot).read_bytes()).hexdigest())
                if result.status == 200:
                    start_extract = time.perf_counter()
                    extracted = extract(result.html, source)
                    row.update(extraction_seconds=time.perf_counter() - start_extract,
                               nonempty=bool(extracted['text']), text=extracted['text'],
                               title_correct=extracted['title'] == case['title'], **text_metrics(extracted['text'], case['expected']))
            except Exception as error:
                row.update(error_type=type(error).__name__)
                if row['fetch_seconds'] is None:
                    row['fetch_seconds'] = time.perf_counter() - start
            rows.append(row)
            save_json(root / 'data' / 'records.json', rows)
            print(f"{position}/{len(jobs)}: {engine} / {case['id']} / F1={row['token_f1']:.3f} {row['error_type']}", flush=True)
    protocol = {'question': 'Влияние загрузчика и типа страницы на извлечение текста', 'config': config,
        'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')},
        'python': platform.python_version(), 'packages': {d.metadata['Name']: d.version
            for d in importlib.metadata.distributions() if d.metadata['Name']},
        'retries': 0, 'isolation': 'Отдельный процесс для каждой попытки; fetch_seconds не включает импорт и запуск Python',
        'order': 'Все сочетания перемешаны генератором с фиксированным seed',
        'primary_metric': 'mean_token_f1_all_attempts', 'mode': 'live_local_synthetic',
        'limitations': ['Скачивание браузера может входить в первый запуск', 'Память и нагрузка системы не измерены',
                        'Ошибки и пустые результаты остаются в знаменателе качества']}
    save_results(root, rows, protocol)
    return not any(r['error_type'] or r['http_status'] != 200 for r in rows)


def replay_benchmark(previous, output):
    previous = Path(previous).resolve()
    rows = json.loads((previous / 'data' / 'records.json').read_text(encoding='utf-8'))
    root = new_output(output)
    cases = json.loads((previous / 'data' / 'corpus.json').read_text(encoding='utf-8'))
    save_json(root / 'data' / 'corpus.json', cases)
    for row in rows:
        if not row['snapshot']:
            continue
        snapshot = (previous / row['snapshot']).resolve()
        if not snapshot.is_relative_to(previous) or hashlib.sha256(snapshot.read_bytes()).hexdigest() != row['html_sha256']:
            raise ValueError('Снимок не прошёл проверку пути или SHA-256')
        payload = snapshot.read_text(encoding='utf-8')
        destination = (root / row['snapshot']).resolve()
        if not destination.is_relative_to(root):
            raise ValueError('Путь снимка выходит за папку результата')
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(snapshot.read_bytes())
        if row['http_status'] == 200:
            start = time.perf_counter()
            extracted = extract(payload, {'text_selector': '#content', 'title_selector': 'title'})
            case = next(c for c in cases if c['id'] == row['case_id'])
            row.update(extraction_seconds=time.perf_counter() - start, text=extracted['text'],
                       nonempty=bool(extracted['text']), title_correct=extracted['title'] == case['title'],
                       **text_metrics(extracted['text'], row['expected']))
    protocol = {'mode': 'offline_replay', 'source_records_sha256': hashlib.sha256(
        (previous / 'data' / 'records.json').read_bytes()).hexdigest(),
        'limitations': ['fetch_seconds сохранено из исходного запуска; сеть и браузеры не запускались']}
    save_results(root, rows, protocol)
    return True
