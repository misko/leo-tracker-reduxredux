"""Archive already-completed local tests/builds and generated model products.

No test, build, radio operation, or deployment is started by this collector.
Only research-derived model products are replaced; source snapshots are retained.
"""

import gzip
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parent
REPO = ROOT.parents[2]
PROVIDER = Path("/tmp/leo-cooperative-provider-final.6laOv4")
ARM = Path("/tmp/leo-cooperative-arm-bundle.hRg86q")
MODELS = Path("/tmp/leo-admission-final.v92JQJ")
FIGURES = REPO / "reports/figures/2026_09_10_scanner_provider_admission"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    sources = [
        (Path("/tmp/leo-scanner-admission-tests.xml"), "admission-tests.xml"),
        (Path("/tmp/leo-cooperative-provider-config-final.xml"), "provider-config-tests.xml"),
        (PROVIDER / "network-tests.xml", "fixed-network-tests.xml"),
        (PROVIDER / "adaptive-network-tests.xml", "adaptive-network-tests.xml"),
        (ARM / "receipt.json", "arm-build-receipt.json"),
        (ARM / "local-stage-receipt.json", "arm-local-stage-receipt.json"),
        (ARM / "build_bundle.py", "original-build-bundle.py"),
        (ARM / "exercise_bundle.py", "original-local-stage.py"),
        (
            Path("/tmp/leo-cooperative-provider.tb4MZ0/run_provider.py"),
            "original-provider-recipe.py",
        ),
    ]
    for mode in ("off", "on", "asan"):
        receipt = json.loads((PROVIDER / f"{mode}-receipt.json").read_text())
        assert receipt["passed"] and receipt["synthetic_iq_only"]
        for path, expected in receipt["artifacts"].items():
            assert sha(Path(path).read_bytes()) == expected
        sources.append((PROVIDER / f"{mode}-receipt.json", f"provider-{mode}-receipt.json"))
        for test in (
            "test_scanner_glrt_provider",
            "test_spf_hop_adaptive_native",
            "test_spf_hop_adaptive_policy",
        ):
            sources.append((PROVIDER / f"{mode}-{test}.log", f"{mode}-{test}.log"))
    inventory = []
    for source, name in sources:
        data = source.read_bytes()
        target = ROOT / f"{name}.gz"
        with target.open("xb") as stream:
            stream.write(gzip.compress(data, mtime=0))
        entry = {"path": target.name, "original_sha256": sha(data), "original_bytes": len(data)}
        if source.suffix == ".xml":
            suites = ET.fromstring(data).findall("testsuite")
            counts = {
                key: sum(int(s.get(key, "0")) for s in suites)
                for key in ("tests", "failures", "errors", "skipped")
            }
            assert counts["tests"] > 0 and not any(
                counts[k] for k in ("failures", "errors", "skipped")
            )
            entry["test_counts"] = counts
        inventory.append(entry)
    # These are regenerable research artifacts, not public persisted contracts.
    for source in sorted((MODELS / "results").iterdir()):
        (ROOT / source.name).write_bytes(source.read_bytes())
    for source in sorted((MODELS / "figures").iterdir()):
        (FIGURES / source.name).write_bytes(source.read_bytes())
    paths = [p for p in ROOT.iterdir() if p.is_file() and p.name != "index.json"]
    paths += list(FIGURES.glob("*.png"))
    paths += [
        REPO / "tools/evaluate_scanner_admission.py",
        REPO / "tests/scanner/test_scanner_admission_model.py",
    ]
    index = {
        "scope": "Research checkpoint; no radio runtime installation or RF",
        "provider_revision": "17ee2cbdcf10660dc8a05cd8002b354b0da4b15d",
        "sdk_revision": "5adeed570f728f89eba96c80e58b2783af1fb91a",
        "originals": inventory,
        "files": [
            {
                "path": str(p.relative_to(REPO)),
                "bytes": p.stat().st_size,
                "sha256": sha(p.read_bytes()),
            }
            for p in sorted(paths)
        ],
    }
    with (ROOT / "index.json").open("x") as stream:
        json.dump(index, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"artifacts": len(paths), "archived_originals": len(inventory)}))


if __name__ == "__main__":
    main()
