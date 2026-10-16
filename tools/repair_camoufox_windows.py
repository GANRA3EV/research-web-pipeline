"""Явное исправление манифеста Windows-сборки Camoufox с резервной копией.

Причина и исходное обсуждение: https://github.com/daijro/camoufox/issues/650
Без --apply выполняется только просмотр предлагаемого изменения.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re


def repaired_bytes(original: bytes) -> bytes:
    blocks = list(re.finditer(rb"<dependency>.*?</dependency>", original, re.DOTALL))
    matching = [b for b in blocks if re.search(rb'name\s*=\s*[\"\x27]mozglue[\"\x27]', b[0])]
    if not matching:
        return original
    if len(matching) != 1:
        raise ValueError("Найдено несколько зависимостей mozglue; автоматическое изменение отклонено")
    block = matching[0]
    return original[:block.start()] + b" " * len(block[0]) + original[block.end():]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if os.name != "nt":
        parser.exit(2, "Исправление предназначено для Windows\n")
    if args.executable:
        path = args.executable.resolve()
    else:
        from camoufox.pkgman import launch_path
        path = Path(launch_path()).resolve()
    original = path.read_bytes()
    if original[:2] != b"MZ" or path.name.lower() != "camoufox.exe":
        raise ValueError("Ожидался PE-файл camoufox.exe")
    fixed = repaired_bytes(original)
    if fixed == original:
        print("Зависимость mozglue в манифесте отсутствует; изменение не нужно")
        return
    print("Файл:", path)
    print("SHA-256 до:", hashlib.sha256(original).hexdigest())
    print("SHA-256 после:", hashlib.sha256(fixed).hexdigest())
    if not args.apply:
        print("Для применения запустите команду с --apply")
        return
    backup = path.with_suffix(".exe.original")
    if backup.exists() and backup.read_bytes() != original:
        raise ValueError("Уже существует отличающаяся резервная копия")
    if not backup.exists():
        backup.write_bytes(original)
    path.write_bytes(fixed)
    report = path.with_suffix(".exe.repair.json")
    report.write_text(json.dumps({"source": "https://github.com/daijro/camoufox/issues/650",
        "before_sha256": hashlib.sha256(original).hexdigest(),
        "after_sha256": hashlib.sha256(fixed).hexdigest(), "backup": str(backup)}, indent=2), encoding="utf-8")
    print("Созданные файлы:", path, backup, report, sep="\n")


if __name__ == "__main__":
    main()
