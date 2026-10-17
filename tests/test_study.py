import json

import pytest

from web_pipeline.backends import FetchResult
from web_pipeline.study import isolated_fetch, replay_benchmark, run_benchmark, text_metrics
from web_pipeline.study_corpus import corpus_server


def test_token_metrics_penalize_extra_and_missing_words():
    metric = text_metrics('карта карта перевод', 'карта перевод платёж')
    assert metric['token_precision'] == pytest.approx(2 / 3)
    assert metric['token_recall'] == pytest.approx(2 / 3)
    assert not metric['exact_text']
    assert text_metrics('', 'карта')['token_f1'] == 0


def test_isolated_http_fetch_runs_in_worker(tmp_path):
    with corpus_server() as base:
        result = isolated_fetch('curl_cffi', {'url': base + '/static'}, 5, tmp_path / 'worker.log')
    assert result['error_type'] == ''
    assert result['result']['status'] == 200
    assert 'Карта заблокирована' in result['result']['html']
    assert result['process_seconds'] >= result['fetch_seconds']


def test_benchmark_and_replay_preserve_failures_and_verify_hash(tmp_path):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'engines': ['curl_cffi'], 'repetitions': 2}), encoding='utf-8')
    def fetcher(engine, source, settings):
        if source['url'].endswith('/static'):
            return FetchResult(source['url'], 200, '<title>Статическая страница</title><article id="content">Карта заблокирована. Клиент просит проверить операцию.</article>')
        raise TimeoutError()
    result = tmp_path / 'result'
    assert not run_benchmark(config, result, fetcher=fetcher)
    rows = json.loads((result / 'data' / 'records.json').read_text(encoding='utf-8'))
    assert len(rows) == 8
    assert sum(r['token_f1'] == 1 for r in rows) == 2
    assert replay_benchmark(result, tmp_path / 'replay')
    replay = json.loads((tmp_path / 'replay' / 'data' / 'records.json').read_text(encoding='utf-8'))
    assert [r['token_f1'] for r in rows] == [r['token_f1'] for r in replay]
    snapshot = next(r['snapshot'] for r in rows if r['snapshot'])
    (result / snapshot).write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError, match='SHA-256'):
        replay_benchmark(result, tmp_path / 'tampered')
