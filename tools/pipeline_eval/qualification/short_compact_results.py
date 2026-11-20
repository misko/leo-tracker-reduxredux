"""Seal two-block compact inference, then score resulting positions and modeled timing."""

import argparse
import gzip
import json
from pathlib import Path

from .. import figure_books, whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km
from . import short_compact as trial
from . import short_compact_release as release
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file

METHOD = "short_compact"
PREDICTIONS = "positions.jsonl.gz"
ATTEMPTS = "attempts.jsonl.gz"
DECISIONS = "release-decisions.json"
LOCK = "prediction-lock.json"
RULE = "release-rule-lock.json"
SCORE = "scores.csv"
TIMES = "timing.csv"


def mounted(base):
    report = trial.REPORT
    rule = whole_iq.read(report / RULE)
    whole_iq.checked(Path(release.__file__), rule["source_sha256"])
    whole_iq.checked(report / "PROTOCOL.md", rule["protocol_sha256"])
    source = whole_iq.checked(report / "source-lock.json", rule["worker_lock_sha256"])
    whole_iq.checked(source, (base / "source-lock.sha256").read_text().strip())
    lock = whole_iq.read(source)
    for file, sha in lock["waveform_files"].items():
        whole_iq.checked(trial.WAVE / file, sha)
    return lock


def prediction(row, method, *, result=None):
    fields = ("id", "profile", "native_sha256", "catalog_sha256", "tile")
    return {k: row[k] for k in fields} | dict(
        method=method,
        result=row["result"] if result is None else result,
    )


def combine(base, plan):
    archive, positions, decisions = [], [], {}
    assignments = base / "additional/additional-cpus.json"
    revised = whole_iq.read(
        whole_iq.checked(assignments, _sha(trial.REPORT / "additional-cpus.json"))
    )
    if revised["source_lock_sha256"] != _sha(trial.REPORT / "source-lock.json"):
        raise ValueError("additional CPU assignments do not bind the original experiment")
    initial = {
        ident: int(cpu) for cpu, ids in revised["original_runs_unchanged"].items() for ident in ids
    }
    extra = {ident: int(cpu) for cpu, ids in revised["cpus"].items() for ident in ids}
    if (
        set(initial) != set(trial.ROOF)
        or initial.keys() & extra.keys()
        or initial.keys() | extra.keys() != plan["cases"].keys()
    ):
        raise ValueError("additional CPU assignments must move only the unstarted waveform cases")
    for ident, spec in plan["cases"].items():
        folder = base / "additional" / ident if ident in extra else base / ident
        expected_cpu = extra.get(ident, initial.get(ident))
        rows = []
        for name in ("0", "1", "2", "full"):
            row = whole_iq.read(folder / name / "prediction.json")
            if (
                row["name"] != name
                or row["cpu"] != expected_cpu
                or any(row[k] != spec[k] for k in ("id", "tile", "native_sha256", "catalog_sha256"))
                or (name != "full" and _sha(folder / name / "block.json") != row["input_sha256"])
                or (name == "full" and row["input_sha256"] != spec["native_sha256"])
            ):
                raise ValueError("recording, factor subset or scheduled attempt did not match")
            rows.append(row)
        early, cases = release.decide(rows[:3])
        full = rows[3]
        time = full["worker_wall_s"] + full["input_preparation_wall_s"]
        ordinary_finish = [a + time for a in full["support"]["available_s"]]
        if cases["released"]:
            end = cases["last_worker_end_elapsed_s"]
        else:
            end = [
                max(a, b) + time
                for a, b in zip(
                    cases["last_worker_end_elapsed_s"], full["support"]["available_s"], strict=True
                )
            ]
        cases.update(
            ordinary_terminal_elapsed_s=ordinary_finish,
            proposed_terminal_elapsed_s=end,
            stock_cpu_s=full["worker_cpu_s"],
            eventual_policy_cpu_s=cases["speculative_cpu_s"]
            + (0.0 if cases["released"] else full["worker_cpu_s"]),
            full_status=full["result"]["status"],
            eventual_status=(early if cases["released"] else full["result"])["status"],
        )
        decisions[ident] = cases
        archive.extend(rows)
        positions.extend(
            [
                prediction(full, "short_compact_full"),
                prediction(full, METHOD, result=early),
                prediction(rows[1], "short_compact_at150"),
                prediction(rows[2], "short_compact_at225"),
            ]
        )
    return archive, positions, decisions


def seal(base):
    report = trial.REPORT
    if (report / LOCK).is_file():
        raise FileExistsError("short compact prediction seal already exists")
    plan = mounted(base)
    attempts, results, decisions = combine(base, plan)
    pack(report / ATTEMPTS, attempts)
    pack(report / PREDICTIONS, results)
    save_json(report / DECISIONS, decisions)
    preflight = sorted(p.name for p in report.glob("*preflight*.json"))
    instrument = sorted(p.name for p in report.glob("instrumentation-rejection*.json"))
    files = (
        "source-lock.json",
        "PROTOCOL.md",
        "additional-cpus.json",
        "waveform-adapter-lock.json",
        RULE,
        ATTEMPTS,
        PREDICTIONS,
        DECISIONS,
        *preflight,
        *instrument,
    )
    save_json(
        report / LOCK,
        dict(
            cases=list(plan["cases"]),
            files={name: _sha(report / name) for name in files},
            packer_sha256=_sha(Path(__file__)),
        ),
    )


def sealed(path, name):
    lock = whole_iq.read(path / name)
    for member, sha in lock["files"].items():
        whole_iq.checked(path / member, sha)
    return lock


def load(path):
    with gzip.open(path, "rt") as stream:
        return [json.loads(line) for line in stream]


def waveform_queries(out):
    root = trial.REPORT
    authority = root / "waveform-score-authority.json"
    original = root / "waveform-original-queries.json"
    if not authority.exists():
        prior = trial.WAVE / "score-lock.json"
        pins = whole_iq.read(prior)
        identified = whole_iq.checked(
            trial.WAVE / "figure-queries.json", pins["files"]["figure-queries.json"]
        )
        write(authority, prior.read_bytes())
        write(original, identified.read_bytes())
    pins = whole_iq.read(authority)
    source = whole_iq.read(whole_iq.checked(original, pins["files"]["figure-queries.json"]))
    doc = dict(
        queries=[
            dict(
                row,
                bindings={
                    "native_sha256": row["bindings"]["native_sha256"],
                    "catalog_sha256": row["bindings"]["catalogue_sha256"],
                },
            )
            for row in source["queries"]
        ]
    )
    save_json(out / "waveform-queries.json", doc)
    return {row["id"]: row for row in doc["queries"]}


def write_scores(out, rows, cases, wave):
    _, controls = held_references(None, list(case for case in cases if case in trial.ROOF))
    refs = {r["id"]: r for r in controls} | wave
    result = []
    for row in rows:
        truth = refs[row["id"]]["truth"]
        original = refs[row["id"]].get("reference")
        for arm in ARMS:
            record = row["result"]["arms"][arm]
            result.append(
                dict(
                    id=row["id"],
                    profile=row["profile"],
                    arm=arm,
                    method=row["method"],
                    status=row["result"]["status"],
                    error_km=distance_km(record["latlon"], truth),
                    conditional_rms_hz=record.get("rf_rms_hz"),
                    false_publication=record["latlon"] is not None
                    and refs[row["id"]].get("condition") in ("omitted", "far-omitted"),
                    **{
                        name + "_archived_error_km": original[name][arm]["error_km"]
                        if original is not None
                        else None
                        for name in ROLES
                    },
                )
            )
    csv_file(out / SCORE, result)


def write_times(out, decisions):
    times = []
    for ident, row in decisions.items():
        times.append(
            dict(
                id=ident,
                released_before_end=row["released"],
                checkpoint_s=row["checks"][-1]["nominal_checkpoint_s"],
                checkpoint_finish_s=row["last_worker_end_elapsed_s"][-1],
                ordinary_elapsed_s=row["ordinary_terminal_elapsed_s"][-1],
                speculative_serial_policy_elapsed_s=row["proposed_terminal_elapsed_s"][-1],
                ordinary_cpu_s=row["stock_cpu_s"],
                speculative_serial_policy_cpu_s=row["eventual_policy_cpu_s"],
                ordinary_success=row["full_status"] == "ok",
                eventual_success=row["eventual_status"] == "ok",
            )
        )
    csv_file(out / TIMES, times)
    return times


def resource_plot(out, timing):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    fig, (wall, cpu) = plt.subplots(1, 2, figsize=(11.8, 5.5), layout="constrained")
    wave_labels = {
        row["id"]: row["condition"]
        for row in whole_iq.read(out / "waveform-queries.json")["queries"]
    }
    for i, row in enumerate(timing):
        name = row["id"] if row["id"] in trial.ROOF else "Sim. " + wave_labels[row["id"]]
        for ax, left, right, stock_ok, arm_ok in (
            (
                wall,
                "ordinary_elapsed_s",
                "speculative_serial_policy_elapsed_s",
                row["ordinary_success"],
                row["eventual_success"],
            ),
            (cpu, "ordinary_cpu_s", "speculative_serial_policy_cpu_s", True, True),
        ):
            ax.plot(
                [row[left], row[right]],
                [i, i],
                linewidth=1,
                color="0.70",
                zorder=1,
            )
            ax.scatter(
                row[left],
                i,
                color="#194e72" if stock_ok else "white",
                edgecolor="#194e72",
                label="Full only" if i == 0 else None,
                zorder=2,
            )
            ax.scatter(
                row[right],
                i,
                color="#982b41" if arm_ok else "white",
                edgecolor="#982b41",
                label="Serial blocks with fallback" if i == 0 else None,
                zorder=2,
            )
        wall.text(-0.03, i, name, va="center", ha="right", transform=wall.get_yaxis_transform())
    wall.axvline(300, color="0.42", linewidth=1, linestyle="--", label="300 s schedule")
    for ax, label in ((wall, "Modeled elapsed from initial clock (s)"), (cpu, "Measured CPU (s)")):
        ax.set(ylim=(len(timing) - 0.4, -0.65), xlabel=label, yticks=[], xlim=(0, None))
        ax.legend(frameon=False, loc="lower left", fontsize=8)
    fig.suptitle("Independent compact block checks and ordinary full-recording fallback")
    fig.savefig(out / "latency.png", dpi=155)
    fig.savefig(out / "latency.pdf", metadata={"CreationDate": None})
    plt.close(fig)


def chart(out, queries):
    selectors = [
        ("short_compact_full", "Complete compact stock"),
        ("short_compact_at150", "75–150 s estimate · ungated"),
        ("short_compact_at225", "150–225 s estimate · ungated"),
    ]
    cases = list(trial.ROOF)
    output = []
    for scope, keys, ids in (
        ("roof", ("one", "stock", "one_native_factors", "all_visits"), cases),
        ("transfer", ("candidate", "stock", "one", "four"), list(queries)),
    ):
        caption = (
            "Independent 75-second fits, checked at 150 and 225 s. Gate compares both c arms "
            "and nominal local position confidence. Complete compact is the scheduled fallback."
        )
        if scope == "transfer":
            caption += " One previously sealed simulated waveform with two omitted offers."
        else:
            caption += " Four original v5 options use full capture-era factors."
        provenance = [LOCK, SCORE, TIMES]
        files = [PREDICTIONS, *provenance]
        spec = dict(
            id=f"short_compact-{scope}",
            method=METHOD,
            scope=scope,
            seal=f"{scope}-figure-lock.json",
            cases=ids,
            title="Early compact v5 fix by independent time blocks",
            caption=caption,
            provenance=provenance,
            series=[
                dict(
                    key=key,
                    label=label,
                    file=PREDICTIONS,
                    value=method,
                    where=dict(profile="roof" if scope == "roof" else "waveform"),
                    **(dict(match=["native_sha256", "catalog_sha256", "tile"]) if i else {}),
                )
                for i, (key, (method, label)) in enumerate(
                    zip(keys, [(METHOD, "Released before 300 s"), *selectors], strict=True)
                )
            ],
        )
        if scope == "transfer":
            spec.update(
                queries="waveform-queries.json",
                condition_labels=dict(
                    containing="25 km containing",
                    omitted="25 km near omitted",
                    **{"far-omitted": "25 km far omitted"},
                ),
            )
            files.append(spec["queries"])
        save_json(
            out / spec["seal"], dict(cases=ids, files={name: _sha(out / name) for name in files})
        )
        output.append(spec)
    save_json(out / "figures.json", dict(version=1, charts=output))


def score(out):
    source = trial.REPORT
    pins = sealed(source, LOCK)
    out.mkdir(exist_ok=True, parents=True)
    wave = waveform_queries(out)
    write_scores(out, load(source / PREDICTIONS), pins["cases"], wave)
    timing = write_times(out, whole_iq.read(source / DECISIONS))
    resource_plot(out, timing)
    if source == out:
        chart(out, wave)
        figure_books.generate(out / "charts", ARMS, panel="screening", evidence=out)
        seal_resources(out, pins)


def seal_resources(out, prediction):
    stage = "stage-figure.json"
    score_lock = "score-lock.json"
    save_json(
        out / stage,
        dict(
            version=1,
            id="short-compact-latency",
            title="Elapsed time and CPU for independent compact blocks",
            sample="Four roof recordings and one simulated waveform with three offers",
            boundary="Stored native factors → compact solves → serial release or fallback",
            note=(
                "CPU is measured host work. Elapsed time adds measured fit cost to original "
                "factor availability. Availability plus compute is a replay timing model."
            ),
            seal=score_lock,
            image="latency.png",
            pdf="latency.pdf",
            csv=TIMES,
        ),
    )
    files = (
        stage,
        "latency.png",
        "latency.pdf",
        SCORE,
        TIMES,
        LOCK,
        "waveform-original-queries.json",
        "waveform-score-authority.json",
        "waveform-queries.json",
    )
    save_json(
        out / score_lock,
        dict(cases=prediction["cases"], files={name: _sha(out / name) for name in files}),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "score"))
    p.add_argument("path", type=local_output)
    args = p.parse_args()
    if args.action == "seal":
        seal(args.path)
    else:
        score(args.path)


if __name__ == "__main__":
    main()
