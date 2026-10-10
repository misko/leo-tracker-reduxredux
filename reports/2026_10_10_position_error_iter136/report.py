"""Completion-gated descriptive audit reporting; no inference or reference ports."""

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARMS = ("fitted-c", "zero-c")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(here=HERE, root=ROOT):
    path = here / "protocol.json"
    plan = json.loads(path.read_text())
    labels = [m["label"] for m in plan["members"]]
    if len(labels) != 12 or len(set(labels)) != 12:
        raise ValueError("full fixed twelve required")
    for group in ("sources", "inputs"):
        for name, expected in plan[group].items():
            if sha(root / name) != expected:
                raise ValueError("frozen binding changed: " + name)
    receipts, hashes = {}, {}
    for label in labels:
        for suffix in (".json", ".claim.json"):
            file = here / "results" / (label + suffix)
            receipt = json.loads(file.read_text())
            if receipt["label"] != label or receipt["protocol_sha256"] != sha(path):
                raise ValueError("foreign receipt")
            hashes[str(file.relative_to(here))] = sha(file)
            if suffix == ".json":
                if receipt["status"] not in ("complete", "failed"):
                    raise ValueError("nonterminal member")
                receipts[label] = receipt
    return plan, receipts, hashes


def arm_summary(value, pair_count):
    details = value["pair_details"]
    if value["pairs"] != pair_count or len(details) != pair_count:
        raise ValueError("arm pair coverage mismatch")
    scores = [d["score"] for d in details]
    masses = [d["shared_label_mass"] for d in details]
    if not all(math.isfinite(x) for x in scores + masses) or any(
        x < 0 or x > 1 + 1e-12 for x in masses
    ):
        raise ValueError("invalid score/mass")
    if not math.isclose(sum(scores), value["score_sum"], rel_tol=1e-12, abs_tol=1e-10):
        raise ValueError("score summary mismatch")
    groups = value["groups"]
    if sum(g["pairs"] for g in groups) != pair_count:
        raise ValueError("group coverage mismatch")
    blocks = [g["alternating_blocks"] for g in groups]
    comparable = [b for b in blocks if all(x["pairs"] > 0 for x in b)]
    return dict(
        pairs=pair_count,
        score_sum=value["score_sum"],
        score_mean=value["score_mean"],
        positive_pairs=value["positive_pairs"],
        shared_label_mass_sum=sum(masses),
        shared_label_mass_mean=sum(masses) / pair_count if pair_count else None,
        groups=groups,
        groups_positive=sum(g["score_sum"] > 0 for g in groups),
        comparable_block_groups=len(comparable),
        both_blocks_positive=sum(all(x["score_sum"] > 0 for x in b) for b in comparable),
        both_blocks_negative=sum(all(x["score_sum"] < 0 for x in b) for b in comparable),
        opposite_block_signs=sum(b[0]["score_sum"] * b[1]["score_sum"] < 0 for b in comparable),
        frequency_nll=value["frequency_nll"],
        archive_objective_delta=value["archive_objective_delta"],
    )


def summarize(plan, receipts):
    if set(receipts) != {m["label"] for m in plan["members"]}:
        raise ValueError("incomplete membership")
    rows = []
    for member in plan["members"]:
        raw = receipts[member["label"]]
        support = raw.get("support")
        row = dict(
            label=member["label"],
            dataset=member["dataset"],
            status=raw["status"],
            error=raw.get("error"),
            elapsed_s=raw["total_elapsed_s"],
            observations=len(support["rows"]) if support else None,
            support_available=support["available"] if support else None,
            support_unavailable_reasons=support["unavailable_reasons"] if support else None,
        )
        if raw["status"] == "complete":
            pairing = raw["pairing"]
            n = row["observations"]
            used = [i for p in pairing["pairs"] for i in p]
            unpaired = [p["index"] for p in pairing["unpaired"]]
            if (
                len(set(used + unpaired)) != n
                or sorted(used + unpaired) != list(range(n))
                or raw["observations"] != n
                or pairing["observations"] != n
            ):
                raise ValueError("original row accounting mismatch")
            row.update(
                pairs=len(pairing["pairs"]),
                unpaired=len(unpaired),
                unpaired_reasons=pairing["reason_counts"],
                arms={arm: arm_summary(raw["arms"][arm], len(pairing["pairs"])) for arm in ARMS},
            )
            first, second = [raw["arms"][arm]["pair_details"] for arm in ARMS]

            def keys(ds):
                return [
                    (
                        d["first_window_id"],
                        d["second_window_id"],
                        d["group"],
                        d["alternating_block"],
                    )
                    for d in ds
                ]

            if keys(first) != keys(second):
                raise ValueError("c arms use different pairs")
        rows.append(row)
    complete = all(r["status"] == "complete" for r in rows)
    totals = None
    if complete:
        totals = dict(
            observations=sum(r["observations"] for r in rows),
            support_available=sum(r["support_available"] for r in rows),
            pairs=sum(r["pairs"] for r in rows),
            unpaired=sum(r["unpaired"] for r in rows),
        )
        for field in ("unpaired_reasons", "support_unavailable_reasons"):
            count = Counter()
            for row in rows:
                count.update(row[field])
            totals[field] = dict(count)
        totals["arms"] = {}
        for arm in ARMS:
            count = totals["pairs"]
            score = sum(r["arms"][arm]["score_sum"] for r in rows)
            mass = sum(r["arms"][arm]["shared_label_mass_sum"] for r in rows)
            totals["arms"][arm] = dict(
                score_sum=score,
                score_mean=score / count if count else None,
                shared_label_mass_sum=mass,
                shared_label_mass_mean=mass / count if count else None,
            )
    return dict(
        members=rows,
        complete=complete,
        totals=totals,
        runtime_s=sum(r["elapsed_s"] for r in rows),
        interpretation=(
            "Conditional score after full-data nuisance fitting; "
            "not rho, significance or position accuracy"
        ),
    )


def markdown(summary):
    lines = [
        "# Conditional frequency-correlation audit",
        "",
        "All twelve terminal members are included. Failed members remain explicit; "
        "full-cohort totals are withheld if any member failed.",
        "",
        "These are descriptive derivatives at zero correlation after full-data nuisance fitting. "
        "They are not estimates of rho, calibrated significance tests or position accuracy. "
        "No parameter is selected.",
        "",
        "| Member | Status | Rows | Support available | Pairs | Unpaired | "
        "Fitted-c mean score | c=0 mean score | Seconds |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    def fmt(x):
        return "unavailable" if x is None else f"{x:.6g}"

    for row in summary["members"]:
        means = [row.get("arms", {}).get(arm, {}).get("score_mean") for arm in ARMS]
        values = [row.get(k) for k in ("observations", "support_available", "pairs", "unpaired")]
        lines.append(
            f"| {row['label']} | {row['status']} | "
            + " | ".join(map(fmt, values + means + [row["elapsed_s"]]))
            + " |"
        )
        if row.get("error"):
            lines += ["", f"{row['label']} failure: `{row['error']}`", ""]
    lines += [
        "",
        f"Total recorded member elapsed time: {summary['runtime_s']:.3f} seconds.",
        "",
        "## Coverage and conditional summaries",
        "",
        "```json",
        json.dumps(summary["totals"], indent=2),
        "```",
        "",
        "## Group and alternating-block consistency",
        "",
        "Groups use fixed RX/channel/RF/edge identity. Alternating blocks contain disjoint pairs, "
        "but fitted nuisance parameters are shared; sign agreement is descriptive.",
        "",
        "| Member | Arm | Score sum | Shared-label mass sum | Positive groups | "
        "Comparable block groups | Both positive | Both negative | Opposite signs |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary["members"]:
        for arm, value in row.get("arms", {}).items():
            fields = [
                value[k]
                for k in (
                    "score_sum",
                    "shared_label_mass_sum",
                    "groups_positive",
                    "comparable_block_groups",
                    "both_blocks_positive",
                    "both_blocks_negative",
                    "opposite_block_signs",
                )
            ]
            lines.append(f"| {row['label']} | {arm} | " + " | ".join(map(fmt, fields)) + " |")
    lines += [
        "",
        "Per-group scores, alternating-block summaries, failure reasons and raw receipt hashes "
        "are retained in `summary.json`; raw receipts retain every support row and pair.",
    ]
    if summary["complete"]:
        lines += ["", "![Conditional score and pair coverage](conditional-scores.png)"]
    return "\n".join(lines) + "\n"


def plot(summary, path):
    if not summary["complete"]:
        raise ValueError("full matched coverage required for plot")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = summary["members"]
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, constrained_layout=True)
    for arm in ARMS:
        axes[0].plot(
            range(len(rows)),
            [r["arms"][arm]["score_mean"] if r["pairs"] else float("nan") for r in rows],
            "o-",
            label=arm,
        )
    axes[0].axhline(0, color="gray", linewidth=0.8)
    axes[0].set_ylabel("Mean conditional score per pair")
    axes[0].legend()
    axes[0].set_title("Descriptive zero-correlation score; no fitted rho or accuracy claim")
    axes[1].bar(range(len(rows)), [r["pairs"] for r in rows])
    axes[1].set_ylabel("Disjoint eligible pairs")
    axes[1].set_xticks(range(len(rows)), [r["label"] for r in rows], rotation=45, ha="right")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    plan, receipts, hashes = load()
    result = summarize(plan, receipts)
    result.update(protocol_sha256=sha(HERE / "protocol.json"), raw_sha256=hashes)
    (HERE / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    (HERE / "RESULTS.md").write_text(markdown(result))
    if result["complete"]:
        plot(result, HERE / "conditional-scores.png")


if __name__ == "__main__":
    main()
