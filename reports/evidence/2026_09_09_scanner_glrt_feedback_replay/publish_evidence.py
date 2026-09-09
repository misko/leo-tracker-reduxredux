"""Archive bounded offline receipts, excluding all IQ and executable artifacts."""

import gzip
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = Path("/tmp/leo-sdk-feedback.MD8dVh")
OUTPUT = Path(__file__).parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    summary = json.loads((RAW / "saved-replay-final/saved-summary.json").read_text())
    assert summary["unchanged_inputs"]
    assert all(r["verified"] and r["results"] == r["observations"] for r in summary["checks"])
    suite = ET.parse(RAW / "regression.xml").getroot().find("testsuite")
    assert suite is not None and suite.attrib["tests"] == "961"
    assert all(suite.attrib[k] == "0" for k in ("failures", "errors", "skipped"))
    selected = [
        RAW / name
        for name in (
            "run_saved_replay.py",
            "run_saved_replay.initial.py",
            "run_saved_replay.pre-permission-fix.py",
            "run_sanitizers.py",
            "run_sanitizers.initial.py",
            "initial-tests.log",
            "initial-tests.xml",
            "regression.log",
            "regression.xml",
            "saved-run.log",
            "saved-run-corrected.log",
            "saved-run-final.log",
            "sanitizers.log",
            "sanitizers-final.log",
            "arm-cross-build.log",
        )
    ]
    for directory in (
        "saved-replay",
        "saved-replay-final",
        "sanitized",
        "sanitized-final",
        "arm-cross-build",
    ):
        selected.extend(
            p
            for p in (RAW / directory).rglob("*")
            if p.is_file() and (p.suffix in (".json", ".jsonl", ".stderr"))
        )
    selected.extend(
        p
        for p in RAW.glob("sanitized-*")
        if p.is_file() and (p.suffix in (".json", ".jsonl", ".stderr"))
    )
    for rate in (2500000, 5000000):
        checked = json.loads((RAW / f"sanitized-final-{rate}.verification.json").read_text())
        assert checked["verified"] and checked["results"] == checked["observations"] == 16
    artifacts = {}
    for path in sorted(set(selected)):
        if path.name.endswith(".build.json"):
            receipt = json.loads(path.read_text())
            binary = path.with_name(path.name.removesuffix(".build.json"))
            assert sha(binary) == receipt["binary_sha256"]
            for name, expected in receipt["sources_sha256"].items():
                assert sha(ROOT / name) == expected, name
            for name, expected in receipt.get("dependencies_sha256", {}).items():
                assert sha(Path(name)) == expected, name
        relative = path.relative_to(RAW)
        destination = OUTPUT / (str(relative) + ".gz")
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = path.read_bytes()
        encoded = gzip.compress(content, mtime=0)
        with destination.open("xb") as stream:
            stream.write(encoded)
        artifacts[str(destination.relative_to(OUTPUT))] = dict(
            sha256=sha(destination),
            original_sha256=hashlib.sha256(content).hexdigest(),
            original_bytes=len(content),
            source=str(path),
        )
    sources = {
        name: sha(ROOT / name)
        for name in (
            "tools/scanner_glrt_sdk_replay.c",
            "tools/qualify_scanner_glrt_sdk.py",
            "tests/scanner/test_glrt_sdk_replay.py",
            "src/leo/scanner/native_presence/scanner_glrt.c",
            "src/leo/scanner/native_presence/scanner_glrt.h",
            "src/leo/scanner/native_presence/frame_result.c",
            "src/leo/scanner/native_presence/adaptive_scan.h",
            str(Path(__file__).relative_to(ROOT)),
        )
    }
    with (OUTPUT / "index.json").open("x") as stream:
        json.dump(
            dict(
                base_commit="ab10f587",
                scope="desktop saved-IQ feedback parity; no ARM/RF/deployment",
                artifacts=artifacts,
                sources_sha256=sources,
                tests=suite.attrib,
                original_saved_corpus_index="reports/evidence/2026_09_08_arm_presence_symbol_support/index.json",
            ),
            stream,
            indent=2,
        )
        stream.write("\n")
    print(json.dumps(dict(artifacts=len(artifacts), source_hashes=len(sources))))


if __name__ == "__main__":
    main()
