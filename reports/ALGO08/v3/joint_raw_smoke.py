"""One matched raw-to-standard-publication pair on the small southern development waveform."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from time import perf_counter

from leo.storage.fast_scan import FastScanStore
from tools.pipeline_eval.qualification import cache_residency as cache
from tools.pipeline_eval.qualification import paired_publication as pairs
from aperture_trial import BENCH, PAYLOAD, RELEASE, archive_identity, machine
from joint_publication import artifacts


HERE = Path(__file__).resolve().parent
SOURCE = BENCH / "exact-curved-lookahead-south-inside/pair.json"


def run(output):
    if sha256(SOURCE.read_bytes()).hexdigest() != "48fed3c62639ef81fb99e4b76921bcacd999e769a78ebb607b2b886b6f0951f0":
        raise ValueError("Southern development assignment changed")
    source = json.loads(SOURCE.read_bytes())
    recording, archive, region = Path(source["recording"]), Path(source["archive"]["root"]), Path(source["region"])
    if archive_identity(archive) != source["archive"]:
        raise ValueError("Southern causal archive changed")
    system = machine()
    if system["cpu"] != [2] or system["nice"] < 15 or any(n != "1" for n in system["threads"].values()):
        raise ValueError("Expected one low-priority numerical core")
    pairs.verified_v3(pairs.NAMED_V3)
    output.mkdir(exist_ok=False)
    store = FastScanStore(output)
    _, _, inventory = store.inventory(recording, verify_windows=False)
    pins = [(Path(r["path"]) / "manifest.json", r["manifest_digest"]) for r in inventory["segments"]]
    query_file = BENCH / "ds30-cache-residency.so"
    if sha256(query_file.read_bytes()).hexdigest() != "4f10e0a2e23121e184ee7d37767f55c29fefc158f4182a2dd99c4268ff2ce6ab":
        raise ValueError("Unexpected cache probe")
    probe = cache.load_query(query_file)
    args = ["--recording", str(recording), "--region", str(region), "--archive", str(archive)]
    runs = {}
    for arm in ("candidate", "baseline"):
        root = output / arm
        if arm == "baseline":
            root.mkdir()
            cmd = [str(pairs.NAMED_V3), *args, "--bulk-root", str(root)]
        else:
            cmd = [str(RELEASE / "venv/bin/python"), "-BPs", str(HERE / "joint_publication.py"),
                   *args, "--output", str(root)]
        environment = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (HERE, PAYLOAD, RELEASE / "src", RELEASE))))
        snapshot = cache.bound_snapshot(store, recording, tuple(pins), os.sysconf("SC_PAGE_SIZE"), probe)
        start = pairs.child_usage()
        clock = perf_counter()
        result = subprocess.run(cmd, env=environment, check=True, capture_output=True, text=True, timeout=100)
        wall = perf_counter() - clock
        use = {k: v - start[k] for k, v in pairs.child_usage().items()}
        if arm == "baseline":
            receipt = json.loads(result.stdout)
            pairs.verify_v3_publication(root, receipt)
        else:
            study = json.loads((root / "joint-research-receipt.json").read_bytes())
            if study["route"] != "complete" or study["input"] != "raw recording":
                raise ValueError("The research solve did not publish directly from raw I/Q")
            receipt = study["receipt"]
        measured = pairs.evidence(root, receipt, started_ns=0, read_only=True)
        native_file, = (root / "fast-scan-automatic-work").glob("*/detections.json")
        runs[arm] = dict(elapsed_s=wall, **use, cache=snapshot, receipt=receipt, arms=measured["arms"],
                         raw_authority=measured["raw_authority"], native_file_sha256=sha256(native_file.read_bytes()).hexdigest(),
                         evidence=artifacts(root, receipt))
    original = source["runs"]["candidate"]
    if runs["baseline"]["arms"] != original["arms"]:
        raise ValueError("Fresh v3 differs from the archived solver")
    for r in runs.values():
        if r["raw_authority"] != original["raw_authority"] or r["receipt"]["region"] != original["receipt"]["region"]:
            raise ValueError("Raw input or supplied region changed")
    if runs["baseline"]["native_file_sha256"] != runs["candidate"]["native_file_sha256"]:
        raise ValueError("The two pipelines consumed different detections")
    (output / "pair.json").write_text(json.dumps(dict(machine=system, archive=source["archive"],
        source_pair_sha256=sha256(SOURCE.read_bytes()).hexdigest(), region_sha256=sha256(region.read_bytes()).hexdigest(),
        order=list(runs), runs=runs), indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
