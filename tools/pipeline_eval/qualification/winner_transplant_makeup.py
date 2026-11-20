"""Finish only winner-transplant cells excluded by the primary last-start horizon."""

import argparse
import gzip
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from . import screening_figures
from . import winner_transplant_results as results
from . import winner_transplant_trial as trial
from .bracketed_position import check_release
from .full_held_scores import held_references
from .full_v5_check import _sha
from .margin_admission_results import sealed
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file
from .support_cross_results import resources

REPORT = trial.REPORT / "makeup"
PREFIX = "winner_transplant_makeup_"
read = whole_iq.read


def run(primary_work, work):
    rows = sealed(trial.REPORT, "prediction-lock.json", "predictions.jsonl.gz")
    original = read(trial.REPORT / "plan.json")
    check_release(original)
    missing = [r for r in rows if r["terminal"] == "not-launched"]
    if not missing:
        print("all primary cells launched")
        return
    if any(
        r["result"]["reason"] != "prospective wall-time launch horizon reached" for r in missing
    ):
        raise ValueError("the make-up only covers documented primary scheduling exclusions")
    witness = {(r["id"], r["condition"]): r for r in original["schedule"]}
    if (REPORT / "plan.json").exists():
        raise FileExistsError("the winner-transplant make-up plan already exists")
    work.mkdir(exist_ok=False)
    actions = []
    for row in missing:
        ident, mode = row["id"], row["condition"]
        action = witness[ident, mode]
        primary = (primary_work / ident / mode).resolve()
        target = work / ident / mode
        target.mkdir(parents=True)
        (target / "recording").symlink_to(primary / "recording", target_is_directory=True)
        whole_iq.checked(target / "recording/native.json", action["native_sha256"])
        whole_iq.checked(target / "recording/request.json", action["prepared_request_sha256"])
        for file in ("plan.json", "raw.json"):
            write(target / file, (primary / file).read_bytes())
        actions.append(
            dict(
                action,
                method=PREFIX + mode,
                primary_method=action["method"],
                primary_status=row["result"]["status"],
                primary_reason=row["result"]["reason"],
            )
        )
    save_json(
        REPORT / "plan.json",
        dict(
            schedule=actions,
            cases=sorted({r["id"] for r in actions}),
            primary_lock_sha256=_sha(trial.REPORT / "prediction-lock.json"),
            source_sha256=_sha(Path(__file__)),
            **{k: original[k] for k in ("memory_bytes", "swap_bytes", "service_limit_s")},
        ),
    )
    print("make-up lock", _sha(REPORT / "plan.json"), flush=True)

    def lane(cpu):
        return [trial.runner.service(work, r) for r in actions if r["cpu"] == cpu]

    with ThreadPoolExecutor(len(trial.LANES)) as pool:
        outcomes = [r for group in pool.map(lane, trial.LANES) for r in group]
    write(REPORT / "predictions.jsonl.gz", compressed_rows(outcomes))
    save_json(
        REPORT / "prediction-lock.json",
        dict(files={name: _sha(REPORT / name) for name in ("plan.json", "predictions.jsonl.gz")}),
    )


def publish(work):
    candidates = sealed(REPORT, "prediction-lock.json", "predictions.jsonl.gz")
    plan = read(REPORT / "plan.json")
    whole_iq.checked(trial.REPORT / "prediction-lock.json", plan["primary_lock_sha256"])
    expected = {(row["id"], row["condition"]): row for row in plan["schedule"]}
    if len(candidates) != len(expected):
        raise ValueError("make-up output did not preserve all scheduled cells")
    _, _, stock, five = trial.load_controls()
    combined = []
    for row in candidates:
        ident, condition = row["id"], row["condition"]
        planned = expected.pop((ident, condition))
        if any(row[k] != v for k, v in planned.items()):
            raise ValueError("make-up changed the predetermined input or assignment")
        path = work / ident / condition
        if read(path / "attempt.json") != row:
            raise ValueError("a make-up publication differs from the service receipt")
        log = whole_iq.checked(path / "service.log", row["log_sha256"])
        write(REPORT / f"{ident}-{condition}.log.gz", gzip.compress(log.read_bytes(), mtime=0))
        resource = row.get("position_resources") or {}
        for edge in ("start", "end"):
            if resource and (
                resource[edge]["cpus"] != [row["cpu"]]
                or resource[edge]["memory.max"] != plan["memory_bytes"]
                or resource[edge]["memory.swap.max"] != plan["swap_bytes"]
                or resource[edge]["memory.swap.current"] != 0
            ):
                raise ValueError("the make-up left the original resource boundary")
        combined.append(row)
        for other in (stock[ident], five[ident]):
            combined.append(
                dict(
                    other,
                    makeup_condition=condition,
                    stock_native_sha256=stock[ident]["native_sha256"],
                    fifth_native_sha256=five[ident]["native_sha256"],
                )
            )
    ids = sorted({r["id"] for r in candidates})
    _, references = held_references(None, ids)
    scores = results.scoring(combined, {r["id"]: r for r in references})
    csv_file(REPORT / "scores.csv", scores)
    csv_file(REPORT / "resources.csv", resources(candidates))
    for mode in sorted({r["condition"] for r in candidates}):
        figure(mode, combined)


def figure(mode, combined):
    active = [r for r in combined if r.get("condition") == mode and r["method"] == PREFIX + mode]
    controls = [r for r in combined if r.get("makeup_condition") == mode]
    cases = sorted({r["id"] for r in active})
    out = REPORT / mode
    write(out / "positions.jsonl.gz", compressed_rows(active + controls))
    for name in ("prediction-lock.json", "scores.csv", "resources.csv"):
        write(out / name, (REPORT / name).read_bytes())
    names = ("positions.jsonl.gz", "prediction-lock.json", "scores.csv", "resources.csv")
    save_json(out / "figure-lock.json", dict(cases=cases, files={n: _sha(out / n) for n in names}))

    def series(key, method, label):
        return dict(
            key=key,
            label=label,
            value=method,
            file=names[0],
            native_field="paired_capture_sha256",
            match=["catalog_sha256", "original_request_sha256", "stock_native_sha256", "tile"],
        )

    panel = dict(
        id="winner-transplant-makeup-" + mode.replace("_", "-"),
        method=PREFIX + mode,
        scope="roof",
        title="Winner transplant after the primary launch horizon",
        caption=(
            "Separate make-up of the original sealed diagnostic input. "
            "The original panel retains its terminal scheduling exclusion. "
            "This replay uses privileged capture-era measurements and stored factors."
        ),
        cases="sealed",
        seal="figure-lock.json",
        provenance=list(names[1:]),
        series=[
            series("one", PREFIX + mode, "Separate make-up transplant"),
            series("stock", results.STOCK, "Complete fixed four"),
            series("one_native_factors", results.FIFTH, "Complete fixed five"),
        ],
    )
    save_json(out / "figures.json", dict(version=2, charts=[panel]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("primary_work", type=local_output)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--plot", type=local_output)
    args = parser.parse_args()
    run(args.primary_work, args.work)
    if (REPORT / "prediction-lock.json").exists():
        publish(args.work)
        if args.plot:
            screening_figures.generate(args.plot, evidence=REPORT)
