"""Audit genuine peer-retry trials and seal the timing and support comparison."""

import argparse
from collections import defaultdict
from math import ceil
from pathlib import Path

from ..__main__ import encoded, local_output, save_json, write
from ..scoring import distribution
from ..variants import peer_retry
from . import peer_retry_support as support
from . import peer_retry_trial as trial
from . import scout_stage_figures as plot
from .capture_runtime import read
from .full_v5_check import MARGIN_GATE, _sha, compare_probes
from .prefix_figures import csv_file
from .single_pass_trial import read_gzip

REPORT = support.REPORT


def raw_proposals(item):
    def project(row):
        return dict(
            integer_epoch_sample=row[1],
            fractional_epoch_offset_samples=0,
            fractional_tracking_cfo_hz=row[2],
        )

    return {key: [project(row) for row in item[key]] for key in ("coarse", "acquired")}


def support_rows(ident, rows):
    """Audit raw retained and refined proposals independently of the projection census."""
    channels = defaultdict(list)
    for row in rows:
        original = row["methods"]["conditional"]
        attempts = original["attempts"]
        for rx, probe in enumerate(original["probes"]):
            channels[(rx, probe["channel"])].append((row["visit"], row["traces"][:2]))
        if len(attempts) not in (2, 3):
            raise ValueError("unexpected original peer attempt count")
    for row in rows:
        original = row["methods"]["conditional"]
        if len(original["attempts"]) != 3 or not original["attempts"][2]["gate"]:
            continue
        rx = original["attempts"][2]["receiver"]
        target = original["probes"][rx]
        donors = [
            trace for visit, trace in channels[(rx, target["channel"])] if visit != row["visit"]
        ]
        for c in support.active(target):
            for stage in ("coarse", "acquired"):
                for label, lane in (("failed", (rx,)), ("peer", (1 - rx,)), ("both", (rx, 1 - rx))):
                    for limit in (1, 8):

                        def candidates(trace, lane=lane, stage=stage, limit=limit):
                            return [
                                r for ant in lane for r in raw_proposals(trace[ant])[stage][:limit]
                            ]

                        measured = support.compare(c, candidates(row["traces"][:2]))
                        controls = [support.compare(c, candidates(trace)) for trace in donors]
                        yield dict(
                            case=ident,
                            visit=row["visit"],
                            rx=rx,
                            cohort=row["cohort"],
                            rank=c["candidate_rank"],
                            stage=stage,
                            lane=label,
                            ranks_per_lane=limit,
                            matched_donors=len(donors),
                            **{key: int(outcome) for key, outcome in measured.items()},
                            **{
                                key + "_matched_sum": sum(item[key] for item in controls)
                                for key in measured
                            },
                        )


def audit(work):
    lock = read(work / "input-lock.json")
    if _sha(work / "input-lock.json") != _sha(REPORT / "input-lock.json"):
        raise ValueError("the measured replay does not match its published input lock")
    clocks, lanes, attempts, visits, raw = [], [], [], [], []
    resources = {}
    for name, policy in lock["cases"].items():
        receipt = read_gzip(work / f"{name}.json.gz")
        if (
            receipt["case"] != name
            or receipt["input_lock_sha256"] != _sha(work / "input-lock.json")
            or receipt["cpu"] not in trial.CPUS
            or not receipt["fine_calls"]
        ):
            raise ValueError("worker receipt did not authenticate the original detector trial")
        resources[name] = {k: receipt[k] for k in ("cpu", "peak_rss_kib", "fine_calls")}
        raw.extend(support_rows(name, receipt["rows"]))
        for index, (fixture, row) in enumerate(zip(policy["rows"], receipt["rows"], strict=True)):
            identity = dict(
                case=name,
                edge=policy["producer"]["edge"],
                visit=row["visit"],
                cohort=row["cohort"],
                iq_sha256=row["iq_sha256"],
            )
            base = row["methods"]["conditional"]
            retry = base["attempts"][2:]
            if (
                (fixture["visit"], fixture["cohort"]) != (row["visit"], row["cohort"])
                or encoded(fixture["probes"]) != encoded(base["probes"])
                or (row["cohort"] == trial.RESCUE and not any(r["gate"] for r in retry))
            ):
                raise ValueError("the evaluated capture lineage or rescue cohort changed")
            reference_retry = {r["receiver"]: r["gate"] for r in retry}
            for mode, result in row["methods"].items():
                visits.append(
                    dict(
                        **identity,
                        mode=mode,
                        retry=bool(retry),
                        public_exact=encoded(result["public"]) == encoded(base["public"]),
                        factors_exact=encoded(result["probes"]) == encoded(base["probes"]),
                    )
                )
                for before, after in zip(base["probes"], result["probes"], strict=True):
                    rx = before["receiver_id"]
                    comparison = compare_probes(before, after, 10_000_000)
                    matched = len(comparison["positive_matches"])
                    before_pub = base["public"]["receivers"][rx]
                    after_pub = result["public"]["receivers"][rx]
                    lanes.append(
                        dict(
                            **identity,
                            mode=mode,
                            receiver=rx,
                            retry=rx in reference_retry,
                            original_positive=bool(comparison["production_positive"]),
                            positive=bool(comparison["native_positive"]),
                            matched=matched,
                            original_candidates=comparison["production_positive"],
                            positive_candidates=comparison["native_positive"],
                            new_candidates=comparison["native_only"],
                            factors_exact=encoded(before) == encoded(after),
                            public_exact=encoded(before_pub) == encoded(after_pub),
                        )
                    )
                for number, r in enumerate(result["attempts"]):
                    candidates = r["public"]
                    complete = [c for c in candidates if c["fractional_epoch_status"] == "complete"]
                    positive = sum(c["fractional_margin"] >= MARGIN_GATE for c in complete)
                    if r["gate"] != bool(positive):
                        raise ValueError("observed fractional gate differs from public candidates")
                    attempts.append(
                        dict(
                            **identity,
                            mode=mode,
                            attempt=number,
                            receiver=r["receiver"],
                            retry=r["retry"],
                            anchors=len(r["anchors"]),
                            candidates=len(candidates),
                            integer_gate=sum(c["passed_margin_gate"] for c in candidates),
                            complete=len(complete),
                            fractional_gate=positive,
                            gate=r["gate"],
                            public_exact=encoded(candidates)
                            == encoded(base["attempts"][number]["public"]),
                        )
                    )
            timed = row["timings"]
            expected = [
                (repeat, i, peer_retry.MODES[(index + repeat + i) % 3])
                for repeat in range(trial.REPEATS)
                for i in range(3)
            ]
            if [(r["repeat"], r["slot"], r["mode"]) for r in timed] != expected:
                raise ValueError("counterbalanced timing receipt has incomplete coverage")
            clocks.extend(
                dict(**identity, retry=bool(retry), cpu=receipt["cpu"], **r) for r in timed
            )
    return resources, visits, lanes, attempts, clocks, raw


def timing(rows):
    baseline = {(r["case"], r["visit"], r["repeat"]): r for r in rows if r["mode"] == "conditional"}
    stats = {}
    for mode in peer_retry.MODES:
        arm = [r for r in rows if r["mode"] == mode]
        wall = [r["wall_ns"] / 1e6 for r in arm]
        savings = [
            (baseline[r["case"], r["visit"], r["repeat"]]["cpu_ns"] - r["cpu_ns"]) / 1e6
            for r in arm
        ]
        stats[mode] = dict(
            cpu_ms=distribution([r["cpu_ns"] / 1e6 for r in arm]),
            wall_ms=distribution(wall),
            at_most_20_ms=sum(v <= 20 for v in wall),
            coarse_ms=distribution([r["coarse_cpu_ns"] / 1e6 for r in arm]),
            paired_cpu_saving_ms=distribution(savings),
        )
    return stats


def aggregate(lanes):
    result = {}
    for mode in peer_retry.MODES:
        selected = [r for r in lanes if r["mode"] == mode]
        rescue = [r for r in selected if r["retry"] and r["original_positive"]]
        result[mode] = dict(
            probes=len(selected),
            original_positive=sum(r["original_positive"] for r in selected),
            positive=sum(r["positive"] for r in selected),
            probes_new_positive=sum(r["positive"] and not r["original_positive"] for r in selected),
            original_rescued_probes=len(rescue),
            matched_rescued_probes=sum(bool(r["matched"]) for r in rescue),
            original_rescued_candidates=sum(r["original_candidates"] for r in rescue),
            matched_rescued_candidates=sum(r["matched"] for r in rescue),
            new_candidates=sum(r["new_candidates"] for r in selected),
            factors_exact=sum(r["factors_exact"] for r in selected),
            public_exact=sum(r["public_exact"] for r in selected),
        )
    return result


def raw_summary(rows):
    result = {}
    for stage in ("coarse", "acquired"):
        for lane in ("failed", "peer", "both"):
            for ranks in (1, 8):
                unit = f"{stage}/{lane}/{ranks}"
                subset = [
                    r
                    for r in rows
                    if (r["stage"], r["lane"], r["ranks_per_lane"]) == (stage, lane, ranks)
                ]
                if not subset:
                    continue
                donors = sum(r["matched_donors"] for r in subset)
                metrics = [
                    k
                    for k in subset[0]
                    if k.startswith(("epoch", "alias", "literal"))
                    and not k.endswith("_matched_sum")
                ]
                result[unit] = dict(
                    targets=len(subset),
                    donor_comparisons=donors,
                    targets_with_matched_donors=sum(r["matched_donors"] > 0 for r in subset),
                    observed={key: sum(r[key] for r in subset) for key in metrics},
                    matched_null={
                        key: sum(r[key + "_matched_sum"] for r in subset) / donors
                        if donors
                        else None
                        for key in metrics
                    },
                )
    return result


def schedule_bounds(lanes):
    retry = [r for r in lanes if r["mode"] == "complement8" and r["retry"]]
    rescued = [r for r in retry if r["original_positive"]]
    recovered = sum(bool(r["matched"]) for r in rescued)
    missing = len(rescued) - recovered
    budget = ceil(len(retry) / 4)
    return dict(
        completed_retry_visits=len(retry),
        original_rescued_probes=len(rescued),
        complement_matched_probes=recovered,
        one_in_four_full_retry_budget=budget,
        expected_matched_probes_if_independent=recovered + missing / 4,
        target_informed_best_case_probes=recovered + min(missing, budget),
        full_retry_fraction_for_90_percent_retention=max(
            0, (0.9 * len(rescued) - recovered) / missing
        )
        if missing
        else None,
        timed=False,
    )


def chart(summary):
    title = "Replacing the original 22-anchor peer retry"
    note = (
        "Complete original dual-receiver detector clocks on authenticated saved IQ. "
        "The separate rescue cohort uses archived outcomes only for evaluation."
    )
    fig, axes = plot.canvas(title, "40 outcome-blind and 20 known-rescue visits", note)
    modes = ("conditional", "complement8")
    groups = ("outcome-blind", "retry-visits")
    t = summary["timing"]
    plot.paired(
        axes[0],
        ["Outcome-blind", "Original retry"],
        [tuple(t[group][mode]["cpu_ms"]["p50"] for mode in modes) for group in groups],
        title="Median complete detector CPU",
        xlabel="Host milliseconds",
        fmt=".1f",
    )
    r = summary["lanes"]
    plot.paired(
        axes[1],
        ["Outcome-blind", "Known-rescue"],
        [
            tuple(r[group][mode]["matched_rescued_probes"] for mode in modes)
            for group in ("outcome-blind", "known-rescue")
        ],
        title="Original rescued probes with a match",
        xlabel="Physical receiver-probes",
        fmt=".0f",
    )
    plot.key(fig, "Original 12/22 anchors", "Original primaries + eight-anchor retry")
    fig.savefig(REPORT / "stage.png", dpi=165, facecolor="white")
    fig.savefig(REPORT / "stage.pdf", facecolor="white", metadata={"CreationDate": None})
    plot.plt.close(fig)
    save_json(
        REPORT / "stage-figure.json",
        dict(
            version=1,
            id="peer-retry-complement8",
            title=title,
            sample="40 outcome-blind and 20 known-rescue dual visits on four recordings",
            boundary="Resident CI16 through original dual detection, retry and projection",
            note=note,
            seal="qualification-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="timing.csv",
        ),
    )


def publish(work):
    resources, visits, lanes, attempts, clocks, raw = audit(work)

    def cohort(rows, label):
        return [r for r in rows if r["cohort"] == label]

    groups = (trial.BLIND, trial.RESCUE)
    summary = dict(
        resources=resources,
        timing={group: timing(cohort(clocks, group)) for group in groups}
        | {"retry-visits": timing([r for r in clocks if r["retry"]])},
        lanes={group: aggregate(cohort(lanes, group)) for group in groups},
        per_case={
            name: {
                group: aggregate([r for r in cohort(lanes, group) if r["case"] == name])
                for group in groups
            }
            for name in resources
        },
        raw_primary_proposals=raw_summary(raw),
        one_in_four_full_retry_diagnostic={
            group: schedule_bounds(cohort(lanes, group)) for group in groups
        },
    )
    files = ("input-lock.json", "PROTOCOL.md", "primary-support.csv", "primary-support.json")
    for name, data in (
        ("visits", visits),
        ("lanes", lanes),
        ("attempts", attempts),
        ("timing", clocks),
        ("raw-primary-support", raw),
    ):
        name += ".csv"
        csv_file(REPORT / name, data)
        files += (name,)
    for ident in resources:
        for suffix in (".json.gz", ".log"):
            name = ident + suffix
            write(REPORT / name, (work / name).read_bytes())
            files += (name,)
    save_json(REPORT / "summary.json", summary)
    chart(summary)
    files += ("summary.json", "stage-figure.json", "stage.png", "stage.pdf")
    save_json(
        REPORT / "qualification-lock.json",
        dict(
            publisher_sha256=_sha(Path(__file__)),
            files={name: _sha(REPORT / name) for name in files},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    publish(parser.parse_args().work)
