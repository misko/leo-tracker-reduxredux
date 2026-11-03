"""Saved-corpus experiment; reference export and owned replay run in separate environments.

select freezes a channel-balanced random panel without reading GLRT outcomes.
oracle-export only reads the deployed public storage ports; it runs no detector.
replay uses repository-owned science and exported, hash-verified 20 ms IQ only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import multiprocessing
import random
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path


def digest(payload):
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def write(path, document):
    path.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")


def select_panel(dataset, output, *, per_channel=8, seed=20261010):
    manifest_bytes = (dataset / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    seal = json.loads((dataset / "seal.json").read_bytes())
    assert digest(manifest_bytes) == seal["files"]["manifest.json"]
    rng = random.Random(seed)
    members = []
    for capture in manifest["captures"]:
        entry = {
            k: capture[k] for k in ("dataset_label", "session_id", "sample_rate_hz", "source_kind")
        }
        if capture["sample_rate_hz"] != 2500000:
            entry.update(
                status="unsupported_rate", reason="native fast predictor requires 2.5 MS/s"
            )
        elif capture["source_kind"] != "published":
            entry.update(
                status="unpublished_archive",
                reason="no published IQ/analysis binding in frozen DS18",
            )
        else:
            payload = (dataset / capture["metadata_snapshot"]).read_bytes()
            assert digest(payload) == capture["metadata_snapshot_sha256"]
            metadata = json.loads(payload)
            events = metadata["receipt"]["events"]
            chosen = []
            for channel in sorted({e["target"]["channel"] for e in events}):
                indices = [e["visit_index"] for e in events if e["target"]["channel"] == channel]
                chosen.extend(rng.sample(indices, min(per_channel, len(indices))))
            entry.update(
                status="selected",
                visit_indices=sorted(chosen),
                manifest_sha256=capture["recording_manifest_sha256"],
            )
        members.append(entry)
    output.mkdir(parents=True, exist_ok=True)
    panel = {
        "dataset": "DS18",
        "manifest_sha256": digest(manifest_bytes),
        "seed": seed,
        "per_channel": per_channel,
        "probe_start_ms": 0,
        "probe_ms": 20,
        "selection": "random within recording/channel, before GLRT outcomes; both RX retained",
        "members": members,
    }
    path = output / "selection.json"
    if path.exists() and json.loads(path.read_bytes()) != panel:
        raise ValueError("refusing to change a frozen selection")
    write(path, panel)
    return panel


def export_member(member, root, output):
    # Numerical-oracle access only: the replay phase does not import these adapters.
    import numpy as np
    from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore

    store = AdaptiveHopIqStore(Path(root), read_only=True)
    analyses = AdaptiveHopAnalysisStore(Path(root), read_only=True)
    try:
        capture = store.inspect(member["session_id"])
        if capture.manifest_sha256 != member["manifest_sha256"]:
            raise ValueError("capture manifest changed since DS18 was sealed")
        geometry = capture.manifest.receipt.plan.geometry
        assert geometry.sample_rate_hz == 2500000 and tuple(geometry.receiver_ids) == (0, 1)
        binding = bind_actual_visit_analysis(
            capture.manifest.receipt,
            input_manifest_sha256=capture.manifest_sha256,
            probe_stride_ms=120,
        )
        rows = []
        windows = []
        with (
            analyses.job(binding) as job,
            store.reader(member["session_id"], expected=capture) as reader,
        ):
            metrics = job.manifest()
            if metrics is None:
                raise ValueError("existing GLRT analysis is not sealed")
            metrics_digest = digest(metrics.model_dump_json().encode())
            for visit_index in member["visit_indices"]:
                saved = job.read_visit(visit_index)
                visit, raw = reader.read_visit_ci16(visit_index)
                probes = [p.model_dump(mode="json") for p in saved.probes if p.probe_start_ms == 0]
                assert len(probes) == 2 and sorted(p["receiver_id"] for p in probes) == [0, 1]
                assert binding.configuration.probe_ms == 20
                assert int(saved.valid_start_counter) == visit.event.valid_start_counter
                window = np.ascontiguousarray(raw[:50000])
                assert window.shape == (50000, 2, 2)
                target = visit.event.target.model_dump(mode="json")
                target["lnb_lo_hz"] = geometry.lnb_lo_hz
                event = visit.event.model_dump(mode="json")
                rows.append(
                    {
                        "dataset_label": member["dataset_label"],
                        "session_id": member["session_id"],
                        "visit_index": visit_index,
                        "target": target,
                        "event": event,
                        "saved_actual_if_hz": saved.actual_if_center_hz,
                        "sample_start": visit.event.valid_start_counter,
                        "iq_sha256": digest(window.tobytes()),
                        "baseline_probes": probes,
                    }
                )
                windows.append(window)
        label = member["dataset_label"]
        output = Path(output)
        payload = np.stack(windows).tobytes()
        (output / f"{label}.ci16").write_bytes(payload)
        write(
            output / f"{label}.json",
            {
                "member": member,
                "binding": binding.model_dump(mode="json"),
                "metrics_document_sha256": metrics_digest,
                "iq_sha256": digest(payload),
                "rows": rows,
            },
        )
        return {"dataset_label": label, "status": "exported", "windows": len(rows)}
    except Exception as error:
        return {
            "dataset_label": member["dataset_label"],
            "status": "unavailable",
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        analyses.close()
        store.close()


PREDICTORS = {}


def replay_member(path):
    import numpy as np

    from leo.processing.fast_scan import predictor_factory
    from leo.scanner.fast_scan_analysis import VerifiedFastWindow, production_glrt

    path = Path(path)
    exported = json.loads(path.read_bytes())
    payload = path.with_suffix(".ci16").read_bytes()
    assert digest(payload) == exported["iq_sha256"]
    raw = np.frombuffer(payload, dtype="<i2").reshape(-1, 50000, 2, 2)
    results = []
    for metadata, window in zip(exported["rows"], raw, strict=True):
        assert digest(window.tobytes()) == metadata["iq_sha256"]
        edge = metadata["target"]["edge"]
        if edge not in PREDICTORS:
            PREDICTORS[edge] = predictor_factory(edge, 2)
        started = time.perf_counter_ns()
        scores = PREDICTORS[edge].score_ci16(window)
        fast_ms = (time.perf_counter_ns() - started) / 1e6
        sample = VerifiedFastWindow(
            metadata["visit_index"],
            metadata["iq_sha256"],
            {"actual_if_center_hz": metadata["event"]["actual_lo_frequency_hz"]},
            metadata["target"],
            window,
        )
        started = time.perf_counter_ns()
        glrt = production_glrt(sample, (0, 1))
        glrt_ms = (time.perf_counter_ns() - started) / 1e6
        results.append(
            {
                **metadata,
                "fast_scores": scores,
                "fast_ms": fast_ms,
                "glrt_ms": glrt_ms,
                "recomputed": [r.model_dump(mode="json") for r in glrt],
            }
        )
    return results


def best_margin(probe):
    values = [
        c["fractional_margin"]
        for c in probe["candidates"]
        if c.get("fractional_margin") is not None
    ]
    return max(values) if values else None


def summarize(results):
    import numpy as np

    from leo.contracts.fast_scan import FastScanPolicyV1

    cutoff = FastScanPolicyV1().threshold
    rows = []
    for result in results:
        pair_pass = max(s["margin"] for s in result["fast_scores"]) >= cutoff
        for rx in (0, 1):
            old = next(p for p in result["baseline_probes"] if p["receiver_id"] == rx)
            new = next(p for p in result["recomputed"] if p["receiver_id"] == rx)
            old_margin = best_margin(old)
            new_margin = best_margin(new)
            rows.append(
                {
                    "dataset_label": result["dataset_label"],
                    "session_id": result["session_id"],
                    "visit_index": result["visit_index"],
                    "channel": result["target"]["channel"],
                    "edge": result["target"]["edge"],
                    "receiver_id": rx,
                    "fast_score": result["fast_scores"][rx]["margin"],
                    "pair_pass": pair_pass,
                    "existing_margin": old_margin,
                    "recomputed_margin": new_margin,
                    "margin_delta": None
                    if old_margin is None or new_margin is None
                    else new_margin - old_margin,
                }
            )
    comparable = [r for r in rows if r["margin_delta"] is not None]
    deltas = np.array([r["margin_delta"] for r in comparable])
    strong = [r for r in comparable if r["existing_margin"] >= 0.1]
    active = [r for r in comparable if r["existing_margin"] >= 0.025]
    summaries = {}
    for edge in ("lower", "upper", "all"):
        part = [r for r in comparable if edge == "all" or r["edge"] == edge]
        x = np.array([r["fast_score"] for r in part])
        y = np.array([r["existing_margin"] for r in part])
        summaries[edge] = {
            "rx_windows": len(part),
            "pearson_fast_vs_existing": float(np.corrcoef(x, y)[0, 1]),
        }
    summary = {
        "visits": len(results),
        "receiver_windows": len(rows),
        "comparable_receiver_windows": len(comparable),
        "max_abs_margin_delta": float(abs(deltas).max()),
        "mean_abs_margin_delta": float(abs(deltas).mean()),
        "margins_within_1e_12": int(np.sum(abs(deltas) <= 1e-12)),
        "active_decision_disagreements": sum(
            (r["existing_margin"] >= 0.025) != (r["recomputed_margin"] >= 0.025) for r in comparable
        ),
        "strong_decision_disagreements": sum(
            (r["existing_margin"] >= 0.1) != (r["recomputed_margin"] >= 0.1) for r in comparable
        ),
        "fast_cutoff": cutoff,
        "pair_kept_visits": sum(
            max(s["margin"] for s in r["fast_scores"]) >= cutoff for r in results
        ),
        "existing_strong_rx_windows": len(strong),
        "strong_retained": sum(r["pair_pass"] for r in strong),
        "strong_retained_by_own_receiver_score": sum(r["fast_score"] >= cutoff for r in strong),
        "existing_active_rx_windows": len(active),
        "active_retained": sum(r["pair_pass"] for r in active),
        "fast_pair_median_ms": float(np.median([r["fast_ms"] for r in results])),
        "glrt_pair_median_ms": float(np.median([r["glrt_ms"] for r in results])),
        "correlations": summaries,
    }
    return rows, summary


def plot(rows, summary, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = ["#2563eb", "#ea580c", "#16a34a", "#dc2626"]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.7), layout="constrained")
    valid = [r for r in rows if r["margin_delta"] is not None]
    for channel, color in enumerate(colors, 1):
        group = [r for r in valid if r["channel"] == channel]
        axes[0].scatter(
            [r["existing_margin"] for r in group],
            [r["recomputed_margin"] for r in group],
            s=10,
            alpha=0.5,
            color=color,
            label=f"CH{channel}",
        )
        for axis, edge in zip(axes[1:], ("lower", "upper"), strict=True):
            part = [r for r in group if r["edge"] == edge]
            axis.scatter(
                [r["fast_score"] for r in part],
                [r["existing_margin"] for r in part],
                s=12,
                alpha=0.5,
                color=color,
                label=f"CH{channel}",
            )
    lim = max(r["existing_margin"] for r in valid) * 1.03
    axes[0].plot([0, lim], [0, lim], "k--", lw=1, label="Equal margin")
    axes[0].set(
        xlabel="Existing GLRT margin",
        ylabel="Recomputed GLRT margin",
        title="Same 20 ms IQ: GLRT agreement",
    )
    for axis, edge in zip(axes[1:], ("lower", "upper"), strict=True):
        axis.axvline(summary["fast_cutoff"], color="black", ls="--", lw=1)
        axis.axhline(0.1, color="black", ls=":", lw=1)
        corr = summary["correlations"][edge]["pearson_fast_vs_existing"]
        axis.set(
            xlabel="Fast pilot score (per RX)",
            ylabel="Existing GLRT margin",
            title=f"{edge.title()} edge · Pearson r = {corr:.3f}",
        )
    for axis in axes:
        axis.grid(alpha=0.18)
        axis.legend(fontsize=8)
    fig.suptitle(
        f"DS18 · {summary['visits']} paired visits · 2.5 MS/s · random examples across recordings\n"
        "GLRT also computed below the fast-score cutoff; cutoff unchanged",
        fontsize=12,
    )
    fig.savefig(output / "comparison.png", dpi=180)
    fig.savefig(output / "comparison.pdf")
    plt.close(fig)
    fig, axes = plt.subplots(2, 4, figsize=(15, 7), sharex=True, sharey=True, layout="constrained")
    for row, edge in enumerate(("lower", "upper")):
        for col, channel in enumerate(range(1, 5)):
            axis = axes[row, col]
            part = [r for r in valid if r["edge"] == edge and r["channel"] == channel]
            for rx, marker in ((0, "o"), (1, "x")):
                group = [r for r in part if r["receiver_id"] == rx]
                axis.scatter(
                    [r["fast_score"] for r in group],
                    [r["existing_margin"] for r in group],
                    s=14,
                    alpha=0.5,
                    color=colors[col],
                    marker=marker,
                    label=f"RX{rx + 1}",
                )
            axis.axvline(summary["fast_cutoff"], color="k", ls="--", lw=0.8)
            axis.axhline(0.1, color="k", ls=":", lw=0.8)
            axis.set_title(f"CH{channel} {edge} · n={len(part)}")
            axis.grid(alpha=0.18)
            axis.legend(fontsize=8)
            if row == 1:
                axis.set_xlabel("Fast pilot score")
            if col == 0:
                axis.set_ylabel("Existing GLRT margin")
    fig.suptitle("DS18: fast score versus saved GLRT, by channel and edge")
    fig.savefig(output / "per-channel.png", dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("select", "oracle-export", "replay"))
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    args = parser.parse_args()
    if args.phase == "select":
        panel = select_panel(args.dataset, args.output)
        print(
            json.dumps(
                {
                    "members": len(panel["members"]),
                    "selected": sum(m["status"] == "selected" for m in panel["members"]),
                }
            )
        )
    elif args.phase == "oracle-export":
        panel = json.loads((args.output / "selection.json").read_bytes())
        with ProcessPoolExecutor(
            max_workers=8, mp_context=multiprocessing.get_context("spawn")
        ) as pool:
            futures = [
                pool.submit(export_member, m, args.bulk_root, args.output)
                for m in panel["members"]
                if m["status"] == "selected"
            ]
            coverage = []
            for future in futures:
                item = future.result()
                coverage.append(item)
                print(json.dumps(item), flush=True)
        write(args.output / "export-coverage.json", coverage)
    else:
        coverage = json.loads((args.output / "export-coverage.json").read_bytes())
        paths = [
            args.output / f"{c['dataset_label']}.json"
            for c in coverage
            if c["status"] == "exported"
        ]
        started = time.perf_counter()
        with ProcessPoolExecutor(
            max_workers=8, mp_context=multiprocessing.get_context("spawn")
        ) as pool:
            results = [r for group in pool.map(replay_member, paths) for r in group]
        elapsed = time.perf_counter() - started
        write(args.output / "results.json", results)
        rows, summary = summarize(results)
        summary["eight_worker_replay_wall_s"] = elapsed
        write(args.output / "summary.json", summary)
        with (args.output / "comparison.csv").open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        plot(rows, summary, args.output)
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
