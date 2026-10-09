"""Full-membership descriptive residual audit; no fitting or operational choices."""

import json
from collections import Counter

import numpy as np

DATASETS = ("DS16", "DS17", "DS18")
ARMS = ("fitted-c", "zero-c")


def distribution(values):
    data = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    if not len(data):
        return dict(count=0, mean=None, median=None, p95=None, worst=None)
    return dict(
        count=len(data),
        mean=float(np.mean(data)),
        median=float(np.median(data)),
        p95=float(np.percentile(data, 95)),
        worst=float(np.max(data)),
    )


def summarize(plan, receipts, digest):
    members = plan["members"]
    labels = [m.get("member", m)["inventory_label"] for m in members]
    assert len(labels) == len(set(labels)) == 148, "Full148 frozen membership required"
    assert not (set(receipts) - set(labels)), "Unexpected receipt outside frozen membership"
    cases = []
    for binding in members:
        member = binding.get("member", binding)
        label = member["inventory_label"]
        receipt = receipts.get(label)
        if receipt is not None:
            assert receipt["member"] == member
            assert receipt["protocol_sha256"] == digest
            assert receipt["status"] in ("complete", "failed")
        cases.append(
            dict(
                member=member,
                loader_kind=binding.get(
                    "loader_kind", binding.get("loader_binding", {}).get("kind")
                ),
                status=receipt["status"] if receipt else "missing",
                error=receipt.get("error") if receipt else None,
                receipt=receipt,
            )
        )
    complete = all(c["status"] == "complete" for c in cases)
    groups = {}
    subsets = {d: [c for c in cases if c["member"]["dataset"] == d] for d in DATASETS}
    subsets["Pooled"] = cases
    if any(c["loader_kind"] is not None for c in subsets["DS16"]):
        subsets["DS16-original48"] = [
            c for c in subsets["DS16"] if c["loader_kind"] == "legacy_ds16"
        ]
        subsets["DS16-added15"] = [c for c in subsets["DS16"] if c["loader_kind"] != "legacy_ds16"]
    subsets["DS18-prior24"] = [
        c for c in subsets["DS18"] if c["member"].get("exposure") == "previously_evaluated_consumed"
    ]
    subsets["DS18-other10-consumed"] = [
        c for c in subsets["DS18"] if c["member"].get("exposure") != "previously_evaluated_consumed"
    ]
    for name, rows in subsets.items():
        groups[name] = dict(
            membership=len(rows), statuses=dict(Counter(c["status"] for c in rows)), arms=None
        )
        # Full-cohort aggregates remain withheld until every member is accounted successfully.
        if complete:
            groups[name]["arms"] = {
                arm: aggregate([c["receipt"]["arms"][arm] for c in rows]) for arm in ARMS
            }
    return dict(
        complete=complete,
        membership=148,
        cases=cases,
        groups=groups,
        scope="Descriptive consumed-data residual audit; no new fit or position improvement.",
    )


def aggregate(rows):
    pairs = [row["receiver_pairs"] for row in rows]
    eligible = [s for p in pairs for s in p["satellites"] if s["eligible"]]
    scan_bias = [
        float(np.median([abs(s["mean_hz"]) for s in p["satellites"] if s["eligible"]]))
        if p["eligible_satellite_count"]
        else None
        for p in pairs
    ]
    serial = [g for row in rows for g in row["serial_groups"]]
    return dict(
        scans=len(rows),
        counts={
            key: sum(row["counts"].get(key, 0) for row in rows)
            for key in ("total", "assigned", "eligible_assignment", "noise", "nonfinite")
        },
        paired_receiver=dict(
            orientation="RX1-RX0",
            pairs_total=sum(p["pairs_total"] for p in pairs),
            eligible_satellite_recording_groups=len(eligible),
            eligible_pair_count=sum(s["pair_count"] for s in eligible),
            recordings_with_eligible_group=sum(p["eligible_satellite_count"] > 0 for p in pairs),
            recordings_no_op=sum(p["no_op"] for p in pairs),
            per_scan_median_abs_group_mean_hz=distribution(scan_bias),
            signed_group_mean_hz=distribution([s["mean_hz"] for s in eligible]),
            group_pair_count=distribution([s["pair_count"] for s in eligible]),
            scope=(
                "Recording/satellite groups are descriptive correlated samples; "
                "no independence claim."
            ),
        ),
        temporal=dict(
            total_groups=len(serial),
            eligible_groups=sum(g["eligible"] for g in serial),
            correlation=distribution([g["correlation"] for g in serial if g["eligible"]]),
        ),
        glrt_margin=dict(
            scope="Descriptive associations; no quality filtering or operational cutoff.",
            residual_correlation=distribution(
                [row["margin"]["correlation_residual"] for row in rows]
            ),
            absolute_residual_correlation=distribution(
                [row["margin"]["correlation_abs_residual"] for row in rows]
            ),
        ),
        frequency_residuals={
            key: distribution([row.get("residuals", {}).get(key) for row in rows])
            for key in ("mean_hz", "median_hz", "rms_hz", "median_abs_hz", "p95_abs_hz")
        },
    )


def render(summary, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# B7 full-membership residual audit",
        "",
        "This audit reconstructs existing B7 residuals. It performs no new fit and "
        "establishes no position-accuracy improvement. Both c arms are reported separately. "
        "Satellite assignments and eligible groups follow one shared fitted-c policy; "
        "reference positions and errors do not select groups.",
        "",
        "| Dataset | Members | Complete | Failed | Missing |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, group in summary["groups"].items():
        status = group["statuses"]
        lines.append(
            f"| {name} | {group['membership']} | {status.get('complete', 0)} | "
            f"{status.get('failed', 0)} | {status.get('missing', 0)} |"
        )
    if not summary["complete"]:
        lines += [
            "",
            "**Full-cohort aggregate statistics withheld: missing or failed members remain.**",
        ]
        fig, ax = plt.subplots(figsize=(7, 4), constrained_layout=True)
        ax.bar(DATASETS, [summary["groups"][d]["statuses"].get("complete", 0) for d in DATASETS])
        ax.set_ylabel("Completed recordings (not residual magnitude)")
        ax.set_title("Residual audit coverage; aggregates withheld")
        fig.savefig(output / "coverage.png", dpi=160)
        plt.close(fig)
        lines += ["", "![Coverage](coverage.png)"]
    else:
        lines += [
            "",
            "| Dataset | Arm | Eligible groups | Eligible pairs | Scans with groups | "
            "No-op scans | Median scan absolute group-mean Hz | p95 scan Hz | "
            "Eligible temporal groups | Median temporal correlation |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for name, group in summary["groups"].items():
            for arm in ARMS:
                values = group["arms"][arm]
                pairs, temporal = values["paired_receiver"], values["temporal"]
                bias = pairs["per_scan_median_abs_group_mean_hz"]

                def fmt(value):
                    return "unavailable" if value is None else f"{value:.3f}"

                lines.append(
                    f"| {name} | {arm} | {pairs['eligible_satellite_recording_groups']} | "
                    f"{pairs['eligible_pair_count']} | {pairs['recordings_with_eligible_group']} | "
                    f"{pairs['recordings_no_op']} | {fmt(bias['median'])} | {fmt(bias['p95'])} | "
                    f"{temporal['eligible_groups']} | {fmt(temporal['correlation']['median'])} |"
                )
        fig, axes = plt.subplots(2, 1, figsize=(12, 7), constrained_layout=True, sharex=True)
        for arm in ARMS:
            pairs = [c["receipt"]["arms"][arm]["receiver_pairs"] for c in summary["cases"]]
            bias = [
                np.median([abs(s["mean_hz"]) for s in p["satellites"] if s["eligible"]])
                if p["eligible_satellite_count"]
                else np.nan
                for p in pairs
            ]
            axes[0].plot(range(1, 149), bias, ".", label=arm)
            axes[1].plot(
                range(1, 149), [p["eligible_satellite_count"] for p in pairs], ".", label=arm
            )
        for ax in axes:
            ax.axvline(63.5, color="gray", linestyle="--")
            ax.axvline(114.5, color="gray", linestyle="--")
            ax.legend()
        axes[0].set_ylabel("Median |paired group mean|, Hz")
        axes[1].set_ylabel("Eligible satellite groups")
        axes[1].set_xlabel("Frozen member order: DS16 1–63; DS17 64–114; DS18 115–148")
        fig.suptitle("Per-recording RX1−RX0 residuals; shared fitted-c eligibility")
        fig.savefig(output / "paired-per-scan.png", dpi=170)
        plt.close(fig)
        fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
        for ax, arm in zip(axes, ARMS, strict=True):
            groups = [
                s
                for c in summary["cases"]
                for s in c["receipt"]["arms"][arm]["receiver_pairs"]["satellites"]
                if s["eligible"]
            ]
            ax.hist([s["mean_hz"] for s in groups], bins=40)
            ax.set_title(
                f"{arm}: {len(groups)} groups / {sum(s['pair_count'] for s in groups)} pairs"
            )
            ax.set_xlabel("Satellite/recording paired residual mean, Hz")
            ax.set_ylabel("Group count (correlated samples)")
        fig.suptitle("Pooled descriptive receiver bias; no independent-sample inference")
        fig.savefig(output / "paired-group-bias.png", dpi=170)
        plt.close(fig)
        lines += [
            "",
            "![Per-recording paired residuals and eligibility](paired-per-scan.png)",
            "",
            "![Pooled group bias with sample counts](paired-group-bias.png)",
            "",
            "Each paired difference is RX1 minus RX0. Eligible counts and temporal "
            "correlations describe shared fitted-c groups; recording and satellite groups "
            "are correlated. GLRT-margin associations remain descriptive. "
            "No group is chosen using position accuracy, and improved in-sample residuals "
            "would not establish better localization.",
        ]
        lines += [
            "",
            "| Dataset | Arm | Median recording RMS Hz | p95 recording RMS Hz | "
            "Median recording absolute residual Hz |",
            "|---|---|---:|---:|---:|",
        ]
        for name, group in summary["groups"].items():
            for arm in ARMS:
                frequency = group["arms"][arm]["frequency_residuals"]
                lines.append(
                    f"| {name} | {arm} | {fmt(frequency['rms_hz']['median'])} | "
                    f"{fmt(frequency['rms_hz']['p95'])} | "
                    f"{fmt(frequency['median_abs_hz']['median'])} |"
                )
    lines += ["", "| Member | Session | Status | Failure |", "|---|---|---|---|"]
    for case in summary["cases"]:
        member = case["member"]
        error = str(case["error"] or "").replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {member['inventory_label']} | {member['session_id']} | {case['status']} | {error} |"
        )
    (output / "RESULTS.md").write_text("\n".join(lines) + "\n")


def main():
    import hashlib
    from pathlib import Path

    here = Path(__file__).resolve().parent
    raw = (here / "protocol.json").read_bytes()
    plan = json.loads(raw)
    root = here.parents[1]
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
    receipts = {p.stem: json.loads(p.read_text()) for p in (here / "results").glob("*.json")}
    render(summarize(plan, receipts, hashlib.sha256(raw).hexdigest()), here)


if __name__ == "__main__":
    main()
