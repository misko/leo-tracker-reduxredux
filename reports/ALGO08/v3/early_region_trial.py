"""Run early regional evidence on the three sealed mixed-aperture availability inputs."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from aperture_trial import read, write
from early_region import preflight
from full_family_amortized_trial import run as fit
from mixed_aperture_availability import prepare
from sparse_consensus_trial import CASES


HERE = Path(__file__).resolve().parent
SOURCE = "55a2a50b7025b39eff4f243e3eae972a64f8f24f838e7779c386a030de9b345f"


def control():
    blob = (HERE / "measurements/mixed-aperture-availability.json.gz").read_bytes()
    if sha256(blob).hexdigest() != SOURCE:
        raise ValueError("Saved availability comparison changed")
    return json.loads(gzip.decompress(blob))


def run(case, output):
    base = control()[case]
    audit, counts = [], {}
    def scope():
        from leo.operations.tle_archive import TleArchiveReader
        return preflight(TleArchiveReader(Path(base["identity"]["archive"]["root"])), audit, counts)

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "solver.json"
        fit(case, "control", path, load_saved_inputs=prepare,
            evidence_context=scope)
        row = read(path)
    entry, = audit
    stopped = bool(entry["result"].get("complete") and entry["result"].get("would_withhold"))
    if (len(row["attempts"]) != int(not stopped)
            or stopped and (row["status"] != "withheld" or row["reason"] != "both_receivers_support_far_exterior")):
        raise ValueError("Expected one regional check followed by exactly its declared route")
    if any(row["identity"][k] != base["identity"][k] for k in ("native_sha256", "archive", "offer", "graph_parameters")):
        raise ValueError("Early proof changed the saved detector or causal input")
    row.update(preflight=audit, catalogue=counts)
    write(output, row)


def score(directory, output, archive):
    baseline = control()
    rows = {case: read(directory / f"{case}.json") for case in CASES}
    compared = {}
    for case, row in rows.items():
        old = baseline[case]
        entry, = row["preflight"]
        same = {key: row.get(key) == old.get(key) for key in ("arms", "associated", "owners", "science", "grid_points")}
        proved = (row["reason"] == "both_receivers_support_far_exterior" and row["status"] == "withheld"
                  and entry["result"].get("complete") is True and entry["result"].get("would_withhold") is True)
        compared[case] = dict(cpu_s=row["cpu_s"], elapsed_s=row["elapsed_s"], original_cpu_s=old["cpu_s"],
                              original_elapsed_s=old["elapsed_s"], original_status=old["status"], status=row["status"],
                              reason=row["reason"], ranks=len(row["ranks"]), original_ranks=len(old["ranks"]),
                              attempts=[a["decision"] for a in row["attempts"]], original_attempts=[a["decision"] for a in old["attempts"]],
                              preflight=entry, catalogue=row["catalogue"], same_science=same,
                              passed=proved if case == "south-far" else row["status"] == "ok" and all(same.values()))
    write(output, dict(control_sha256=SOURCE, cases=compared))
    with archive.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(rows, separators=(",", ":"), allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    job = commands.add_parser("run")
    job.add_argument("case", choices=CASES)
    job.add_argument("output", type=Path)
    scorer = commands.add_parser("score")
    for name in ("directory", "output", "archive"):
        scorer.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    (run if args.pop("action") == "run" else score)(**args)
