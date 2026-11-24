"""Verify precision and complete products against each staged named v3 control."""

from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT/"src"), str(ROOT)]

from exact_named_route import bind, digest, read
from held_adaptive_0160_score import verified


ARMS = ("c0", "fitted_c")
RECEIPT = ("run_id", "session_id", "window_count", "counts", "region", "decision", "terminal_sha256")


def parity(named, found):
    before, after = (value["worker"]["receipt"] for value in (named, found))
    owners = {arm: named["rows"].get(arm) == found["rows"].get(arm) for arm in ARMS}
    return dict(complete=before["decision"] == after["decision"] == "complete",
                receipt=all(before[key] == after[key] for key in RECEIPT), terminal=named["terminal"] == found["terminal"],
                authority=named["science"]["raw_authority"] == found["science"]["raw_authority"],
                ordered_owners=all(owners.values()),
                calibration=all(named["science"]["arms"][arm] == found["science"]["arms"][arm] for arm in ARMS),
                objective=named["worker"]["solve"].get("objective_replay") == found["worker"]["solve"].get("objective_replay"),
                layout=named["science"]["scientific_digests"] == found["science"]["scientific_digests"],
                eight_pngs=len(named["products"]["images"]) == 8 and named["products"]["images"] == found["products"]["images"])


def verify(case, root):
    from aperture_trial import write
    from leo.contracts.digests import canonical_digest
    from prospective_0316_solver import owner_delta
    from triage_bounds import calibration_comparison

    bound = read(root/"binding.json")
    enrollment = bound["input"]
    if enrollment != bind(case):
        raise ValueError("Saved input differs from the sealed enrollment")
    request = read(Path(enrollment["request"]))
    original = Path(enrollment["stage"])
    clock, baseline = read(root/"clock.json"), read(original/"stock-clock.json")["timing"]
    if clock["exit_code"]:
        raise ValueError("Candidate process did not complete. Preserve the sealed exit evidence.")
    stock = verified(original/"stock", baseline, f"saved-{case}-worker.json", request)
    candidate = verified(root/"candidate", clock, "worker.json", request)
    if (not stock["trace"]["stock_control"] or not candidate["trace"]["stock_control"]
            or stock["trace"]["machine"] != candidate["trace"]["machine"]
            or stock["sample"]["evaluated_points"] != 179):
        raise ValueError("Expected two genuine standard named publications on the same numerical configuration")
    checks = parity(stock, candidate)
    ports = read(root/"candidate/ports.json")
    science = {mode: dict(arms=report["science"]["arms"]) for mode, report in (("named", stock), ("candidate", candidate))}
    write(root/"result.json", dict(case=request["case"], exact=all(checks.values()), parity=checks, enrollment=bound,
          source_bindings=enrollment["sources"], binding_sha256=digest(root/"binding.json"), exit_sha256=digest(root/"clock.json"),
          clocks=dict(named=baseline, candidate=clock),
          speedup={metric: baseline[metric]/clock[metric] for metric in ("cpu_s", "elapsed_s")},
          geography=calibration_comparison(science, request["case"]), waveform_reads=0, backing_catalogue_reads=0, ports=ports,
          owners={arm: owner_delta(stock["rows"].get(arm, []), candidate["rows"].get(arm, [])) for arm in ARMS},
          ordered_owner_sha256={mode: canonical_digest(data["rows"]) for mode, data in (("named", stock), ("candidate", candidate))},
          artifacts={mode: {key: report[key] for key in ("products", "terminal", "worker", "science")}
                     for mode, report in (("named", stock), ("candidate", candidate))}))


if __name__ == "__main__":
    verify(sys.argv[1], Path(sys.argv[2]))
