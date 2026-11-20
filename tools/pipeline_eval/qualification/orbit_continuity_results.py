"""Score blind native continuity and a separately privileged continuation audit."""

import argparse
import gzip
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from ..__main__ import encoded, save_json
from ..scoring import ARMS, arm_outcome, distance_km
from . import orbit_continuity_trial as trial
from . import orbit_proposals_results as old
from .absolute_doppler_results import MATCH
from .armijo_finish_results import pack
from .prefix_figures import csv_file

OUT, MODEL, world = trial.OUT, trial.model, trial.world
BASE = "orbit_continuity_free_rematch_control"
COMPARISON = "chart-positions.jsonl.gz"
PLOT = "continuity-support.png"
MAIN_METRICS = (
    "train_profiles",
    "early_links",
    "held_eligible_orbits",
    "held_visit_opportunities",
    "held_coherent_hits",
    "held_placebo_hits",
    "held_orbits",
    "held_blocks",
    "held_cfo_rms_hz",
    "held_strength",
    "held_lead",
    "rival_distance_km",
    "training_loss",
    "world_sites",
    "training_comparisons",
    "inverse_points",
    "rivals",
)
SAME_EARLY = (
    "train_profiles",
    "early_links",
    "early_orbit_ids",
    "held_eligible_orbits",
    "held_visit_opportunities",
    "training_loss",
    "inverse_points",
    "training_comparisons",
)
SURVEY_WORKER = """
import json
import sys
from resource import RLIMIT_AS, setrlimit
from types import SimpleNamespace
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km
from tools.pipeline_eval.variants import orbit_continuity as m

setrlimit(RLIMIT_AS, (768 << 20, 768 << 20))
q = json.load(sys.stdin)
d = q['capture']
cap = SimpleNamespace(**(d | {'catalog':d['catalog'].encode('ascii')}))
late = 0.65 * cap.duration_s
reference = cap.duration_s / 2
early = [r for r in cap.probes if (r['valid_start_counter']-cap.first_counter)/cap.sample_rate_hz
         + cap.probe_ms/2000 < late]
arcs, _ = m.forward.extract(SimpleNamespace(**(vars(cap) | {'probes':early})))
states, ids, _ = m.forward.bank(cap)
profiles = m.early_profiles(arcs, states)
p = q['survey_scoring_point']
xyz, up = geodetic_to_ecef_km(*p, 0), ecef_to_enu_matrix(*p)[2]
s = [m.forward.spectrum(a, xyz, up) for a in profiles]
loss, drift = m.forward.clock_profile(s, profiles, False)
links = m.winner_links(s, profiles, drift, reference)
lanes = m.held_lanes(cap,late,False)
out = m.forecast(lanes,states,p,links,drift,reference)
early_ids = sorted({int(ids[x.orbit]) for x in links})
json.dump(dict(out, early_links=len(links), early_orbit_ids=early_ids, training_loss=loss),
          sys.stdout, allow_nan=False)
"""


def inputs():
    lock = OUT / "prediction-lock.json"
    receipt = world.read(lock)
    world.verify(OUT, receipt["files"])
    Q, _, _ = trial.roster()
    if world.read(OUT / "blind-plan.json")["cases"] != Q:
        raise ValueError("changed frozen continuity plan")
    with gzip.open(OUT / "positions.jsonl.gz", "rt") as stream:
        loaded = list(map(json.loads, stream))
    source = {r["id"]: r for r in loaded}
    if len(source) != len(loaded) or set(source) != set(receipt["cases"]):
        raise ValueError("missing locked continuity attempt")
    refs, _, omitted, _, _ = old.old_score.clock.original.authorities()
    return receipt, Q, source, refs, omitted


def diagnose():
    _, Q, rows, refs, _ = inputs()
    use = [q for q in Q if not q["shuffle"]]
    paths = [Path(p.__file__) for p in (MODEL, MODEL.inverse, MODEL.forward)]
    paths.extend(
        trial.ROOT / "tools/pipeline_eval/variants" / (n + ".py")
        for n in (
            "joint_pass",
            "pass_hypotheses",
            "absolute_doppler",
            "doppler_turns",
        )
    )
    paths.append(trial.ROOT / "tools/pipeline_eval/scoring.py")

    def lane(i):
        command = trial.prior.old.previous.command(trial.CPUS[i], SURVEY_WORKER, paths)
        results = []
        for q in use[i::2]:
            native = trial.prior.old.load(q["recording"])
            raw = vars(native) | {"catalog": native.catalog.decode("ascii")}
            if (
                world.digest(encoded(dict(capture=raw, shuffle=False)))
                != rows[q["id"]]["input_sha256"]
            ):
                raise ValueError("privileged forecast has different native observations")
            request = encoded(dict(capture=raw, survey_scoring_point=refs[q["recording"]]["truth"]))
            p = subprocess.run(command, input=request, capture_output=True, check=True, timeout=45)
            results.append(dict(id=q["id"], at_survey=json.loads(p.stdout)))
        return results

    with ThreadPoolExecutor(2) as executor:
        results = [r for part in executor.map(lane, range(2)) for r in part]
    save_json(
        OUT / "survey-diagnostic.json",
        dict(
            diagnostic_only=True,
            blind_prediction_lock_sha256=world.digest((OUT / "prediction-lock.json").read_bytes()),
            diagnostic_protocol_sha256=world.digest((OUT / "DIAGNOSTIC.md").read_bytes()),
            diagnostic_source_sha256=world.digest(Path(__file__).read_bytes()),
            rows=results,
        ),
    )


def score():
    receipt, Q, primary, refs, omitted = inputs()
    previous = trial.prior.OUT / "prediction-lock.json"
    world.verify(previous.parent, world.read(previous)["files"])
    with gzip.open(previous.parent / "positions.jsonl.gz", "rt") as stream:
        prior = {v["id"]: v for v in map(json.loads, stream)}
    diagnostic = world.read(OUT / "survey-diagnostic.json")
    if diagnostic["blind_prediction_lock_sha256"] != world.digest(
        (OUT / "prediction-lock.json").read_bytes()
    ):
        raise ValueError("privileged continuation diagnostic differs from locked blind request")
    survey = {r["id"]: r["at_survey"] for r in diagnostic["rows"]}
    series, panels, scores = [], {}, []
    for q in Q:
        ident, recording, condition = (q[k] for k in ("id", "recording", "cohort"))
        r = primary[ident]
        match = {k: r[k] for k in MATCH}
        if any(r.get(k) != v for k, v in q.items()):
            raise ValueError("the row does not match the frozen request")
        truth = refs[recording]["truth"]
        if old.old_score.inside(truth, q["tile"]) != (condition != "omitted"):
            raise ValueError("the held recording differs from its evaluator offer")
        if condition == "omitted":
            binding = omitted[ident]
            if truth != binding["truth"] or any(
                r["original_request_sha256" if k == "input_sha256" else k] != v
                for k, v in binding["bindings"].items()
            ):
                raise ValueError("the omitted query differs from its recorded authority")
        if q["shuffle"]:
            a, b = r["result"], primary[recording]["result"]
            if any(a["metrics"].get(k) != b["metrics"].get(k) for k in SAME_EARLY) or (
                a["arms"]["c0"]["forced_latlon"] != b["arms"]["c0"]["forced_latlon"]
            ):
                raise ValueError("late-only control changed early geometry or opportunity scope")
        panels.setdefault(condition, []).append(
            dict(id=ident, recording=recording, condition=condition, truth=truth, bindings=match)
        )
        compared = [r]
        if condition in ("containing", "omitted"):
            other = prior[ident]
            if any(other.get(k) != v for k, v in (q | match).items()):
                raise ValueError("earlier free-rematch control differs from locked data")
            compared.append(other | {"method": BASE})
        series.extend(compared)
        for item in compared:
            result = item["result"]
            for arm in ARMS:
                endpoint = result["arms"][arm]
                status, reason = arm_outcome(result, endpoint)
                m = result["metrics"] if arm == "c0" else {}
                s = survey.get(ident, {}) if arm == "c0" and item["method"] == MODEL.METHOD else {}
                scores.append(
                    dict(
                        id=ident,
                        recording=recording,
                        cohort=condition,
                        method=item["method"],
                        arm=arm,
                        status=status,
                        reason=reason,
                        error_km=distance_km(endpoint["latlon"], truth),
                        forced_error_km=distance_km(endpoint["forced_latlon"], truth),
                        forced_inside_scored_offer=old.old_score.inside(
                            endpoint["forced_latlon"], q["tile"]
                        ),
                        published_inside_scored_offer=old.old_score.inside(
                            endpoint["latlon"], q["tile"]
                        ),
                        cpu_s=item.get("cpu_s"),
                        wall_s=item.get("native_elapsed_s"),
                        rss_kib=item.get("peak_rss_kib"),
                        **{k: m.get(k) for k in MAIN_METRICS if k != "held_lead"},
                        forecast_held_lead=m.get("held_lead")
                        if item["method"] == MODEL.METHOD
                        else None,
                        prior_shape_held_lead=m.get("held_lead")
                        if item["method"] == BASE
                        else None,
                        **{f"survey_{k}": s.get(k) for k in MAIN_METRICS},
                    )
                )
    save_json(OUT / "scores.json", dict(rows=scores))
    csv_file(OUT / "scores.csv", scores)
    plot(scores)
    artifacts = (
        "prediction-lock.json",
        "scores.json",
        "scores.csv",
        PLOT,
        "survey-diagnostic.json",
        "DIAGNOSTIC.md",
    )
    files = receipt["files"] | {k: world.digest((OUT / k).read_bytes()) for k in artifacts}
    files[COMPARISON] = pack(OUT, COMPARISON, series)
    save_json(
        OUT / "score-lock.json",
        dict(
            cases=receipt["cases"],
            files=files,
            previous_lock_sha256=world.digest(previous.read_bytes()),
        ),
    )
    cards(panels, files | {"score-lock.json": world.digest((OUT / "score-lock.json").read_bytes())})


def plot(scores):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator, PercentFormatter

    rows = [r for r in scores if r["arm"] == "c0" and r["method"] == MODEL.METHOD]
    y = np.arange(len(rows))
    labels = [
        r["id"].replace("-profile-shuffle", " shuffled").replace("-omitted", " omitted")
        for r in rows
    ]
    fig, (a, b, c) = plt.subplots(1, 3, figsize=(13.5, 5), layout="constrained")
    for field, name, marker in (
        ("early_links", "Blind winner", "D"),
        ("survey_early_links", "Given survey", "o"),
    ):
        a.scatter([r[field] for r in rows], y, label=name, marker=marker)
    for field, name, marker in (
        ("held_coherent_hits", "Orbit forecasts", "D"),
        ("held_placebo_hits", "Frequency placebo", "x"),
        ("survey_held_coherent_hits", "Given survey", "o"),
    ):
        b.scatter([r[field] for r in rows], y, label=name, marker=marker)
    c.scatter([r["forecast_held_lead"] for r in rows], y, label="Blind winner", marker="D")
    c.axvline(MODEL.LEAD, linestyle="--", color="0.4", label="Publication requirement")
    a.xaxis.set_major_locator(MaxNLocator(integer=True))
    b.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=5))
    c.set_xticks(np.arange(-0.01, 0.04, 0.01))
    c.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    for i, (ax, label) in enumerate(
        zip(
            (a, b, c),
            (
                "Bound early orbit and RF hypotheses",
                "Unique coherent late visits",
                "Held rate lead vs geographic rival",
            ),
            strict=True,
        )
    ):
        ax.set(yticks=y, yticklabels=labels if i == 0 else [""] * len(y), xlabel=label)
        ax.invert_yaxis()
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), frameon=False)
    fig.savefig(OUT / PLOT, dpi=150)
    plt.close(fig)


def cards(panels, files):
    figures = []
    for cohort, rows in panels.items():
        direct = cohort in ("containing", "fresh")
        ids = [r["id"] for r in rows]
        seal = cohort + "-figure-lock.json"
        scope = {
            "containing": "on two roof recordings",
            "omitted": "with omitted offers",
            "fresh": "on the fresh recording",
            "shuffle": "with deranged late visits",
        }[cohort]
        view = dict(
            id=MODEL.METHOD + "-" + cohort,
            method=MODEL.METHOD,
            scope="roof" if direct else "transfer",
            title="Causal orbit continuity " + scope,
            cases=ids,
            seal=seal,
            caption="Early orbits predict late native peaks. Offers stay in evaluation.",
            provenance=["prediction-lock.json", "score-lock.json"],
            series=[],
        )
        line = dict(
            key="one" if direct else "candidate",
            value=MODEL.METHOD,
            label="Orbit continuity",
            forced_label="Orbit continuity · forced",
            where={"cohort": cohort},
            file=COMPARISON,
        )
        view["series"].append(line)
        if cohort in ("containing", "omitted"):
            line = dict(
                key="stock",
                value=BASE,
                label="Free rematch",
                where={"cohort": cohort},
                match=list(MATCH),
                file=COMPARISON,
            )
            if not direct:
                line["forced_label"] = "Free rematch · forced"
            view["series"].append(line)
        lock = files.copy()
        if not direct:
            name = cohort + "-queries.json"
            save_json(OUT / name, dict(queries=rows))
            lock[name] = world.digest((OUT / name).read_bytes())
            view["queries"] = name
        save_json(OUT / seal, dict(cases=ids, files=lock))
        figures.append(view)
    save_json(OUT / "figures.json", dict(version=2, charts=figures))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--survey-diagnostic", action="store_true")
    if parser.parse_args().survey_diagnostic:
        diagnose()
    else:
        score()
