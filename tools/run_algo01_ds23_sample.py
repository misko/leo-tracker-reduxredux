"""Sealed random DS23 validation of the conservative ALGO01 composition.

Stages isolate the read-only public tracking adapter, causal input preparation,
and inference. Reference coordinates and geographic error are absent.
"""

import argparse
import copy
import dataclasses
import hashlib
import json
import random
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "reports/2026_10_18_ds23_post_ds22"
OUT = ROOT / "reports/2026_10_18_algo01_ds23_random20"
SEED = 2026101802
ARMS = ("c0", "fitted_c")


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    import numpy as np

    def serialize(x):
        if isinstance(x, np.ndarray):
            return x.tolist()
        if isinstance(x, np.generic):
            return x.item()
        raise TypeError(type(x).__name__)

    path.write_text(json.dumps(value, default=serialize, indent=2, allow_nan=False) + "\n")


def sample_members(members, count=20, seed=SEED):
    return random.Random(seed).sample(sorted(members, key=lambda r: r["dataset_label"]), count)


def seal():
    manifest_path = DATASET / "manifest.json"
    digest = "sha256:" + sha(manifest_path)
    if digest != (DATASET / "manifest.sha256").read_text().split()[0]:
        raise ValueError("DS23 membership authority mismatch")
    manifest = read(manifest_path)
    selected = sample_members(manifest["members"])
    old = {m["dataset_label"] for m in read(DATASET / "random_sample_10.json")["selected"]}
    compact = []
    for m in selected:
        compact.append(
            {
                k: m[k]
                for k in (
                    "dataset_label",
                    "recording_id",
                    "recording_format",
                    "case_id",
                    "captured_utc_ns",
                    "tracking_inputs",
                )
            }
        )
        compact[-1]["raw_authority_digest"] = m["raw_recording"]["identity_sha256"]
        compact[-1]["previously_sampled"] = m["dataset_label"] in old
    document = dict(
        dataset_id="DS23",
        manifest_sha256=digest,
        seed=SEED,
        population=len(manifest["members"]),
        sample_size=20,
        sampling="uniform without replacement, no substitutions or readiness filter",
        selected_before_any_new_fit=True,
        selected=compact,
        algorithm="ALGO01 conservative composition",
        original_regional_center=[37.906, -122.545],
        box_width_km=25,
        paired_c=True,
        GPS_used_for_sampling_or_inference=False,
    )
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "sample.json"
    if path.exists():
        if read(path) != document:
            raise ValueError("refusing to change the sealed sample")
    else:
        write(path, document)
    print(json.dumps(dict(seed=SEED, scans=[r["dataset_label"] for r in compact])), flush=True)


def export(case):
    # Executed with the deployed same-repository public input adapter on PYTHONPATH.
    import leo.storage.scanner_tracking_source as public_port

    member = next(m for m in read(OUT / "sample.json")["selected"] if m["dataset_label"] == case)
    directory = OUT / case
    directory.mkdir(exist_ok=True)
    receipt = directory / "input_receipt.json"
    if receipt.exists():
        old = read(receipt)
        if (
            old["status"] == "exported"
            and sha(directory / "tracking.json") != old["tracking_sha256"]
        ):
            raise ValueError("sealed tracking export changed")
        print(case, old["status"], flush=True)
        return
    result = dict(
        case=case,
        recording_id=member["recording_id"],
        recording_format=member["recording_format"],
        sample_sha256=sha(OUT / "sample.json"),
        public_adapter_path=public_port.__file__,
        public_adapter_sha256=sha(Path(public_port.__file__)),
        raw_authority_digest=member["raw_authority_digest"],
    )
    began = time.monotonic()
    try:
        if member["recording_format"] == "short_window_iq_recording":
            sources = member["tracking_inputs"]
            if not sources:
                raise ValueError("existing fast tracking contract unavailable")
            source = min(sources, key=lambda r: r["path"])
            raw = Path(source["path"]).read_bytes()
            if "sha256:" + hashlib.sha256(raw).hexdigest() != source["sha256"]:
                raise ValueError("frozen fast tracking authority changed")
            (directory / "tracking.json").write_bytes(raw)
            result.update(adapter="fast_tracking_contract", source_path=source["path"])
        elif member["recording_format"] == "starlink_adaptive_hop_iq":
            store = public_port.ScannerTrackingInputStore(
                Path("/srv/bulk/leo"), adaptive_probe_stride_ms=120
            )
            try:
                tracking = store.load(member["recording_id"])
            finally:
                store.close()
            if tracking.session_id != member["recording_id"]:
                raise ValueError("tracking belongs to another recording")
            document = dataclasses.asdict(tracking)
            document["timing"] = (
                tracking.timing.model_dump(mode="json") if tracking.timing else None
            )
            write(directory / "tracking.json", document)
            result.update(adapter="ScannerTrackingInputStore.load", qualified=tracking.qualified)
        else:
            raise ValueError("unsupported recording adapter")
        result.update(status="exported", tracking_sha256=sha(directory / "tracking.json"))
    except (ValueError, OSError, RuntimeError) as error:
        result.update(status="input_unavailable", reason=f"{type(error).__name__}: {error}")
    result["seconds"] = time.monotonic() - began
    write(receipt, result)
    print(case, result["status"], result.get("reason", ""), flush=True)


def prepare(case):
    import ds23_radio_noise as noise
    import evaluate_ds23_phase_refreshed as pilot
    import prepare_ds23_genuine_causal_prior as prior

    pilot.OUTPUT = OUT
    pilot.prepare(case)
    directory = OUT / case
    if read(directory / "prepared.json")["status"] != "prepared":
        return
    noise.run(directory)
    prior.SOURCE, prior.OUTPUT = OUT, OUT / "causal_prior"
    if not (prior.OUTPUT / case / "receipt.json").exists():
        prior.run(case)


def selected_supports(n):
    """Whole, prefix and suffix hypotheses; no hand-written breakpoint time."""
    supports = {(0, n)} | {(a, n) for a in range(1, n - 11)} | {(0, b) for b in range(12, n)}
    return sorted((a, b) for a, b in supports if b - a >= 12)


def final_scan(case):
    from evaluate_ds23_phase_refreshed import FreshScan

    scan = FreshScan(OUT / case, noise_mode="radio")
    prior = OUT / "causal_prior" / case
    scan.previous_tle_path = prior / "previous.tle"
    scan.receipt = read(prior / "receipt.json")
    return scan


def causal_fit(scan, node, keep, arm):
    from propagate_ds23_arc_positions import fit_position

    return fit_position(scan, node, keep, [], arm, "native")


def fit_and_gate(scan, node, keep, stage, max_rounds=4):
    """Monotone paired-arm rejection with equal data and budgets in each pair."""
    import numpy as np
    from audit_ds23_algo01_coverage import retained_metrics

    history = []
    for epoch in range(max_rounds):
        pair, rejected = {}, set()
        for arm in ARMS:
            p, record = causal_fit(scan, node, keep, arm)
            metrics = retained_metrics(p, record["fit"]["parameters"])
            pair[arm] = dict(record=record, metrics=metrics)
            rejected.update(r["component"] for r in metrics["tracks"] if not r["compatible"])
        history.append(
            dict(epoch=epoch, active_points=int(keep.sum()), rejected_components=sorted(rejected))
        )
        print(
            scan.case,
            stage,
            epoch,
            "points",
            int(keep.sum()),
            "rejected",
            len(rejected),
            flush=True,
        )
        if not rejected:
            return p, keep, pair, history, True
        if epoch == max_rounds - 1:
            break
        next_keep = keep.copy()
        for row, sl in zip(p.rows, p.slices, strict=True):
            if row["component"] in rejected:
                next_keep[sl] = False
        if not next_keep.any():
            return p, keep, pair, history, False
        assert np.all(~next_keep | keep)
        keep = next_keep
    return p, keep, pair, history, False


def salvage(scan, node, keep):
    """Apply the published all-catalogue shortlist and independently gated trim."""
    import numpy as np
    from investigate_ds23_adaptive_failures import repaired_fit
    from localize_merged_track_catalogue import raw_curvature
    from prototype_dsx01_continuous_position import latlon

    from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
    from leo.analysis.research.phase_linear_geometry import (
        phase_linear_frequency,
        prepare_phase_geometry,
    )
    from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
    from leo.analysis.research.retained_track_likelihood import profile

    # Leave all excluded tracks out of independent calibration. This unit-phase
    # calibration and 3s shortlist score reproduce the published salvage stages;
    # the final position refit uses causal, satellite-specific phase uncertainty.
    p, fitted, _, _ = repaired_fit(scan, node, "c0", "unit", keep)
    x = fitted["parameters"]
    state = p.state(x)
    repaired, retained, diagnostics = copy.deepcopy(node), keep.copy(), []
    for k, (i, sl) in enumerate(zip(p.members, p.slices, strict=True)):
        if keep[sl].any():
            continue
        track = scan.tracks[i]
        t, values = track["times"], track["values"]
        q = track["rf_hz"] / 11.5e9
        radio = scan.hardware(track, state["beta"])
        radio += q * scan.rx_basis[i] @ state["smooth"][track["receiver"] - 1]
        y, noise = values - radio, p.point_noise[sl]
        f, elevation, derivative = phase_linear_frequency(
            prepare_phase_geometry(scan.sky, t), *latlon(x)
        )
        coarse_phase = np.linspace(-10, 10, 81)
        prediction = q * (f[:, None] + derivative[:, None] * coarse_phase[None, :, None])
        terms = profile(y, prediction.reshape(-1, len(t)), np.diag(1 / noise))
        cost = terms["cost"].reshape(len(scan.norads), -1) + coarse_phase[None, :] ** 2 / 9
        cost[elevation.max(axis=1) < 0] = np.inf
        shortlist = set(map(int, np.argsort(cost.min(axis=1))[:30]))
        for lo in np.arange(t[0], t[-1], 20):
            m = (t >= lo) & (t < lo + 20)
            if m.sum() < 8:
                continue
            terms = profile(
                y[m], prediction[:, :, m].reshape(-1, int(m.sum())), np.diag(1 / noise[m])
            )
            cost = terms["cost"].reshape(len(scan.norads), -1) + coarse_phase[None, :] ** 2 / 9
            cost[elevation[:, m].max(axis=1) < 0] = np.inf
            shortlist.update(map(int, np.argsort(cost.min(axis=1))[:10]))
        shortlist.add(p.rows[k]["candidate_index"])
        alternatives = []
        grid = np.linspace(-15, 15, 121)
        supports = [
            (a, b)
            for a, b in selected_supports(len(t))
            if t[b - 1] - t[a] >= 20 and raw_curvature(dict(times=t[a:b], values=values[a:b]))
        ]
        for j in sorted(shortlist):
            bank = dict(
                time_s=scan.sky["time_s"],
                position_km=np.repeat(scan.sky["position_km"][[j]], len(grid), axis=0),
                velocity_km_s=np.repeat(scan.sky["velocity_km_s"][[j]], len(grid), axis=0),
            )
            ff, ee = paired_phase_frequency(
                bank,
                np.tile(t, len(grid)),
                np.repeat(np.arange(len(grid)), len(t)),
                grid,
                *latlon(x),
            )
            ff, ee = ff.reshape(len(grid), -1), ee.reshape(len(grid), -1)
            for a, b in supports:
                terms = profile(y[a:b], q * ff[:, a:b], np.diag(1 / noise[a:b]))
                cost = terms["cost"] + grid**2 / 9
                cost[ee[:, a:b].min(axis=1) < 0] = np.inf
                best = int(np.argmin(cost))
                residual = terms["residual"][best]
                screen = batch_noise_screen(residual[None], t[a:b])
                if (
                    terms["rms"][best] > 450
                    or abs(terms["bias"][best]) > 3000
                    or not np.isfinite(cost[best])
                    or not screen["noise_screen_pass"][0]
                    or np.max(abs(residual) / noise[a:b]) > 6
                ):
                    continue
                alternatives.append(
                    dict(
                        start_index=a,
                        stop_index=b,
                        points=b - a,
                        candidate_index=j,
                        norad=int(scan.norads[j]),
                        phase_s=float(grid[best]),
                        cost=float(cost[best]),
                        alias=int(terms["alias"][best]),
                        rms_hz=float(terms["rms"][best]),
                        max_external_radio_sigma=float(np.max(abs(residual) / noise[a:b])),
                    )
                )
        alternatives.sort(key=lambda a: (-a["points"], a["cost"]))
        chosen = alternatives[0] if alternatives else None
        diagnostics.append(
            dict(
                component=track["key"],
                candidate_count=len(shortlist),
                supports_tested=len(supports),
                selected=chosen,
                alternatives=alternatives[:5],
            )
        )
        if chosen:
            repaired["seed"]["rows"][k].update(
                candidate_index=chosen["candidate_index"], candidate_norad=chosen["norad"]
            )
            repaired["aliases"][k] = chosen["alias"]
            retained[sl.start + chosen["start_index"] : sl.start + chosen["stop_index"]] = True
        print(
            scan.case,
            "salvage",
            track["key"],
            "retained",
            chosen["points"] if chosen else 0,
            flush=True,
        )
    return repaired, retained, diagnostics


def infer(case):
    import numpy as np
    from audit_ds23_algo01_coverage import coverage
    from evaluate_ds23_phase_refreshed import extend_associations
    from propagate_ds23_arc_positions import PositionNormal

    directory = OUT / case
    if (directory / "result.json").exists():
        print(case, "already finished", flush=True)
        return
    prepared = read(directory / "prepared.json")
    if prepared["status"] != "prepared":
        write(directory / "result.json", dict(case=case, status=prepared["status"], GPS_used=False))
        return
    began = time.monotonic()
    # Separate discovery process is necessary because its read guard is global.
    original = read(directory / "fit_radio_noise.json")
    winner = next(
        c for c in original["choices"] if c["hypothesis"] == original["selected_hypothesis"]
    )
    node = copy.deepcopy(winner["node"])
    scan = final_scan(case)
    p = PositionNormal(scan, node, scan.radio_sigma_hz, False)
    keep = np.ones(len(p.values), bool)
    failed = {
        r["component"] for r in winner["arms"]["c0"]["metrics"]["tracks"] if not r["compatible"]
    }
    for row, sl in zip(p.rows, p.slices, strict=True):
        if row["component"] in failed:
            keep[sl] = False
    if not keep.any():
        write(
            directory / "result.json",
            dict(case=case, status="no_passing_calibration", GPS_used=False),
        )
        return
    p, keep, pair, before_history, stable = fit_and_gate(scan, node, keep, "exclude_refit")
    trims = []
    if stable and not keep.all():
        node, keep, trims = salvage(scan, node, keep)
        p, keep, pair, after_history, stable = fit_and_gate(scan, node, keep, "salvage_refit")
    else:
        after_history = []
    observations = read(directory / "observations.json")
    original_ids = {o["observation_id"] for o in observations}
    for arm in ARMS:
        saved = pair[arm]["record"]
        p = PositionNormal(
            scan,
            node,
            scan.radio_sigma_hz,
            arm == "fitted_c",
            reference=np.asarray(saved["phase_reference"]),
            keep=keep,
        )
        p.phase_sigma = np.asarray(saved["phase_widths_s"])
        x = saved["fit"]["parameters"]
        extended = extend_associations(p, x, pair[arm]["metrics"])
        pair[arm]["association"] = coverage(extended["tracks"], scan.tracks, original_ids)
        pair[arm]["association_tracks"] = extended["tracks"]
    write(
        directory / "result.json",
        dict(
            case=case,
            algorithm="ALGO01 batch composition",
            status="complete" if stable else "gate_refit_unstable",
            arms=pair,
            final_node=node,
            final_mask=keep,
            initial_failed_components=sorted(failed),
            trims=trims,
            exclusion_history=before_history,
            post_salvage_history=after_history,
            paired_masks_aliases_and_identities=True,
            GPS_used=False,
            future_TLE_used=False,
            source_sha256=sha(Path(__file__)),
            seconds=time.monotonic() - began,
        ),
    )
    print(
        case, "complete" if stable else "unstable", "seconds", time.monotonic() - began, flush=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage", required=True, choices=("seal", "export", "prepare", "discover", "infer")
    )
    parser.add_argument("--case")
    args = parser.parse_args()
    if args.stage == "seal":
        seal()
    elif args.stage == "discover":
        import evaluate_ds23_phase_refreshed as pilot

        pilot.OUTPUT = OUT
        pilot.fit_case(args.case, noise_mode="radio")
    else:
        if not args.case:
            parser.error("--case is required for this stage")
        {"export": export, "prepare": prepare, "infer": infer}[args.stage](args.case)
