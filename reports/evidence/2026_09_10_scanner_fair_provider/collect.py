"""Archive completed provider/bundle checks, never execute RF or deployment."""

import gzip
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PROVIDER = Path("/tmp/leo-fair-provider.H4jTxK")
BUNDLE = Path("/tmp/leo-fair-arm-bundle.j2s41X")
LIBIIO = Path("/home/mouse9911/gits/libiio-scanner-cooperative-provider")
LIBIIO_REVISION = "b6e692400acd0690767167abc381b0268a640bf7"
PROVIDER_FILES = (
    "iiod/CMakeLists.txt",
    "iiod/spf-scanner-glrt.c",
    "iiod/spf-scanner-glrt.h",
    "tests/README.scanner-glrt-cooperative.md",
    "tests/scanner-glrt-adaptive-fixture.h",
    "tests/test_scanner_glrt_build_config.py",
    "tests/scanner-glrt-worker-delay.c",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=LIBIIO)


def main():
    originals = []
    source = [
        (Path("/tmp/leo-fair-provider-config.xml"), "build-config.xml"),
        (PROVIDER / "network.xml", "network.xml"),
        (PROVIDER / "run_provider.py", "run-provider.py"),
    ]
    summaries = []
    expected_diff = git(
        "diff", LIBIIO_REVISION + "^", LIBIIO_REVISION, "--", *PROVIDER_FILES[:-1]
    ).decode()
    wrapper_sha = digest(git("show", f"{LIBIIO_REVISION}:{PROVIDER_FILES[-1]}"))
    for case in ("off", "fair", "delayed", "asan"):
        receipt = json.loads((PROVIDER / f"{case}-receipt.json").read_bytes())
        assert receipt["passed"] and receipt["synthetic_iq_only"]
        assert receipt["libiio_diff"] == expected_diff
        assert receipt["test_wrapper_sha256"] == wrapper_sha
        for filename, expected in receipt["artifacts"].items():
            assert digest(Path(filename).read_bytes()) == expected
        text = (PROVIDER / f"{case}-test_scanner_glrt_provider.log").read_text()
        lines = [line for line in text.splitlines() if line.startswith("adaptive provider ")]
        assert len(lines) == 14 and all(line.endswith(" PASS") for line in lines)
        rows = [{k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", line)} for line in lines]
        fair = [
            {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", line)}
            for line in text.splitlines()
            if line.startswith("fair provider ")
        ]
        assert len(fair) == (0 if case == "off" else 14)
        summaries.append({"case": case, "provider_scenarios": rows, "admission": fair})
        names = [f"{case}-receipt.json", f"{case}-configure.log", f"{case}-build.log"]
        names += [
            f"{case}-{target}.log"
            for target in (
                "test_scanner_glrt_provider",
                "test_spf_hop_adaptive_native",
                "test_spf_hop_adaptive_policy",
            )
        ]
        source += [(PROVIDER / name, name) for name in names]
    source += [
        (PROVIDER / name, name)
        for name in (
            "sdk.so.build.json",
            "sdk-asan.so.build.json",
            "worker.build.json",
            "worker-delayed.build.json",
        )
    ]
    source += [
        (BUNDLE / name, "arm-" + name)
        for name in (
            "build_bundle.py",
            "exercise_bundle.py",
            "receipt.json",
            "local-stage-receipt.json",
            "configure.json",
            "compile.json",
            "worker-symbols.json",
        )
    ]
    source += [
        (BUNDLE / "release" / name, "arm-" + name)
        for name in (
            "bundle.json",
            "configuration.json",
            "algorithm.json",
            "worker.build.json",
            "libleo-scanner-glrt.so.build.json",
        )
    ]
    assert all(path.is_file() for path, _ in source), "a required gate is not complete"
    for path, _ in source:
        if path.name.endswith(".build.json"):
            build = json.loads(path.read_bytes())
            for filename, expected in build["sources_sha256"].items():
                assert digest((REPO / filename).read_bytes()) == expected
            for filename, expected in build.get("dependencies_sha256", {}).items():
                assert digest(Path(filename).read_bytes()) == expected
    for path, archived in source:
        data = path.read_bytes()
        record = {
            "path": archived + ".gz",
            "original_sha256": digest(data),
            "original_bytes": len(data),
        }
        if path.suffix == ".xml":
            suites = ET.fromstring(data).findall("testsuite")
            counts = {
                key: sum(int(s.get(key, "0")) for s in suites)
                for key in ("tests", "errors", "failures", "skipped")
            }
            assert counts["tests"] > 0 and not any(
                counts[key] for key in ("errors", "failures", "skipped")
            )
            record["counts"] = counts
        with (HERE / record["path"]).open("xb") as stream:
            stream.write(gzip.compress(data, mtime=0))
        originals.append(record)
    for name in PROVIDER_FILES:
        data = git("show", f"{LIBIIO_REVISION}:{name}")
        target = "libiio-" + name.replace("/", "_") + ".gz"
        with (HERE / target).open("xb") as stream:
            stream.write(gzip.compress(data, mtime=0))
        originals.append(
            {"path": target, "original_sha256": digest(data), "original_bytes": len(data)}
        )
    with (HERE / "summary.json").open("x") as stream:
        json.dump(summaries, stream, indent=2)
        stream.write("\n")
    files = [p for p in HERE.iterdir() if p.is_file() and p.name != "index.json"]
    index = {
        "scope": "Synthetic provider and local ARM bundle checks; no radio deployment or RF",
        "libiio_revision": LIBIIO_REVISION,
        "leo_revision": "0eb6ee2f8afa6b8b3317f9e9e40221fba553f0bd",
        "originals": originals,
        "files": [
            {"path": p.name, "bytes": p.stat().st_size, "sha256": digest(p.read_bytes())}
            for p in sorted(files)
        ],
    }
    with (HERE / "index.json").open("x") as stream:
        json.dump(index, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"files": len(files), "originals": len(originals), "scenarios": 56}))


if __name__ == "__main__":
    main()
