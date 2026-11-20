"""Run capped matched compact positions for frozen signal and time-spread policies."""

import argparse
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import save_json
from ..scoring import validate_result
from . import capture_whole_results as whole
from . import field_exact_waveform as field
from . import retry_evidence_trial as trial
from .capture_runtime import checked, read
from .full_v5_check import _sha

CPUS = {trial.CASE1: 16, trial.CASE2: 17}
MODES = (trial.SIGNAL, trial.CONTROL)


def baseline(ident):
    src = trial.selector_waveform if ident == trial.CASE1 else field
    return src.REPORT, src.METHOD


def source(work, ident):
    group = work / ident
    folder, method = baseline(ident)
    predecessor = whole.sealed(folder, "prediction-lock.json")
    locked = checked(folder / "source-lock.json", predecessor["files"]["source-lock.json"])
    original = read(locked)
    for field_ in ("receiver", "receiver_files", "position_limit_s", "original"):
        if field_ not in original:
            raise ValueError(f"position lineage is missing {field_}")
    return dict(
        source_lock_sha256=_sha(locked),
        selector_policy_sha256=_sha(work / "policy-lock.json"),
        selector_receipt_sha256=_sha(group / "selection.json"),
        launcher_sha256=_sha(Path(__file__)),
        baseline_method=method,
        **{k: original[k] for k in ("receiver", "receiver_files", "position_limit_s", "original")},
    )


def run(work, ident):
    group = work / ident
    case, original = whole_iq.binding(ident)
    lock_path = group / "source-lock.json"
    locked = source(work, ident)
    if lock_path.exists():
        if read(lock_path) != locked:
            raise ValueError("sealed solver configuration changed")
    else:
        save_json(lock_path, locked)
    schedule = MODES if ident == trial.CASE1 else MODES[::-1]
    for mode in schedule:
        directory = group / f"position-{mode}"
        factors = checked(group / f"{mode}.json", read(group / "selection.json")["factors"][mode])
        if directory.exists():
            continue
        with patch.object(whole.trial, "IDENT", ident):
            whole.terminal_position(
                group, mode, factors, directory, CPUS[ident], locked, case, original
            )
        print(ident, mode, read(directory / "terminal.json")["exit_code"], flush=True)


def evidence(work, ident):
    group = work / ident
    locked = source(work, ident)
    if read(group / "source-lock.json") != locked:
        raise ValueError("fresh fits used a different compact solver configuration")
    original = locked["original"]
    common = dict(
        id=ident,
        mode="matched-tile",
        cohort="complete retry evidence factors",
        paired_capture_sha256=original["native"]["sha256"],
        original_request_sha256=original["request"]["sha256"],
        catalog_sha256=original["catalog"]["sha256"],
        tile=original["tile"],
    )
    rows, timings = [], {}
    for mode in MODES:
        folder = group / f"position-{mode}"
        terminal = read(folder / "terminal.json")
        checked(folder / "service.log", terminal["log_sha256"])
        plan, raw = (read(folder / name) for name in ("plan.json", "raw.json"))
        request = checked(folder / "recording/request.json", raw["request_sha256"])
        factor = checked(group / f"{mode}.json", read(group / "selection.json")["factors"][mode])
        _, baseline_request = whole_iq.binding(ident)
        whole_iq.verify_request(
            read(request),
            baseline_request,
            native_path=str(factor),
            native_sha256=raw["native_sha256"],
        )
        if (plan["source_lock_sha256"], raw["native_sha256"]) != (
            _sha(group / "source-lock.json"),
            "sha256:" + _sha(factor),
        ):
            raise ValueError("compact terminal changed its frozen native source")
        if terminal["exit_code"]:
            result = dict(
                status="timed_out" if terminal["exit_code"] == 124 else "failed",
                reason="Capped compact solver returned an unsuccessful terminal",
                boundary="Complete original capture support with selected retries",
                metrics={},
                arms={arm: {"latlon": None} for arm in ("c0", "fitted_c")},
            )
            timings[mode] = dict(status=result["status"], wall_s=terminal["wall_s"])
        else:
            end = read(folder / "end.json")
            if (
                end["cpus"] != [CPUS[ident]]
                or end["memory.max"] != whole_iq.MEMORY
                or end["memory.swap.max"]
                or end["memory.swap.current"]
                or end["memory.events.oom_kill"]
            ):
                raise ValueError("fresh compact fit escaped its measured host resource cap")
            result = read(folder / "position.json")
            validate_result(result)
            timings[mode] = dict(status=result["status"], wall_s=terminal["wall_s"], resources=end)
        rows.append(dict(common, method=mode, result=result, native_sha256=_sha(factor)))
    folder, mode = baseline(ident)
    previous = whole.sealed(folder, "prediction-lock.json")
    archive = checked(folder / whole.POS, previous["files"][whole.POS])
    (earlier,) = (r for r in whole.rows_from(archive) if r["id"] == ident and r["method"] == mode)
    if any(earlier[k] != common[k] for k in whole.MINIMAL):
        raise ValueError("preexisting unconditional comparator changed the original request")
    rows.append(dict(earlier, method=trial.ALL, cohort="preexisting full conditional retry fit"))
    return rows, timings


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("case", choices=tuple(CPUS))
    args = parser.parse_args()
    run(args.work, args.case)
