"""Read-only selected-IQ arithmetic review; not a native precision certificate.

No full raw-IQ stream is available in this profile. Source association uses
recorded owned views plus exact consistency of every overlapping retained cut.
The independent test oracles are review-only and never deployed on the ARM.
"""

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from validate_native_admission import rotated, check_rotation
from tools.review_glrt_iq_probe import capture
from tools.starlink_glrt_tracking_abi import TrackingSnapshot
from tools.starlink_glrt_tracking_journal import review as native_review
from tools.review_glrt_cpu_live_epochs import review_epochs
from tools import review_glrt_cpu_startup
from tools.starlink_glrt_native_replay import rotate
from tests.starlink_glrt.test_cpu_coarse import integer_grid, bank
from tests.starlink_glrt.test_tracking_resolver import oracle
from tests.starlink_glrt.test_tracking_solver import moments
from tests.starlink_glrt.test_native_solver import dense_fit
from review_live_observer import review as observer_review


def review(root):
    rotation_checks = check_rotation()
    status = json.loads((root / "stdout.json").read_text())
    op = json.loads((root.parent / "operator.json").read_text())
    # This qualification entry point is for the built causal-startup probe.
    # Older captures cannot be relabeled as physical execution of this policy.
    # This build distinguishes pre-acquisition epoch-zero boot counters from
    # losses within a nonzero acquisition epoch. The finite child is unchanged.
    assert (
        op["payload_sha256"]["probe"]
        == "360d81ee27bb30b0f350e2d6e56f587895ab34c84e61e58d5fc0c15f4110007e"
    )
    observer = observer_review(root)
    rate = status["rate"]
    ratio = rate // 2500000
    assert rate in (30000000, 60000000) and status["status"] == op["exit_code"] == 0
    assert op["rf_sample_limit"] == 50331648
    assert op["rf_duration_limit_s"] == 20.1326592
    assert status["retention_mode"] == "full"
    assert op["before"] == op["after"] and op["temporary_files_removed"]
    rf = dict(op["rf_after"])
    initial = dict(op["configured"]["rf_state"])
    assert abs(int(rf.pop("rx_lo")) - op["lo_plan_hz"][-1]) <= 16
    assert abs(int(initial.pop("rx_lo")) - op["lo_plan_hz"][0]) <= 16
    assert rf == initial
    assert op["memory"]["required_kib"] == 360 * 1024
    assert op["memory"]["available_kib"] >= 360 * 1024
    for name, receipt in op["artifacts"].items():
        if receipt is None:
            assert not (root.parent / name).exists()
            continue
        raw = (root.parent / name).read_bytes()
        assert receipt["bytes"] == len(raw) and receipt["sha256"] == hashlib.sha256(raw).hexdigest()
    pair = lambda w, k: int(w[k]) + (int(w[k + 1]) << 32)
    blocks = []
    snapshots = []
    bindings = []
    final = None
    for line in (root / "capture.txt").read_text().splitlines():
        if not line:
            continue
        key, wire = line.split(" ", 1)
        if key == "capture_snapshot":
            gen, w = capture(wire, rate)
            number = len(blocks) + 1
            assert pair(w, 4) >= number * 16384 and pair(w, 6) >= number * 16384 and w[19] & 8
            assert pair(w, 0) % ratio == pair(w, 2) % ratio == 0
            assert pair(w, 2) == pair(w, 0) + (pair(w, 4) - 1) * ratio
            assert pair(w, 42) >= pair(w, 2)
            if blocks:
                assert gen > blocks[-1][0] and pair(w, 0) == pair(blocks[-1][1], 0)
                assert pair(w, 42) >= pair(blocks[-1][1], 42)
            blocks.append((gen, w))
        elif key == "capture_final_snapshot":
            _, final = capture(wire, rate)
        elif key == "epoch_binding":
            bindings.append(list(map(int, wire.split())))
        elif key == "tracking_snapshot":
            snapshots.append(TrackingSnapshot.from_sysfs(wire))
    assert len(blocks) == status["completed_refills"] == status["blocks"] == 1536
    assert len(blocks) * 16384 == pair(final, 4) == pair(final, 6) == 25165824
    assert not final[19] & 3
    for binding in bindings:
        assert binding[3] == binding[2] // ratio + 1
        assert any(s.epoch == binding[1] and s.latest_index == binding[2] for s in snapshots)
    for state in snapshots:
        state.require_drained()
        assert state.rate == rate and state.faults in (0, 8)
    for state in snapshots[1:]:
        assert state.cdc_drops == state.pacer_drops == 0
    assert snapshots[-1].faults == snapshots[-1].configured == 0
    assert not snapshots[-1].status & 16
    origin = pair(blocks[0][1], 0) // ratio - 53
    source_end = origin + len(blocks) * 16384
    rows = [json.loads(line) for line in (root / "worker.jsonl").read_text().splitlines()]
    journals = {"native.journal": (root / "native.journal").read_bytes()}
    epochs = review_epochs((root / "capture.txt").read_text(), rows, journals, status)
    if status["status"] == 1:
        assert status["stage"] == "worker_complete" and status["worker_complete"] == 1
        terminals = [r for r in rows if r["kind"] == "native_terminal"]
        assert terminals and terminals[-1]["result"] == -4
        assert sum(t["retained_popped"] for t in terminals) == status["native_results"] > 0
    scans = [r for r in rows if r["kind"] == "scan"]
    full = np.memmap(root / "iq.ci16", mode="r", dtype="<i2").reshape(-1, 2)
    assert len(full) == 25165824
    searched = np.concatenate(
        [full[r["window_start"] - origin : r["window_start"] - origin + 14000] for r in scans]
    )
    owned = np.fromfile(root / "worker.iq.ci16", dtype="<i2").reshape(-1, 2)
    assert status["retained_scan_samples"] == 0 and len(searched) == len(scans) * 14000
    assert len(owned) <= 6000000 and 0 < len(scans) <= status["attempts"] <= 6
    grids = np.fromfile(root / "grids.u32", dtype="<u4").reshape(len(scans), 11, 3333)
    refs = np.fromfile(root.parent.parent / "direct-references.ci16", dtype="<i2").reshape(
        4, 3300, 4
    )
    bases = []
    for raw in refs:
        ref = raw[:, 0].astype(float) + 1j * raw[:, 1]
        derivative = raw[:, 2].astype(float) + 1j * raw[:, 3]
        t = (2 * np.arange(3300) - 3299) / 5000000
        bases.append(np.column_stack((ref, -derivative, 2j * np.pi * 1000 * t * ref)))
    cuts = []
    cursor = 0
    fits = 0
    hypotheses = 0
    ranking = 0
    timings = []
    accepted_total = 0
    startup_jobs = startup_forecasts = 0

    def retain_view(start, iq, view, recorded_ns):
        assert binding[3] <= start and start + len(iq) <= source_end
        assert view["first"] <= start and start + len(iq) <= view["end"] <= view["source_now"]
        assert view["end"] - view["first"] <= 5000000
        assert view["epoch"] == binding[1] and view["valid"] and not view["closed"]
        assert view["observed_ns"] <= recorded_ns and view["generation"] > 0
        np.testing.assert_array_equal(iq, full[start - origin : start - origin + len(iq)])
        cuts.append((start, iq))

    for index, scan in enumerate(scans):
        if index % 50 == 0:
            print(
                json.dumps(
                    {"phase": "independent_scan_review", "completed": index, "total": len(scans)}
                ),
                file=sys.stderr,
                flush=True,
            )
        binding = next(b for b in bindings if b[1] == scan["epoch"])
        assert scan["attempt"] == index + 1 and scan["epoch"] == binding[1]
        assert "scan_iq_offset" not in scan
        cut = searched[index * 14000 : (index + 1) * 14000]
        retain_view(scan["window_start"], cut, scan["source"], scan["completed_ns"])
        np.testing.assert_array_equal(grids[index], integer_grid(cut, bank()))
        rr = [r for r in rows if r.get("attempt") == scan["attempt"]]
        if not scan["peaks"]:
            assert not grids[index].any()
            continue
        order = next(r for r in rr if r["kind"] == "candidate_order")
        powers = []
        ref = bases[0][:, 0]
        for epoch, frequency, score in scan["peaks"]:
            assert int(grids[index, frequency, epoch]) == score
            x = cut[epoch + 22 : epoch + 3322].astype(float)
            z = x[:, 0] + 1j * x[:, 1]
            powers.append(
                float(
                    max(abs(np.fft.fft(z * np.conj(ref), 16384)) ** 2)
                    / max(float(np.vdot(z, z).real * np.vdot(ref, ref).real), 1)
                )
            )
        np.testing.assert_allclose(order["single_pilot_power"], powers, rtol=2e-12, atol=2e-15)
        assert order["selected_rank"] == int(np.argmax(powers))
        ranking += len(powers)
        seed = next(r for r in rr if r["kind"] == 1)
        resolved = next(r for r in rr if r["kind"] == 2)
        assert seed["repeat"] == seed["fraction"] == 0
        assert seed["first"] == scan["window_start"] + scan["peaks"][order["selected_rank"]][0] + 14
        assert seed["start"] == seed["first"] + 8 and seed["starts"] == [8, 3341, 6675, 10008]
        assert seed["copied"]["source_now"] - scan["window_start"] <= 2500000
        accepted = []
        past = []
        for row in rr:
            if row["kind"] not in (1, 3):
                continue
            count = 13316 if row["kind"] == 1 else 3300
            assert row["iq_offset"] == cursor and row["iq_samples"] == count
            x = owned[cursor : cursor + count]
            assert len(x) == count
            cursor += count
            retain_view(
                row["first"],
                x,
                row["copied"] if row["kind"] == 1 else row["source"],
                row["recorded_ns"],
            )
            if row["kind"] == 1:
                np.testing.assert_allclose(
                    resolved["hypotheses"],
                    oracle(refs[0, :, :2], x, seed["starts"]),
                    rtol=2e-12,
                    atol=2e-8,
                )
                hypotheses += 17
                continue
            z = rotated(x, 0, row["phase_step"])
            phase = row["reference_phase"]
            assert list(moments(z, refs[phase].astype(np.int64)).words) == row["moments"]
            correction, coherence, _ = dense_fit(bases[phase], z)
            np.testing.assert_allclose(row["coherence"], coherence, rtol=2e-12, atol=2e-14)
            step = row["phase_step"]
            step = step if step < 2**31 else step - 2**32
            cfo = step * 2500000 / 2**32 + np.clip(correction[1], -0.25, 0.25) * 1000
            np.testing.assert_allclose(row["cfo_hz"], cfo, rtol=2e-12, atol=2e-8)
            rejection = (32 if np.any(abs(correction) >= 0.25) else 0) | (
                64 if coherence < 0.05 else 0
            )
            assert row["rejection"] == rejection and row["accepted"] == int(rejection == 0)
            past.append(row)
            fits += 1
            if row["accepted"]:
                accepted.append(row)
        terminal = next(r for r in rr if r["kind"] == "worker_terminal")
        startup = review_glrt_cpu_startup.review_startup_carrier(resolved["cfo_hz"], past)
        startup_jobs += startup["initial_jobs_checked"]
        startup_forecasts += startup["causal_forecasts_checked"]
        assert terminal["retained_past"] == len(past) <= 200
        assert terminal["supported_history"] == min(len(accepted), 96)
        accepted_total += len(accepted)
        if terminal["status"] == 1:
            assert len(accepted) >= 8 and all(r["accepted"] for r in past[:8])
            proposals = [r for r in rr if r["kind"] == 4]
            assert 1 <= len(proposals) <= 2
            handoff = proposals[-1]
            assert (
                handoff["frame"] > handoff["last_seen"]
                and handoff["frame"] + 7 <= handoff["last_supported"] + 32
            )
            assert handoff["start"] >= terminal["source"]["source_now"] + 12500
        timings.append(
            dict(
                attempt=scan["attempt"],
                worker_status=terminal["status"],
                accepted=len(accepted),
                past=len(past),
                scan_rank_ms=(order["completed_ns"] - scan["started_ns"]) / 1e6,
                worker_ms=(terminal["completed_ns"] - order["completed_ns"]) / 1e6,
            )
        )
    assert cursor == len(owned)
    observer_iq = np.fromfile(root / "observer.iq.ci16", dtype="<i2").reshape(-1, 2)
    for row in map(json.loads, (root / "observer.jsonl").read_text().splitlines()):
        if row["kind"] != "measurement":
            continue
        binding = next(b for b in bindings if b[1] == row["epoch"])
        cut = observer_iq[row["iq_offset"] : row["iq_offset"] + 3300]
        assert len(cut) == 3300
        retain_view(row["first"], cut, row["source"], row["recorded_ns"])
    overlap_samples = 0
    active = []
    for start, iq in sorted(cuts, key=lambda cut: cut[0]):
        active = [(a, x) for a, x in active if a + len(x) > start]
        for a, x in active:
            end = min(start + len(iq), a + len(x))
            count = end - start
            np.testing.assert_array_equal(iq[:count], x[start - a : start - a + count])
            overlap_samples += count
        active.append((start, iq))
    heads = epochs["native_results"]
    supported = sum(e["supported"] for e in epochs["episodes"])
    assert heads == status["native_results"]
    return dict(
        status="pass",
        scope="full_iq_two_frequency_visit_acquisition_arithmetic_and_source_counters",
        passive_observer=observer,
        run_succeeded=status["status"] == 0,
        post_capture_rf_settings_checked="rf_after" in op,
        full_iq_retained=True,
        live_tracking_qualified=False,
        native_numerical_review_required=bool(heads),
        rate=rate,
        exported_samples=pair(final, 4),
        returned_samples=len(blocks) * 16384,
        rf_seconds=pair(final, 4) / 2500000,
        coarse_origin=origin,
        epoch_bindings=bindings,
        epoch_review=epochs,
        cdc_drops=0,
        pacer_drops=0,
        attempts=status["attempts"],
        complete_searches=len(scans),
        grid_values_checked=int(grids.size),
        ordering_scores_checked=ranking,
        resolver_hypotheses_checked=hypotheses,
        moment_and_dense_fits_checked=fits,
        accepted_past_observations=accepted_total,
        retained_scan_samples=len(searched),
        retained_worker_samples=len(owned),
        overlapping_samples_checked=overlap_samples,
        native_results=heads,
        reported_native_support=supported,
        max_refill_gap_ns=status["max_refill_gap_ns"],
        timings=timings,
        rotation_scalar_oracle_checks=rotation_checks,
        startup_jobs_checked=startup_jobs,
        startup_forecasts_checked=startup_forecasts,
        startup_reviewer_sha256=hashlib.sha256(
            Path(review_glrt_cpu_startup.__file__).read_bytes()
        ).hexdigest(),
        rotation_module_sha256=hashlib.sha256(
            (Path(__file__).parent / "validate_native_admission.py").read_bytes()
        ).hexdigest(),
        sha256={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.iterdir()
            if p.is_file()
        },
        reviewer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )


if __name__ == "__main__":
    root = Path(sys.argv[1])
    result = review(root)
    with (root / "independent-visit-review.json").open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print(json.dumps(result))
