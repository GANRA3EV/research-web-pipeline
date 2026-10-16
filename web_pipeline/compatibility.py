"""Совместимость закреплённых версий Camoufox и fpgen с путями Windows."""
import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def windows_fpgen_paths():
    if os.name != "nt":
        yield
        return
    # Штатная функция Camoufox сначала проверяет и подготавливает свою модель.
    from camoufox.fpgen_model import load_fpgen
    load_fpgen()
    from fpgen import unpacker
    original = unpacker.IndexedZstdFile

    def unicode_safe(filename, *args, **kwargs):
        if isinstance(filename, (str, Path)) and not str(filename).isascii():
            # Python открывает Unicode-путь; indexed_zstd принимает дескриптор
            # и создаёт собственное отображение файла в память.
            with open(filename, "rb") as source:
                return original(source.fileno(), *args, **kwargs)
        return original(filename, *args, **kwargs)

    unpacker.IndexedZstdFile = unicode_safe
    try:
        yield
    finally:
        unpacker.IndexedZstdFile = original
