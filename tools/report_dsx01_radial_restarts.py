"""Post-fit basin plots for independent regional association/localization starts.

This reporter consumes completed workers only. GPS is an evaluation marker;
neither its coordinates nor endpoint grouping feed back into inference.
"""

# ruff: noqa: E501

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from dsx01_inference_audit import CENTER
from localize_merged_track_catalogue import distance_km
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D

OUTPUT = Path("reports/2026_10_18_dsx01_radial_restarts")
ROOT = Path(__file__).resolve().parents[1]
RAW_OBSERVATIONS = ROOT / "reports/2026_10_16_dsx01_fast_association_losses/context-observations.jsonl"
REFERENCE = (37.849061591561885, -122.48574968092912)
ARMS = ("c0", "fitted_c")


def geographic_position(point):
    east, north = np.asarray(point, float)[:2]
    return (
        CENTER[0] + north / 111.0,
        CENTER[1] + east / (111.32 * np.cos(np.deg2rad(CENTER[0]))),
    )


def truth_position():
    return np.array(
        [
            (REFERENCE[1] - CENTER[1]) * 111.32 * np.cos(np.deg2rad(CENTER[0])),
            (REFERENCE[0] - CENTER[0]) * 111.0,
        ]
    )


def endpoint(arm):
    return np.asarray(
        arm.get("endpoint_east_north_km", arm["fit"]["parameters"][:2]), float
    )


def endpoint_groups(points, threshold_km=0.5):
    """Deterministic complete-link groups, with bounded maximum diameter.

    These are descriptive endpoint groups, not proofs of separate optima.
    Complete-link grouping prevents a chain of near endpoints spanning the map
    from being presented as one compact basin.
    """
    points = np.asarray(points, float).reshape(-1, 2)
    if threshold_km <= 0 or not np.isfinite(points).all():
        raise ValueError("finite endpoints and a positive grouping threshold are required")
    labels = np.empty(len(points), dtype=int)
    groups = []
    order = sorted(range(len(points)), key=lambda i: tuple(points[i]))
    for index in order:
        for label, members in enumerate(groups):
            if all(np.linalg.norm(points[index] - points[j]) <= threshold_km for j in members):
                members.append(index)
                labels[index] = label
                break
        else:
            labels[index] = len(groups)
            groups.append([index])
    return labels


def accepted_labels(arm):
    """Return explicit labels when workers persist them; never infer from GPS."""
    labels = arm.get("assignment_labels", arm.get("labels"))
    if isinstance(labels, dict):
        return {str(key): str(value) for key, value in labels.items()}
    rows = arm.get("association_rows", arm.get("rows", arm.get("track_associations", [])))
    return {
        str(row["component"]): str(row.get("candidate_norad", row.get("norad")))
        for row in rows
        if "component" in row and ("candidate_norad" in row or "norad" in row)
    }


def assignment_difference(first, second):
    """Count changed labels including membership changes over the label union."""
    left, right = accepted_labels(first), accepted_labels(second)
    if not left or not right:
        return None
    return sum(left.get(key) != right.get(key) for key in left.keys() | right.keys())


def finite_arm(arm):
    try:
        point = endpoint(arm)
        score = float(arm["fit"]["score"])
    except (KeyError, TypeError, ValueError):
        return False
    return point.shape == (2,) and bool(np.isfinite(point).all()) and np.isfinite(score)


def compact_fit(fit):
    result = {key: fit[key] for key in ("score", "stopped", "converged") if key in fit}
    if "parameters" in fit:
        result["parameters"] = fit["parameters"][:2]
    result["history"] = [
        dict(parameters=row["parameters"][:2])
        for row in fit.get("history", []) if "parameters" in row
    ]
    return result


def compact_arm(arm):
    """Discard large residual/covariance arrays before retaining worker data."""
    keys = (
        "endpoint_east_north_km", "associated_points", "total_glrt_points",
        "associated_tracks", "residual_rms_hz", "assignment_labels", "position_history",
    )
    result = {key: arm[key] for key in keys if key in arm}
    result["fit"] = compact_fit(arm.get("fit", {}))
    labels = accepted_labels(arm)
    if labels:
        result["assignment_labels"] = labels
    return result


def compact_record(data):
    result = {key: data[key] for key in (
        "case", "method", "start_id", "start_east_north_km", "total_glrt_points",
        "linear_nomination_anchor",
    ) if key in data}
    result["arms"] = {name: compact_arm(arm) for name, arm in data.get("arms", {}).items()}
    for key in ("rounds", "curved_parent_rounds"):
        if key not in data:
            continue
        result[key] = []
        for row in data[key]:
            item = {name: row[name] for name in ("anchor", "start_east_north_km") if name in row}
            if "fits" in row:
                item["fits"] = {name: compact_fit(fit) for name, fit in row["fits"].items()}
            if "arms" in row:
                item["arms"] = {name: compact_arm(arm) for name, arm in row["arms"].items()}
            result[key].append(item)
    return result


def raw_denominators(path=RAW_OBSERVATIONS):
    """Count unique raw GLRT observation IDs, including points outside tracks."""
    if not path.exists():
        return {}, None
    ids = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        ids.setdefault(f"DSX01-{row['source_id']}", set()).add(row["observation_id"])
    return {case: len(values) for case, values in ids.items()}, hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(records, threshold_km=0.5, totals=None):
    valid = [
        (data, arm, data["arms"][arm])
        for data in records
        for arm in ARMS
        if arm in data.get("arms", {}) and finite_arm(data["arms"][arm])
    ]
    groups = endpoint_groups([endpoint(row) for _, _, row in valid], threshold_km)
    center_reference = {}
    for name in ARMS:
        candidates = [data for data, arm, _ in valid if arm == name]
        if candidates:
            center_reference[name] = min(
                candidates,
                key=lambda data: (
                    np.linalg.norm(data["start_east_north_km"]), str(data["start_id"])
                ),
            )
    rows = []
    for (data, name, arm), group in zip(valid, groups, strict=True):
        fit = arm["fit"]
        point = endpoint(arm)
        other = data.get("arms", {}).get("fitted_c" if name == "c0" else "c0", {})
        total = (totals or {}).get(data["case"], arm.get("total_glrt_points", data.get("total_glrt_points")))
        count = arm.get("associated_points")
        rows.append(
            dict(
                case=data["case"],
                method=data["method"],
                start_id=data["start_id"],
                arm=name,
                start_east_km=float(data["start_east_north_km"][0]),
                start_north_km=float(data["start_east_north_km"][1]),
                endpoint_east_km=float(point[0]),
                endpoint_north_km=float(point[1]),
                position_error_km=distance_km(geographic_position(point), REFERENCE),
                score=float(fit["score"]),
                endpoint_group=int(group),
                associated_points=count,
                total_glrt_points=total,
                associated_percent=100 * count / total if count is not None and total else None,
                associated_tracks=arm.get("associated_tracks"),
                residual_rms_hz=arm.get("residual_rms_hz"),
                optimizer_stop=fit.get("stopped", fit.get("converged")),
                changed_labels_between_c_arms=assignment_difference(arm, other),
                changed_labels_vs_center_start=assignment_difference(
                    arm, center_reference[name]["arms"][name]
                ),
                label_reference_start_id=center_reference[name]["start_id"],
            )
        )
    for name in ARMS:
        chosen = [row for row in rows if row["arm"] == name]
        if not chosen:
            continue
        minimum = min(row["score"] for row in chosen)
        for row in chosen:
            row["loss_above_best_start_same_arm"] = row["score"] - minimum
    return rows


def decorate(ax, title):
    ax.add_patch(plt.Circle((0, 0), 10, fill=False, color="black", lw=0.9))
    ax.plot(0, 0, "+", color="black", ms=9, label="regional center")
    ax.plot(*truth_position(), "*", color="magenta", ms=12, label="GPS: evaluation only")
    ax.set(
        title=title,
        xlim=(-12.8, 12.8),
        ylim=(-12.8, 12.8),
        aspect="equal",
        xlabel="East from regional center (km)",
        ylabel="North (km)",
    )
    ax.grid(alpha=0.2)


def trajectory(arm, start):
    """Actual recorded iterates only; do not invent a trajectory from endpoints."""
    history = arm.get("position_history", arm["fit"].get("history", []))
    points = []
    for item in history:
        value = item.get("parameters", item.get("east_north_km")) if isinstance(item, dict) else item
        if value is not None:
            point = np.asarray(value, float)[:2]
            if point.shape == (2,) and np.isfinite(point).all():
                points.append(point)
    if not points:
        return None
    return np.vstack([start, points, endpoint(arm)])


def round_trajectories(data, name):
    """Keep round boundaries explicit, especially fitted-c's c0 re-anchors."""
    rounds = data.get("rounds") or data.get("curved_parent_rounds", [])
    paths = []
    for index, row in enumerate(rounds):
        anchor = row.get("start_east_north_km", row.get("anchor"))
        if anchor is None:
            continue
        if name in row.get("fits", {}):
            fit = row["fits"][name]
            arm = dict(fit=fit, endpoint_east_north_km=fit["parameters"][:2])
        else:
            arm = row.get("arms", {}).get(name)
        if arm is not None:
            path = trajectory(arm, anchor)
            if path is not None:
                paths.append((index, np.asarray(anchor), path))
    if not rounds or data.get("curved_parent_rounds"):
        anchor = data.get("linear_nomination_anchor", data["start_east_north_km"])
        path = trajectory(data["arms"][name], anchor)
        if path is not None:
            paths.append((len(rounds), np.asarray(anchor), path))
    return paths


def annotate_start(ax, start_id, point, *, pending=False):
    """Label the actual geographic initialization, not a later round anchor."""
    number = int(str(start_id).replace("start_", ""))
    east, north = np.asarray(point, float)
    label = f"S{number:02d}" + (" pending" if pending else "")
    label += f"\n({east:+g}, {north:+g}) km"
    ax.annotate(
        label,
        (east, north),
        xytext=(0, -11 if north >= 5 else 11),
        textcoords="offset points",
        ha="center",
        va="top" if north >= 5 else "bottom",
        fontsize=6.5 if pending else 7,
        color="0.48" if pending else "black",
        fontweight="normal" if pending else "bold",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none", alpha=0.88),
        zorder=7,
    )


def draw(records, rows, directory, threshold_km, planned_starts=None):
    case, method = records[0]["case"], records[0]["method"]
    by_id = {(str(row["start_id"]), row["arm"]): row for row in rows}
    palette = plt.get_cmap("turbo")
    maximum_group = max((row["endpoint_group"] for row in rows), default=0)
    planned_starts = planned_starts or [
        dict(start_id=r["start_id"], east_north_km=r["start_east_north_km"]) for r in records
    ]
    for mode in ("basins", "loss"):
        fig, axes = plt.subplots(1, 2, figsize=(13, 6.8), layout="constrained")
        for ax, name in zip(axes, ARMS, strict=True):
            selected = [row for row in rows if row["arm"] == name]
            losses = [np.log1p(row["loss_above_best_start_same_arm"]) for row in selected]
            norm = Normalize(vmin=0, vmax=max(losses, default=1) or 1)
            for planned in planned_starts:
                if (str(planned["start_id"]), name) not in by_id:
                    point = np.asarray(planned["east_north_km"])
                    ax.scatter(*point, facecolor="none", edgecolor="0.65", s=55, zorder=3)
                    annotate_start(ax, planned["start_id"], point, pending=True)
            for data in records:
                key = (str(data["start_id"]), name)
                if key not in by_id:
                    continue
                row, arm = by_id[key], data["arms"][name]
                start, end = np.array(data["start_east_north_km"]), endpoint(arm)
                color = (
                    palette(row["endpoint_group"] / max(maximum_group, 1))
                    if mode == "basins"
                    else plt.get_cmap("viridis")(norm(np.log1p(row["loss_above_best_start_same_arm"])))
                )
                for _, anchor, path in round_trajectories(data, name):
                    ax.plot(path[:, 0], path[:, 1], color=color, alpha=0.5, lw=0.9)
                    ax.scatter(*anchor, marker="s", c=[color], s=13, alpha=0.65)
                ax.annotate(
                    "", xy=end, xytext=start,
                    arrowprops=dict(arrowstyle="->", color=color, alpha=0.55, lw=0.65, linestyle=":"),
                )
                ax.scatter(*start, c=[color], s=68, edgecolor="black", linewidth=0.8, zorder=4)
                ax.scatter(*end, c=[color], marker="X", s=48, edgecolor="black", linewidth=0.4, zorder=5)
                annotate_start(ax, data["start_id"], start)
            decorate(ax, f"{case}: {method} / {name} ({len(selected)}/{len(planned_starts)} completed starts)")
            if mode == "loss":
                fig.colorbar(
                    plt.cm.ScalarMappable(norm=norm, cmap="viridis"), ax=ax, shrink=0.7,
                    label="log(1 + final loss above best start, same arm)",
                )
            if selected:
                error = np.array([row["position_error_km"] for row in selected])
                counts = [row["associated_points"] for row in selected if row["associated_points"] is not None]
                text = f"Endpoint error: {error.min():.2f}–{error.max():.2f} km; median {np.median(error):.2f} km"
                if counts:
                    text += f"\nAssociated points: {min(counts):,}–{max(counts):,}"
                ax.text(0.02, 0.02, text, transform=ax.transAxes, fontsize=8,
                        bbox=dict(facecolor="white", alpha=0.85, edgecolor="none"))
        handles, labels = axes[0].get_legend_handles_labels()
        handles += [
            Line2D([], [], marker="o", color="none", markerfacecolor="0.35", markeredgecolor="black"),
            Line2D([], [], marker="o", color="none", markerfacecolor="none", markeredgecolor="0.65"),
            Line2D([], [], marker="X", color="none", markerfacecolor="0.35"),
            Line2D([], [], marker="s", color="none", markerfacecolor="0.35", markersize=4),
        ]
        labels += ["completed start", "pending start", "fitted endpoint", "round anchor"]
        axes[0].legend(handles, labels, loc="upper right", fontsize=6.5, ncol=2)
        caption = (
            f"Endpoint colors: descriptive groups, maximum diameter {threshold_km:g} km (shared across c arms)."
            if mode == "basins"
            else "Final losses are compared only within the same scan, method, and c arm."
        )
        fig.suptitle(
            "Independent association/localization starts; fixed archived GLRT and graph tracks.\n"
            + caption + "\nStart labels S00–S12: (east, north) km from regional center; gray open circles are pending."
            "\nX: endpoints; squares: round anchors; solid: within-round iterates; dotted: displacement. No interpolated loss surface.",
            fontsize=9,
        )
        fig.savefig(directory / f"restart_{mode}.png", dpi=145)
        plt.close(fig)


def markdown_table(rows):
    text = "| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |\n| --- | ---: | ---: | --- | --- |\n"
    for name in ARMS:
        selected = [row for row in rows if row["arm"] == name]
        if not selected:
            text += f"| {name} | 0 | — | — | — |\n"
            continue
        errors = [row["position_error_km"] for row in selected]
        counts = [row["associated_points"] for row in selected if row["associated_points"] is not None]
        count_text = f"{min(counts):,}–{max(counts):,}" if counts else "not recorded"
        text += (
            f"| {name} | {len(selected)} | {len({row['endpoint_group'] for row in selected})} | "
            f"{min(errors):.3f} / {np.median(errors):.3f} / {max(errors):.3f} | {count_text} |\n"
        )
    return text


def run(output=OUTPUT, threshold_km=0.5):
    output = Path(output)
    protocol_path = output / "protocol.json"
    protocol = json.loads(protocol_path.read_text()) if protocol_path.exists() else {}
    totals, raw_digest = raw_denominators()
    render_path = output / "render_bindings.json"
    previous_render = json.loads(render_path.read_text()) if render_path.exists() else {}
    render_bindings, rendered = {}, 0
    reporter_digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    records, failures, bindings = {}, [], {}
    for path in sorted(output.glob("DSX*/*/start_*/result.json")):
        payload = path.read_bytes()
        data = compact_record(json.loads(payload))
        bindings[str(path.relative_to(output))] = hashlib.sha256(payload).hexdigest()
        records.setdefault((data["case"], data["method"]), []).append(data)
        for arm in ARMS:
            if not finite_arm(data.get("arms", {}).get(arm, {})):
                failures.append(dict(path=str(path.relative_to(output)), arm=arm, reason="missing/nonfinite arm"))
    for path in sorted(output.glob("DSX*/*/start_*/failure.json")):
        failures.append(dict(path=str(path.relative_to(output)), detail=json.loads(path.read_text())))
    all_rows, pages = [], []
    for (case, method), data in records.items():
        rows = summarize(data, threshold_km, totals)
        all_rows.extend(rows)
        directory = output / case / method
        key = f"{case}/{method}"
        group_binding = hashlib.sha256(json.dumps(dict(
            reporter=reporter_digest, threshold_km=threshold_km, raw=raw_digest,
            results={path: digest for path, digest in bindings.items() if path.startswith(key + "/")},
        ), sort_keys=True).encode()).hexdigest()
        render_bindings[key] = group_binding
        figures_present = all((directory / f"restart_{mode}.png").exists() for mode in ("basins", "loss"))
        if rows and (previous_render.get(key) != group_binding or not figures_present):
            draw(data, rows, directory, threshold_km, planned_starts=protocol.get("starts"))
            rendered += 1
        text = (
            f"# {case}: {method} independent-start results\n\n"
            "Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. "
            "This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.\n\n"
            + markdown_table(rows)
            + "\n![Independent-start endpoint groups](restart_basins.png)\n\n![Final objective by start](restart_loss.png)\n"
        )
        (directory / "README.md").write_text(text)
        pages.append(f"- [{case}: {method}]({case}/{method}/README.md)")
    if all_rows:
        with (output / "restart_summary.csv").open("w") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(all_rows[0]))
            writer.writeheader()
            writer.writerows(all_rows)
    receipt_path = output / "run_receipt.json"
    status_path = output / "worker_status.json"
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    failed_jobs = receipt.get("failures", []) or [
        {key: row[key] for key in ("case", "method", "start_id", "returncode", "log") if key in row}
        for row in status.get("results", []) if row.get("returncode")
    ]
    completed_count = sum(len(data) for data in records.values())
    expected_count = protocol.get("expected_pipeline_results", protocol.get("expected_worker_results"))
    audit = dict(
        completed_worker_results=completed_count,
        finite_arm_endpoints=len(all_rows),
        failures=failures,
        failed_campaign_jobs=failed_jobs,
        blocked_by_dependency=receipt.get("blocked_by_dependency", []),
        expected_pipeline_results=expected_count,
        missing_pipeline_results=max(0, expected_count - completed_count) if expected_count is not None else None,
        expected=protocol,
        endpoint_group_maximum_diameter_km=threshold_km,
        inference_uses_gps=False,
        grouping_used_for_inference=False,
        grouping_scope="each scan/method, jointly across both c arms",
        raw_glrt_denominator_source=str(RAW_OBSERVATIONS) if raw_digest else None,
        raw_glrt_denominator_source_sha256=raw_digest,
        raw_glrt_denominators=totals,
        groups_redrawn=rendered,
    )
    for filename, value in (("restart_summary.json", all_rows), ("report_audit.json", audit), ("result_bindings.json", bindings), ("render_bindings.json", render_bindings)):
        (output / filename).write_text(json.dumps(value, indent=2) + "\n")
    (output / "README.md").write_text(
        "# DSX01 independent regional pipeline restarts\n\n"
        f"Report contains {audit['completed_worker_results']:,} worker results and {len(all_rows):,} finite c-arm endpoints. "
        f"There are {len(failures):,} failed/missing/nonfinite arm or worker records and {len(failed_jobs):,} failed campaign jobs; consult [audit](report_audit.json) and the [protocol](protocol.json) for planned counts. Partial reports do not imply completion.\n\n"
        "Starts lie on a 5 km grid inside the 10 km disk centered at 37.906°, −122.545°. Localization is bounded by the same 25 × 25 km regional box. "
        "Existing conditional loss maps are preserved separately. Filled circles show completed independent starts, gray open circles show pending starts, and X marks fitted endpoints. "
        "Start labels give their IDs and (east, north) coordinates in km from the regional center; no interpolated loss surface is shown. "
        "The solid paths are recorded within-round optimizer iterates; squares mark round anchors and dotted arrows show net displacement only. "
        "The c0 endpoint supplies the next round's common anchor, so the fitted-c round paths can be discontinuous. Archived acquisition, GLRT, and graph tracks are fixed. "
        "GPS is added after fitting for error measurement and plotting; no endpoint is selected using GPS.\n\n"
        f"Endpoint groups are descriptive complete-link groups of maximum diameter {threshold_km:g} km within each scan/method, shared across c arms. "
        "They are not certified distinct optima. Final objective colors are normalized separately within each method, scan, and arm; objectives must not be compared across different model families.\n\n"
        "[Original and new plots for every configuration](comparisons/README.md) · "
        "[Per-start numerical results](restart_summary.csv) · [Result hashes](result_bindings.json)\n\n"
        + "\n".join(pages) + "\n"
    )
    from compare_dsx01_radial_figures import generate

    audit["comparison_gallery"] = generate(output)
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--endpoint-group-km", type=float, default=0.5)
    args = parser.parse_args()
    result = run(args.output, args.endpoint_group_km)
    print(json.dumps({key: value for key, value in result.items() if key != "expected"}))
