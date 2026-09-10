"""Archive completed local SDK checks; no test, build, RF or deployment action."""

import gzip
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parent
REPO = ROOT.parents[2]
SOURCES = (
    ("/tmp/leo-fair-admission-regression.xml", "native-regression.xml"),
    ("/tmp/leo-fair-admission-new-final.xml", "new-native-tests.xml"),
    ("/tmp/leo-fair-admission-science.xml", "science-tests.xml"),
    ("/tmp/leo-fair-admission-arm.96zt7Y/libleo-scanner-glrt.so.build.json", "arm-sdk-build.json"),
    (
        "/tmp/leo-fair-sdk-checkpoint.cp5cph/legacy-worker-rejection.json",
        "legacy-worker-rejection.json",
    ),
    ("/tmp/leo-fair-sdk-checkpoint.cp5cph/new-sdk.so.build.json", "desktop-sdk-build.json"),
    (
        "/tmp/leo-fair-sdk-checkpoint.cp5cph/verify_old_worker_rejection.py",
        "original-old-worker-check.py",
    ),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    originals = []
    for name, archived in SOURCES:
        data = Path(name).read_bytes()
        target = ROOT / (archived + ".gz")
        archived_data = gzip.compress(data, mtime=0)
        if target.exists():
            assert target.read_bytes() == archived_data
        else:
            with target.open("xb") as stream:
                stream.write(archived_data)
        record = {"path": target.name, "original_bytes": len(data), "original_sha256": digest(data)}
        if name.endswith(".xml"):
            suites = ET.fromstring(data).findall("testsuite")
            counts = {
                k: sum(int(s.get(k, "0")) for s in suites)
                for k in ("tests", "failures", "errors", "skipped")
            }
            assert counts["tests"] and not any(counts[k] for k in ("failures", "errors", "skipped"))
            record["counts"] = counts
        if name.endswith(".build.json"):
            build = json.loads(data)
            for source, expected in build["sources_sha256"].items():
                assert digest((REPO / source).read_bytes()) == expected
        originals.append(record)
    paths = [p for p in ROOT.iterdir() if p.is_file() and p.name != "index.json"]
    paths += [
        REPO / "src/leo/scanner/native_presence" / name
        for name in ("pool.c", "pool.h", "scanner_glrt.c", "scanner_glrt.h")
    ]
    paths += [
        REPO / "tests/scanner" / name
        for name in (
            "test_native_presence_held_pool.py",
            "test_scanner_glrt_fair_admission.py",
            "test_scanner_glrt_fair_science.py",
        )
    ]
    index = {
        "scope": "Unqualified fair-admission SDK checkpoint; no radio installation or RF",
        "base_revision": "c062e905e57c2981693bf94d2ff4dd9ee169c18d",
        "originals": originals,
        "files": [
            {
                "path": str(p.relative_to(REPO)),
                "bytes": p.stat().st_size,
                "sha256": digest(p.read_bytes()),
            }
            for p in sorted(paths)
        ],
    }
    with (ROOT / "index.json").open("x") as stream:
        json.dump(index, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"files": len(paths), "receipts": len(originals)}))


if __name__ == "__main__":
    main()
