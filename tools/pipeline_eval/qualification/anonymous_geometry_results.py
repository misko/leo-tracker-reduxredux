"""Score and render sealed world-search decisions against evaluator-only regions."""

import argparse
import gzip
import json
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from ..__main__ import encoded, save_json
from ..scoring import ARMS, ROLES, arm_outcome, distance_km
from . import anonymous_geometry_trial as trial
from . import clock_geometry_results as clock
from .absolute_doppler_results import MATCH
from .native_joint_full_results import original_scores, roi_margin
from .prefix_figures import csv_file

OUT, world, MODEL = trial.OUT, trial.world, trial.model
PREDICTIONS, PLOT = "positions.jsonl.gz", "anonymous-pass-support.png"
TRUTH_WORKER = """
import json
import sys
from resource import RLIMIT_AS, setrlimit
from types import SimpleNamespace
import numpy as np
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km
from tools.pipeline_eval.variants import anonymous_geometry as m

setrlimit(RLIMIT_AS, (768 << 20, 768 << 20))
q = json.load(sys.stdin)
d = q['capture']
cap = SimpleNamespace(**(d | {'catalog':d['catalog'].encode('ascii')}))
arcs, _ = m.extract(cap)
sky, ids, _ = m.bank(cap)
train, held = m.build(arcs, sky, cap.duration_s)
p = q['survey_scoring_point']
def scores(point):
    xyz, up = geodetic_to_ecef_km(*point, 0), ecef_to_enu_matrix(*point)[2]
    spectra = [m.spectrum(a, xyz, up) for a in train]
    results = []
    for control in (False, True):
        loss, drift = m.clock_profile(spectra, train, control)
        result = m.check(held, point, drift, control, is_null=False)
        results.append(dict(train_loss=loss, oscillator_equivalent_hz_s=drift.tolist(), **result))
    return results

sites = [scores(m._offset(p, 25 * np.cos(phi), 25 * np.sin(phi)))
         for phi in np.arange(8) * np.pi / 4]
answer = scores(p)
for i, r in enumerate(answer):
    r['held_survey_ring_lead'] = min(s[i]['held_loss'] for s in sites) - r['held_loss']
json.dump(answer, sys.stdout, allow_nan=False)
"""
METRICS = (
    "train_profiles",
    "held_profiles",
    "candidate_orbits",
    "coarse_sites",
    "world_sites",
    "training_comparisons",
    "held_comparisons",
    "training_loss",
    "held_loss",
    "held_lead",
    "held_blocks",
    "held_distinct_orbits",
    "held_matched_arcs",
    "held_slope_rms_hz_s",
    "held_curvature_rms_hz_s2",
    "conditional_held_shape_cfo_rms_hz",
    "c_projected_column_norm",
)


def inside(point, tile):
    if point is None:
        return None
    if distance_km(point, tile["center"]) > 1.01 * tile.get("width_km", 25) / np.sqrt(2):
        return False
    return roi_margin(point, tile) >= 0


def survey_diagnostic(rows, Q, refs):
    """Freeze estimates first, then score only the independently measured location."""
    original_cases = [q for q in Q if not q["shuffle"]]
    overrides = (
        MODEL.__file__,
        trial.ROOT / "tools/pipeline_eval/variants/joint_pass.py",
        trial.ROOT / "tools/pipeline_eval/variants/pass_hypotheses.py",
        trial.ROOT / "tools/pipeline_eval/variants/absolute_doppler.py",
    )

    def lane(cpu, inputs):
        results = []
        command = trial.previous.command(cpu, TRUTH_WORKER, overrides)
        for q in inputs:
            native = trial.load(q["recording"])
            raw = vars(native) | {"catalog": native.catalog.decode("ascii")}
            origin = world.digest(encoded(dict(capture=raw, shuffle=False)))
            if origin != rows[q["id"], MODEL.METHOD]["input_sha256"]:
                raise ValueError("survey-only diagnostic has different native observations")
            request = encoded(dict(capture=raw, survey_scoring_point=refs[q["recording"]]["truth"]))
            proc = subprocess.run(
                command, input=request, capture_output=True, check=True, timeout=45
            )
            for method, value in zip(trial.METHODS, json.loads(proc.stdout), strict=True):
                m = rows[q["id"], method]["result"]["metrics"]
                results.append(
                    dict(
                        id=q["id"],
                        method=method,
                        training_winner=m["training_loss"],
                        held_at_training_winner=m["held_loss"],
                        at_survey=value,
                    )
                )
        return results

    with ThreadPoolExecutor(2) as executor:
        a, b = [
            executor.submit(lane, cpu, original_cases[i::2]) for i, cpu in enumerate(trial.CPUS)
        ]
        return a.result() + b.result()


def score():
    receipt = world.read(OUT / "prediction-lock.json")
    world.verify(OUT, receipt["files"])
    Q = world.read(OUT / "blind-plan.json")["cases"]
    track_lock = OUT.parent.parent / "latency-and-support/joint-pass"
    world.verify(track_lock, world.read(track_lock / "prediction-lock.json")["files"])
    tracker = "tools/pipeline_eval/variants/doppler_turns.py"
    recorded = world.read(track_lock / "source-lock.json")[tracker]
    if world.digest((trial.ROOT / tracker).read_bytes()) != recorded:
        raise ValueError("anonymous continuity linker differs from its earlier pinned dependency")
    save_json(
        OUT / "dependency-audit.json",
        dict(
            earlier_lock=str((track_lock / "prediction-lock.json").relative_to(trial.ROOT)),
            earlier_lock_sha256=world.digest((track_lock / "prediction-lock.json").read_bytes()),
            matching_tracker={tracker: recorded},
        ),
    )
    refs, original, omitted, _, _ = clock.original.authorities()
    _, _, earlier = clock.trial.keys()
    with gzip.open(OUT / PREDICTIONS, "rt") as source:
        archive = list(map(json.loads, source))
    rows = {(r["id"], r["method"]): r for r in archive}
    if len(rows) != len(archive) or set(rows) != {(q["id"], m) for q in Q for m in trial.METHODS}:
        raise ValueError("predictions differ from the immutable roster")
    scores, panels = [], {}
    coarse_points = MODEL.earth_mesh(MODEL.COARSE).tolist()
    for q in Q:
        case, recording, cohort = (q[k] for k in ("id", "recording", "cohort"))
        primary = rows[case, MODEL.METHOD]
        target = refs[recording]["truth"]
        nearest_coarse = min(distance_km(target, p) for p in coarse_points)
        expected = cohort != "omitted"
        if inside(target, q["tile"]) != expected:
            raise ValueError("the actual offer does not match the frozen condition")
        if cohort == "omitted":
            seal = omitted[case]
            if target != seal["truth"] or any(
                primary["original_request_sha256" if k == "input_sha256" else k] != v
                for k, v in seal["bindings"].items()
            ):
                raise ValueError("the omitted query does not match its query authority")
        bindings = {k: primary[k] for k in MATCH}
        panels.setdefault(cohort, []).append(
            dict(id=case, recording=recording, condition=cohort, truth=target, bindings=bindings)
        )
        local, roof = {}, {}
        if cohort == "containing":
            roof = original_scores(recording, refs[recording], original[recording], target)
            local = earlier[recording, clock.trial.previous.METHODS[1]]
            if any(local[k] != primary[k] for k in MATCH if k != "input_sha256"):
                raise ValueError("local control has a different native input or archived offer")
            local = clock.chart_control(local)["result"]
        for method in trial.METHODS:
            row = rows[case, method]
            if any(row.get(k) != v for k, v in (q | bindings).items()):
                raise ValueError("paired worldwide methods use different observations")
            outcome = row["result"]
            for arm in ARMS:
                ep = outcome["arms"][arm]
                status, reason = arm_outcome(outcome, ep)
                base = local.get("arms", {}).get(arm, {})
                m = outcome["metrics"] if arm == "c0" else {}
                scores.append(
                    dict(
                        id=case,
                        recording=recording,
                        cohort=cohort,
                        method=method,
                        arm=arm,
                        status=status,
                        reason=reason,
                        position_attempted=m.get("position_attempted", False),
                        held_independent_support=min(m["held_blocks"], m["held_distinct_orbits"])
                        if "held_blocks" in m
                        else None,
                        error_km=distance_km(ep["latlon"], target),
                        forced_error_km=distance_km(ep["forced_latlon"], target),
                        truth_inside_scored_offer=expected,
                        publication_inside_scored_offer=inside(ep["latlon"], q["tile"]),
                        forced_inside_scored_offer=inside(ep["forced_latlon"], q["tile"]),
                        tile_center_error_km=distance_km(q["tile"]["center"], target),
                        nearest_coarse_grid_km=nearest_coarse,
                        local_shared_clock_status=arm_outcome(local, base)[0] if local else None,
                        local_shared_clock_forced_error_km=distance_km(
                            base.get("forced_latlon"), target
                        ),
                        local_shared_clock_held_rms_hz=local.get("metrics", {}).get("held_rms_hz")
                        if arm == "c0"
                        else None,
                        worker_s=row.get("worker_s"),
                        cpu_s=row.get("cpu_s"),
                        wall_s=row.get("native_elapsed_s"),
                        rss_kib=row.get("peak_rss_kib"),
                        **{k: m.get(k) for k in METRICS},
                        **{
                            role + "_error_km": roof[role][arm][0] if role in roof else None
                            for role in ROLES
                        },
                    )
                )
    counts = [
        dict(
            cohort=cohort,
            method=m,
            arm=arm,
            status=dict(
                Counter(
                    r["status"]
                    for r in scores
                    if (r["cohort"], r["method"], r["arm"]) == (cohort, m, arm)
                )
            ),
        )
        for cohort in panels
        for m in trial.METHODS
        for arm in ARMS
    ]
    save_json(OUT / "scores.json", dict(rows=scores, counts=counts))
    csv_file(OUT / "scores.csv", scores)
    plot(scores)
    paths = ("prediction-lock.json", "scores.json", "scores.csv", "dependency-audit.json", PLOT)
    files = receipt["files"] | {k: world.digest((OUT / k).read_bytes()) for k in paths}
    save_json(OUT / "score-lock.json", dict(cases=receipt["cases"], files=files))
    cards(panels, files)


def plot(scores):
    import matplotlib.pyplot as plt

    records = [r for r in scores if r["arm"] == "c0" and r["method"] == MODEL.METHOD]
    names = [
        r["id"].replace("-profile-shuffle", " shuffled").replace("-omitted", " omitted")
        for r in records
    ]
    ypos = np.arange(len(records))
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.8), layout="constrained")
    for method, legend, mark in zip(
        trial.METHODS, ("Shared drift", "Curvature only"), ("D", "x"), strict=True
    ):
        rows = [r for r in scores if r["arm"] == "c0" and r["method"] == method]
        for ax, field in zip(
            axes, ("held_loss", "held_lead", "held_independent_support"), strict=True
        ):
            ax.scatter([r[field] for r in rows], ypos, label=legend, marker=mark)
    axes[1].axvline(0.15, linestyle="--", color="0.4", label="Location lead gate")
    axes[2].axvline(3, linestyle="--", color="0.4", label="Count gate")
    axes[2].set_xticks(range(4))
    for i, (ax, label) in enumerate(
        zip(
            axes,
            (
                "Held loss per arc (normalized)",
                "Held lead over geographic rivals",
                "Smaller of distinct orbit and block counts",
            ),
            strict=True,
        )
    ):
        ax.set(yticks=ypos, yticklabels=names if i == 0 else [""] * len(names), xlabel=label)
        ax.invert_yaxis()
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), frameon=False)
    fig.savefig(OUT / PLOT, dpi=150)
    plt.close(fig)


def cards(panels, files):
    descriptors = []
    for cohort, rows in panels.items():
        direct = cohort == "containing"
        cases = [r["id"] for r in rows]
        seal = cohort + "-figure-lock.json"
        title = {
            "containing": "Worldwide pass geometry on measured roofs",
            "omitted": "Worldwide pass geometry with omitted offers",
            "shuffle": "Worldwide pass geometry on shuffled shapes",
        }[cohort]
        caption = {
            "containing": "Worldwide search uses no region. Original v5 uses the containing offer.",
            "omitted": "Authentic wrong offers are used only to score. Search remains worldwide.",
            "shuffle": "Within-chain shape permutation. Error is relative to the source roof.",
        }[cohort]
        chart = dict(
            id=MODEL.METHOD + "-" + cohort,
            method=MODEL.METHOD,
            scope="roof" if direct else "transfer",
            title=title,
            caption=caption,
            cases=cases,
            seal=seal,
            provenance=["prediction-lock.json", "scores.csv"],
            series=[],
        )
        for j, (method, label) in enumerate(
            zip(trial.METHODS, ("Shared drift", "Curvature only"), strict=True)
        ):
            line = dict(
                key="stock" if j else "one" if direct else "candidate",
                file=PREDICTIONS,
                where={"cohort": cohort},
                value=method,
                label=label,
            )
            if not direct or not j:
                line["forced_label"] = label + " · forced"
            if j:
                line["match"] = list(MATCH)
            chart["series"].append(line)
        lock = files.copy()
        if not direct:
            name = cohort + "-queries.json"
            save_json(OUT / name, dict(queries=rows))
            lock[name] = world.digest((OUT / name).read_bytes())
            chart["queries"] = name
        save_json(OUT / seal, dict(cases=cases, files=lock))
        descriptors.append(chart)
    save_json(OUT / "figures.json", dict(version=2, charts=descriptors))


def diagnose():
    lock = OUT / "prediction-lock.json"
    receipt = world.read(lock)
    world.verify(OUT, receipt["files"])
    Q = world.read(OUT / "blind-plan.json")["cases"]
    refs, *_ = clock.original.authorities()
    with gzip.open(OUT / PREDICTIONS, "rt") as source:
        rows = {(r["id"], r["method"]): r for r in map(json.loads, source)}
    results = survey_diagnostic(rows, Q, refs)
    save_json(
        OUT / "survey-diagnostic.json",
        dict(
            role="Privileged diagnostic at the surveyed coordinate after predictions were sealed",
            prediction_lock_sha256=world.digest(lock.read_bytes()),
            diagnostic_source_sha256=world.digest(Path(__file__).read_bytes()),
            rows=results,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--survey-diagnostic", action="store_true")
    if parser.parse_args().survey_diagnostic:
        diagnose()
    else:
        score()
