"""Poison non-orbital context fields; reconstruct covariance without fitting."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
from algo07_science import engine as e

ROOT = Path(__file__).resolve().parent
REPORT = ROOT.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Forbidden:
    def __getattr__(self, name):
        raise AssertionError("Covariance accessed a forbidden RF/endpoint field: " + name)

    def __getitem__(self, key):
        raise AssertionError("Covariance indexed a forbidden RF/endpoint field")

    def __iter__(self):
        raise AssertionError("Covariance iterated a forbidden RF/endpoint field")


def forbidden(*args, **kwargs):
    raise AssertionError("Covariance called an RF state/likelihood method")


def check(case="FRSH-0001"):
    path = REPORT / "covariance/age_covariance.py"
    spec = importlib.util.spec_from_file_location("independent_age_construction", path)
    covariance = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = covariance
    spec.loader.exec_module(covariance)
    roster = json.loads((REPORT / "evaluation/rf_roster.json").read_text())
    record = next(r for r in roster["cases"] if r["case"] == case)
    source = Path(record["input_path"]).parent.parent
    e.configure(source, ROOT / "construction_runtime")
    e.ROOTS[case[:4]] = source
    d, z, replay = e.load_case(case)
    metadata = dict(case=case, selected_family=record["target_family"])
    _, normal = covariance.candidate_context(d, z, metadata)
    assert normal["status"] == "ready", normal.get("reason")
    scan = copy.copy(d["scan"])
    scan.tracks = Forbidden()
    scan.GPS = scan.ground_truth = scan.position = Forbidden()
    poisoned = dict(d, scan=scan)
    poisoned["problems"] = {}
    for arm, (problem, x) in d["problems"].items():
        p = copy.copy(problem)
        p.scan = scan
        p.values = np.full_like(problem.values, np.nan)
        p.calculate = p.state = forbidden
        poisoned["problems"][arm] = (p, np.full_like(x, np.nan))
    zz = dict(z)
    for field in ("baseline_arms", "baseline_owners", "targets", "eligible_targets",
                  "selected", "gap_selected", "GPS", "ground_truth", "position"):
        zz[field] = Forbidden()
    _, altered = covariance.candidate_context(poisoned, zz, metadata)
    assert altered == normal, "Covariance receipt changed under non-orbital poisoning"
    packet = dict(status="passed", case=case, covariance_source_sha256=sha(path),
        input_path=record["input_path"], input_sha256=sha(record["input_path"]),
        ready=True, pair_count=normal["pair_count"], exact_receipt_equality=True,
        poisoned_fields=["scan.tracks", "problem.values", "problem.calculate", "problem.state",
            "saved position and phase endpoints", "saved owners", "target candidate metadata", "GPS-like fields"],
        legitimate_inputs="TLE/provenance, timestamps, existing physical mode metadata and banks only",
        no_position_optimization=True, no_geographic_truth_read=True,
        baseline_reconstruction_performed=True,
        covariance=normal["coefficient_covariance"])
    output = ROOT / "construction_invariance.json"
    output.write_text(json.dumps(packet, indent=2, allow_nan=False) + "\n")
    print(json.dumps(packet, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--case", default="FRSH-0001")
    check(p.parse_args().case)
