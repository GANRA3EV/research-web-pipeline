"""Командная строка."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from .config import load_config
from .pipeline import run


def main():
    parser = argparse.ArgumentParser(description="Сбор веб-данных в XLSX")
    parser.add_argument("--config", type=Path, default=Path("config/example.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        output = args.output or Path("runs") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        result = run(config, output)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Ошибка параметров или файлов: {exc}\n")
    return 1 if result["failed_pairs"] else 0
