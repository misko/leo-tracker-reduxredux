"""Seal completed nominal-beam evidence after verifying corrected launch bindings."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    target = HERE / "evidence-sha256.json"
    if target.exists():
        for name, expected in json.loads(target.read_text()).items():
            assert digest(ROOT / name) == expected, name
        print("Existing evidence index verified")
        return
    paths = {p for p in HERE.iterdir() if p.is_file()}
    for fold in range(6):
        assert (HERE / f"corrected-fold-{fold}-exit-code.txt").read_text().strip() == "0"
        launch = json.loads((HERE / f"corrected-fold-{fold}-launch.json").read_text())
        for name, expected in launch["sha256"].items():
            path = ROOT / name
            assert digest(path) == expected, name
            paths.add(path)
    audit = json.loads((HERE / "audit-results.json").read_text())
    assert audit["status"] == "pass"
    for name, expected in audit["audited_source_sha256"].items():
        assert digest(ROOT / name) == expected, name
    result = {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)}
    with target.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(f"Sealed {len(result)} files")


if __name__ == "__main__":
    main()
