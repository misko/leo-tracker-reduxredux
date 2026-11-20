"""Score held carrier forecasts and geographic error after the prediction seal."""

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .. import corpus, figure_books, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import clock_transfer_grouped as model
from ..variants import compact_tile_interior
from . import clock_transfer_grouped_trial as trial
from .cold_scenes import CHANNELS
from .full_v5_check import _sha
from .prefix_figures import csv_file

OUT = trial.OUT
MODES = dict(
    carried="Carried carrier",
    clock_only="Receiver clock",
    free_track="Local track clock",
    identity_sham="Identity sham",
    offer_center="Offer center",
)
FORCED_LABELS = dict(
    carried="Carried fit",
    clock_only="Clock fit",
    free_track="Local track fit",
    identity_sham="Sham fit",
    offer_center="Center point",
)
CONDITIONS = dict(containing="Containing", near_missing="Near missing", far_missing="Far missing")


def sealed(report):
    lock = whole_iq.read(report / trial.LOCK)
    for name, digest in lock["files"].items():
        whole_iq.checked(report / name, digest)
    plan = whole_iq.read(report / trial.PLAN)
    rows = list(map(json.loads, gzip.decompress((report / trial.PRED).read_bytes()).splitlines()))
    if lock["cases"] != [r["id"] for r in rows]:
        raise ValueError("clock transfer results differ from the sealed roster")
    for case, row in zip(plan["cases"], rows, strict=True):
        if any(row[name] != value for name, value in case.items()):
            raise ValueError("clock transfer results changed the authenticated input")
        if row["status"] == "ok":
            for position in row["records"]:
                validate_result(position["result"])
            rank = row["audit"]
            if rank["rank_with_c"] != rank["unrestricted_rank"] or rank["c_null_error"] > 1e-10:
                raise ValueError("the claimed RF gauge failed its data-rank audit")
    return plan, rows


def references(rows):
    ids = {r["id"] for r in rows if r["group"] != "simulated"}
    return {
        r["id"]: r
        for panel in ("roof16", "ds26-all159")
        for r in corpus.references(panel)
        if r["id"] in ids
    }


def failure_rows(row):
    from ..variants.multi_session import design

    _, offers = design(row["center"])
    result = dict(
        status=row["status"],
        reason=row["reason"],
        boundary=model.BOUNDARY,
        metrics=dict(position_attempted=False),
        arms={arm: dict(latlon=None) for arm in ARMS},
    )
    return [
        dict(offer=offer, tile=dict(center=tile["center"], width_km=25), method=mode, result=result)
        for offer, tile in offers.items()
        for mode in MODES
    ]


def paired(matches, control):
    common = [
        (r["carried"], r[control])
        for r in matches
        if r["carried"] is not None and r[control] is not None
    ]
    if any(a["held_points"] != b["held_points"] for a, b in common):
        raise ValueError("held forecasts use different raw visits")
    count = len(common)
    return dict(
        compared_targets=count,
        carried_rms_hz=float(np.sqrt(np.mean([a["held_rms_hz"] ** 2 for a, _ in common])))
        if count
        else None,
        control_rms_hz=float(np.sqrt(np.mean([b["held_rms_hz"] ** 2 for _, b in common])))
        if count
        else None,
        carried_loss=float(np.mean([a["held_loss"] for a, _ in common])) if count else None,
        control_loss=float(np.mean([b["held_loss"] for _, b in common])) if count else None,
    )


def sim_identity(matches, label):
    truth = {
        (row["block"], CHANNELS[row["channel"] - 1]): row["norad"]
        for row in label["emitter"]["emitters"]
    }
    result = []
    for target in matches:
        for mode, point in target.items():
            if mode == "target" or point is None:
                continue
            block = point["block"]
            low, high = (30 * block + 20) // 50, (30 * (block + 1) - 1) // 50
            if low != high or (low, point["rf_hz"]) not in truth:
                continue
            reference = truth[low, point["rf_hz"]]
            result.append(
                dict(
                    target=target["target"],
                    mode=mode,
                    guessed=point["orbit"],
                    expected=reference,
                    correct=point["orbit"] == reference,
                )
            )
    return result


def score_row(ident, row, record, truth, reference):
    result = record["result"]
    visible = result["arms"]["c0"]
    m = result["metrics"]
    held = m.get("held", {})
    audit = row.get("audit", {})
    baseline = reference.get("reference", {}).get("baseline", {})
    return dict(
        id=ident,
        recording=row["id"],
        group=row["group"],
        offer=record["offer"],
        mode=record["method"],
        status=result["status"],
        reason=result["reason"],
        truth_tile_margin_km=compact_tile_interior.margin(truth, record["tile"]),
        published_error_km=distance_km(visible.get("latlon"), truth),
        forced_error_km=distance_km(visible.get("forced_latlon"), truth),
        baseline_c0_km=baseline.get("c0", {}).get("error_km"),
        baseline_fitted_c_km=baseline.get("fitted_c", {}).get("error_km"),
        cell=m.get("selected_cell_km"),
        held_targets=m.get("held_targets"),
        held_rms_hz=held.get("rms_hz"),
        held_loss=held.get("loss"),
        held_predicted_tracks=held.get("predicted_tracks"),
        held_blocks=held.get("supported_blocks"),
        held_orbits=held.get("supported_orbits"),
        held_site_lead=m.get("held_site_loss_lead"),
        sham_lead=m.get("held_sham_loss_lead"),
        training_loss=m.get("training_loss"),
        donor_arcs=audit.get("arcs"),
        overlapped_families=audit.get("overlapped_norads"),
        cross_rf_families=audit.get("cross_rf_norads"),
        clock_rank=audit.get("clock_rank"),
        grouped_rank=audit.get("grouped_rank"),
        rank_increment=m.get("carried_rank_increment"),
        unrestricted_rank=audit.get("unrestricted_rank"),
        rank_with_c=audit.get("rank_with_c"),
        c_null_error=audit.get("c_null_error"),
        cpu_s=row.get("worker_cpu_s"),
        wall_s=row.get("direct_worker_s"),
        peak_rss_mib=row["peak_rss_kib"] / 1024 if "peak_rss_kib" in row else None,
    )


def figures(folder, positions, queries, simulated):
    folder.mkdir(parents=True, exist_ok=True)
    files = ("positions.jsonl.gz", "queries.json", "figure-lock.json")
    write(
        folder / files[0], gzip.compress(b"".join(encoded(r) + b"\n" for r in positions), mtime=0)
    )
    save_json(folder / files[1], dict(queries=queries))
    save_json(
        folder / files[2],
        dict(cases=[r["id"] for r in queries], files={n: _sha(folder / n) for n in files[:2]}),
    )
    prefix = "clock-carrier-simulated" if simulated else "clock-carrier-roof"
    charts = []
    for suffix, title, modes in (
        (
            "position",
            "Carried carrier versus receiver-only and local clocks",
            (
                ("candidate", "carried"),
                ("stock", "clock_only"),
                ("one", "free_track"),
                ("four", "offer_center"),
            ),
        ),
        (
            "identity",
            "Carried carrier versus an identity sham",
            (("candidate", "carried"), ("stock", "identity_sham"), ("one", "offer_center")),
        ),
    ):
        label = f"{prefix}-{suffix}"
        sample = "Blind generated site" if simulated else "Four measured recordings at one roof"
        charts.append(
            dict(
                id=label,
                method=label,
                scope="transfer",
                cases="sealed",
                seal=files[2],
                queries=files[1],
                condition_labels=CONDITIONS,
                title=title,
                caption=(
                    sample + ". The unrestricted RF-linear coefficient is a gauge. "
                    "The c0 arm fixes this gauge and retains forced diagnostics."
                ),
                series=[
                    dict(
                        key=k,
                        file=files[0],
                        value=m,
                        label=MODES[m],
                        forced_label=FORCED_LABELS[m],
                    )
                    for k, m in modes
                ],
            )
        )
    save_json(folder / "figures.json", dict(version=2, charts=charts))
    return [c["id"] for c in charts]


def support_figure(report, scores, pairs):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    original = [r for r in scores if r["offer"] == "containing" and r["mode"] == "carried"]
    local = {
        r["recording"]: r
        for r in pairs
        if r["offer"] == "containing" and r["control"] == "free_track"
    }
    points = [
        dict(
            recording=r["recording"],
            kind=r["group"],
            overlapping_families=r["overlapped_families"],
            cross_rf_families=r["cross_rf_families"],
            held_targets=r["held_targets"],
            carried_targets=r["held_predicted_tracks"],
            **{
                k: local[r["recording"]][k]
                for k in ("compared_targets", "carried_rms_hz", "control_rms_hz")
            },
        )
        for r in original
    ]
    csv_file(report / "clock-carrier-support.csv", points)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.3), layout="constrained")
    labels = [r["recording"] if r["kind"] != "simulated" else "Simulated" for r in points]
    x = np.arange(len(points))

    def numeric(field):
        return [np.nan if p[field] is None else p[field] for p in points]

    axes[0].bar(x - 0.22, numeric("held_targets"), width=0.22, label="Eligible heads")
    axes[0].bar(x, numeric("carried_targets"), width=0.22, label="Carried forecasts")
    axes[0].bar(x + 0.22, numeric("cross_rf_families"), width=0.22, label="Cross-RF families")
    axes[0].set_ylabel("Count")
    axes[0].set_title("Anonymous held targets and donor support")
    axes[1].scatter(x - 0.12, numeric("carried_rms_hz"), marker="s", label="Carried")
    axes[1].scatter(x + 0.12, numeric("control_rms_hz"), marker="o", label="Free track")
    axes[1].set_ylabel("Held CFO RMS, Hz")
    axes[1].set_title("Same-target held CFO")
    for ax in axes:
        ax.set_xticks(x, labels, rotation=18)
        ax.grid(axis="y", alpha=0.2)
        ax.axvline(len(points) - 1.5, color="#9ca3af", linestyle="--", linewidth=0.8)
        ax.legend()
    fig.suptitle("Carrier transfer at the selected containing location")
    fig.savefig(report / "clock-carrier-support.png", dpi=175)
    fig.savefig(report / "clock-carrier-support.pdf")
    plt.close(fig)
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id="clock-carrier-support",
            title="Anonymous carrier overlap and held CFO",
            sample="4 measured roof recordings · 1 separately labeled generated site",
            boundary="Archived native GLRT + causal TLE → unlinked held CFO forecast",
            note=(
                "The CFO panel compares identical held visits at the carried mode's chosen site. "
                "Blank CFO markers mean no jointly forecast target."
            ),
            seal="score-lock.json",
            image="clock-carrier-support.png",
            pdf="clock-carrier-support.pdf",
            csv="clock-carrier-support.csv",
        ),
    )


def execute(work, report):
    plan, rows = sealed(report)
    seed = whole_iq.checked(work / "private/seed.bin", plan["private_sim"]["seed_sha256"])
    sim = whole_iq.read(
        whole_iq.checked(work / "private/labels.json", plan["private_sim"]["labels_sha256"])
    )
    save_json(
        report / "simulation-release.json", dict(seed_hex=seed.read_bytes().hex(), labels=sim)
    )
    refs = references(rows)
    scored, pairs, identity = [], [], []
    predicted, queries = defaultdict(list), defaultdict(list)
    for row in rows:
        simulated = row["group"] == "simulated"
        ref = sim if simulated else refs[row["id"]]
        truth = ref["truth"]
        seen = set()
        records = row.get("records") or failure_rows(row)
        for record in records:
            offer = record["offer"]
            ident = f"{row['id']}-{offer}"
            bindings = dict(
                input_sha256=row["input_sha256"],
                native_sha256=row["native_sha256"],
                catalog_sha256=row["catalog_sha256"],
                tile=record["tile"],
            )
            score = score_row(ident, row, record, truth, ref)
            if (score["truth_tile_margin_km"] >= 0) != (offer == "containing"):
                raise ValueError("survey geometry disagrees with registered offer")
            if offer not in seen:
                queries[simulated].append(
                    dict(
                        id=ident,
                        condition=offer,
                        recording=row["id"],
                        truth=truth,
                        bindings=bindings,
                    )
                )
                seen.add(offer)
            predicted[simulated].append(
                dict(id=ident, method=record["method"], result=record["result"], **bindings)
            )
            scored.append(score)
            if record["method"] == "carried":
                matches = record["result"]["metrics"].get("retained_modes", [])
                for control in ("clock_only", "free_track", "identity_sham"):
                    pairs.append(
                        dict(
                            recording=row["id"],
                            group=row["group"],
                            offer=offer,
                            control=control,
                            **paired(matches, control),
                        )
                    )
                if simulated:
                    identity.extend(dict(offer=offer, **r) for r in sim_identity(matches, sim))
    csv_file(report / "scores.csv", scored)
    csv_file(report / "paired-rf.csv", pairs)
    save_json(report / "simulated-identity.json", identity)
    summary = defaultdict(list)
    for score in scored:
        cohort = "simulation" if score["group"] == "simulated" else "roof"
        summary[cohort, score["offer"], score["mode"]].append(score)
    save_json(
        report / "summary.json",
        dict(
            conditions=[
                dict(
                    cohort=cohort,
                    offer=offer,
                    mode=mode,
                    attempted=len(group),
                    published=sum(r["published_error_km"] is not None for r in group),
                    statuses=dict(Counter(r["status"] for r in group)),
                    forced_km=distribution(r["forced_error_km"] for r in group),
                    held_rf_rms_hz=distribution(r["held_rms_hz"] for r in group),
                )
                for (cohort, offer, mode), group in summary.items()
            ]
        ),
    )
    chart_ids = []
    for k, panel in ((False, "measured"), (True, "simulation")):
        chart_ids.extend(figures(report / panel, predicted[k], queries[k], k))
    figure_books.generate(
        report / "charts", ARMS, panel="screening", evidence=report, methods=chart_ids
    )
    support_figure(report, scored, pairs)
    names = (
        trial.LOCK,
        "scores.csv",
        "paired-rf.csv",
        "simulated-identity.json",
        "simulation-release.json",
        "summary.json",
        "charts/manifest.json",
        "stage-figure.json",
        "clock-carrier-support.csv",
        "clock-carrier-support.png",
        "clock-carrier-support.pdf",
    )
    save_json(
        report / "score-lock.json",
        dict(files={n: _sha(report / n) for n in names}, scorer_sha256=_sha(Path(__file__))),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--report", type=local_output, default=OUT)
    args = parser.parse_args()
    execute(args.work, args.report)


if __name__ == "__main__":
    main()
