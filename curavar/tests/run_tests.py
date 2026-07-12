"""Zero-dependency test runner (works without pytest)."""
import sys, traceback
import test_acmg, test_ledger, test_io
mods = [test_acmg, test_ledger, test_io]
passed = failed = 0
for m in mods:
    for name in dir(m):
        if name.startswith("test_"):
            try:
                getattr(m, name)(); passed += 1; print(f"  PASS {m.__name__}.{name}")
            except Exception:
                failed += 1; print(f"  FAIL {m.__name__}.{name}"); traceback.print_exc()
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
