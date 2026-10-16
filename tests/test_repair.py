"""Проверка узкого изменения манифеста без запуска сторонних программ."""
from tools.repair_camoufox_windows import repaired_bytes


def test_only_mozglue_dependency_removed():
    common = b'<dependency><name value="common-controls"/></dependency>'
    glue = b'<dependency><dependentAssembly><assemblyIdentity name="mozglue"/></dependentAssembly></dependency>'
    original = b"MZ-prefix" + common + glue + b"suffix"
    repaired = repaired_bytes(original)
    assert len(original) == len(repaired)
    assert repaired == b"MZ-prefix" + common + b" " * len(glue) + b"suffix"
    assert repaired_bytes(repaired) == repaired
