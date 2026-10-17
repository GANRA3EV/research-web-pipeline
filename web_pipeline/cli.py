"""Командная строка."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from .config import load_config
from .pipeline import run


def main():
    parser = argparse.ArgumentParser(description="Сбор веб-данных в XLSX")
    parser.add_argument("--config", type=Path, default=Path("config/example.json"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--study-config', type=Path)
    mode.add_argument('--replay', type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.study_config or args.replay:
            from .study import run_benchmark, replay_benchmark
            output = args.output or Path('articles') / datetime.now(timezone.utc).strftime('web_%Y%m%dT%H%M%S%fZ')
            success = replay_benchmark(args.replay, output) if args.replay else run_benchmark(args.study_config, output)
            return 0 if success else 1
        config = load_config(args.config)
        output = args.output or Path("runs") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        result = run(config, output)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Ошибка параметров или файлов: {exc}\n")
    return 1 if result["failed_pairs"] or result.get("analysis_status", "ok") != "ok" else 0
