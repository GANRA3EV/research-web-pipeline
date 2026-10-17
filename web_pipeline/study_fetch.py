import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time

from .backends import fetch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', required=True)
    parser.add_argument('--url', required=True)
    parser.add_argument('--timeout', type=float, required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    start = time.perf_counter()
    try:
        result = fetch(args.engine, {'url': args.url, 'wait_for_selector': '#content'},
                       {'timeout_seconds': args.timeout, 'headless': True})
        record = {'result': asdict(result), 'error_type': ''}
    except Exception as error:
        record = {'error_type': type(error).__name__, 'error_message': str(error)[:1500]}
    record['fetch_seconds'] = time.perf_counter() - start
    Path(args.output).write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
