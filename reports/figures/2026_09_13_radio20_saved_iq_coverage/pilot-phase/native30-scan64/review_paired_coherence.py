"""Compare coarse IQ and native retained moments for the same physical pilots.

Fixed timing uses the nearest supported quarter-coarse-sample reference to
the actual native start. A separately reported timing search is diagnostic,
not a new support gate or a detection-performance qualification.
"""

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from tools.starlink_glrt_tracking_journal import review as native_review
from tools.starlink_glrt_native_replay import rotate, coefficients
from tests.starlink_glrt.test_native_solver import dense_fit


def review(root):
    status = json.loads((root / "stdout.json").read_text())
    op = json.loads((root / "operator.json").read_text())
    rows = [json.loads(x) for x in (root / "worker.jsonl").read_text().splitlines()]
    pairs = [r for r in rows if r["kind"] == "native_coarse_iq"]
    if not pairs:
        assert status["native_results"] == 0 and (root / "native.coarse.ci16").read_bytes() == b""
        assert (root / "native.journal").read_bytes() == b"GLRJ1\n"
        assert op["artifacts"]["native.coarse.ci16"] == dict(
            bytes=0, sha256=hashlib.sha256(b"").hexdigest()
        )
        return dict(
            status="no_pairs",
            scope="same_pilot_coarse_iq_native_moment_comparison",
            pairs=0,
            native_total_results=0,
            live_tracking_qualified=False,
            reason="No acquisition reached native submission; numerical comparison is unavailable.",
            reviewer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        )
    terminal = next(r for r in rows if r["kind"] == "native_terminal")
    assert terminal["paired_result"] == 0
    rate = status["rate"]
    ratio = rate // 2500000
    assert rate in (30000000, 60000000) and op["rate"] == rate
    epoch = pairs[0]["source"]["epoch"]
    native = native_review((root / "native.journal").read_bytes(), epoch=epoch, rate=rate)
    assert (
        len(pairs)
        == terminal["paired_copied"]
        == terminal["paired_queued"]
        == min(64, len(native["heads"]))
    )
    iq = np.fromfile(root / "native.coarse.ci16", dtype="<i2").reshape(-1, 2)
    assert len(iq) == 3333 * len(pairs)
    digest = hashlib.sha256((root / "native.coarse.ci16").read_bytes()).hexdigest()
    assert op["artifacts"]["native.coarse.ci16"] == dict(bytes=4 * len(iq), sha256=digest)
    refs = np.fromfile(root.parent / "direct-references.ci16", dtype="<i2").reshape(4, 3300, 4)
    bases = []
    for raw in refs:
        ref = raw[:, 0].astype(float) + 1j * raw[:, 1]
        derivative = raw[:, 2].astype(float) + 1j * raw[:, 3]
        t = (2 * np.arange(3300) - 3299) / 5000000
        bases.append(np.column_stack((ref, -derivative, 2j * np.pi * 1000 * t * ref)))
    bank = Path(
        "/home/mouse9911/gits/plutosdr-fw-radio20-tracking/hdl/library/starlink_glrt/native_cubic_60000000_upper.mem"
    )
    raw = np.asarray(coefficients(bank.read_bytes(), rate_hz=rate), dtype=float)
    n = len(raw)
    ref = raw[:, 0] + 1j * raw[:, 1]
    derivative = raw[:, 2] + 1j * raw[:, 3]
    native_basis = np.column_stack(
        (ref, -derivative, 1j * np.pi * 1000 / rate * (2 * np.arange(n) - (n - 1)) * ref)
    )
    gram = native_basis.conj().T @ native_basis
    checked = []
    for index, row in enumerate(pairs):
        head = native["heads"][index]
        estimate = native["estimates"][index]
        head.require_complete()
        assert row["native_sequence"] == head.sequence == index and row["iq_offset"] == index * 3333
        assert row["iq_samples"] == 3333 and row["first"] == head.start // ratio - 16
        assert (
            row["native_start"],
            row["native_phase_step"],
            row["native_phase_seed"],
            row["native_reference_phase"],
            row["native_count"],
            row["native_fault"],
        ) == (
            head.start,
            head.phase_step,
            head.phase_seed,
            head.reference_phase,
            head.count,
            head.fault,
        )
        view = row["source"]
        assert view["epoch"] == epoch and view["valid"] and not view["closed"]
        assert (
            view["first"] <= row["first"]
            and row["first"] + 3333 <= view["end"] <= view["source_now"]
        )
        assert view["observed_ns"] <= row["recorded_ns"]
        cut = iq[index * 3333 : (index + 1) * 3333]
        phase0 = (head.phase_seed + (row["first"] * ratio - head.start) * head.phase_step) % 2**32
        step = head.phase_step * ratio % 2**32
        rotated = np.asarray(
            [rotate(int(i), int(q), (phase0 + k * step) % 2**32) for k, (i, q) in enumerate(cut)],
            dtype=np.int64,
        )
        fraction = head.start % ratio / ratio
        quarters = round(4 * fraction)
        carry, phase = divmod(quarters, 4)
        fixed = rotated[16 + carry : 16 + carry + 3300]
        correction, coherence, improved = dense_fit(bases[phase], fixed)
        energy = float(np.sum(fixed.astype(float) ** 2) / 3300)
        rejected = (32 if np.any(abs(correction) >= 0.25) else 0) | (64 if coherence < 0.05 else 0)
        scores = []
        for shift in range(-8, 9):
            x = rotated[16 + shift : 16 + shift + 3300].astype(float)
            z = x[:, 0] + 1j * x[:, 1]
            e = float(np.vdot(z, z).real)
            for ph, basis in enumerate(bases):
                r = basis[:, 0]
                score = float(abs(np.vdot(r, z)) ** 2 / (np.vdot(r, r).real * e))
                scores.append([shift, ph, score])
        best = max(scores, key=lambda x: x[2])
        # Independently recompute the native estimate from its retained
        # moments using the dense reference-space projection, not the C Gram.
        center = [
            (n - 1) * r - 2 * p
            for r, p in zip(head.reference_sum, head.reference_prefix_integral, strict=True)
        ]
        p = np.array(
            [
                complex(*head.reference_sum),
                complex(*head.delay_sum),
                -1j * np.pi * 1000 / rate * complex(*center),
            ]
        )
        projected = native_basis @ np.linalg.solve(gram, p)
        native_correction, _, _ = dense_fit(
            native_basis, np.column_stack((projected.real, projected.imag))
        )
        native_coherence = float(abs(p[0]) ** 2 / (gram[0, 0].real * head.observed_energy))
        direction = np.r_[1, np.clip(native_correction, -0.25, 0.25)]
        model = native_basis @ direction
        native_improved = float(
            abs(direction @ p) ** 2 / (np.vdot(model, model).real * head.observed_energy)
        )
        predicted = (
            (head.phase_step if head.phase_step < 2**31 else head.phase_step - 2**32) * rate / 2**32
        )
        expected = [
            direction[1] * 1e-6,
            direction[2] * 1000,
            predicted + direction[2] * 1000,
            native_coherence,
            native_improved,
        ]
        np.testing.assert_allclose(
            [
                estimate[k]
                for k in ("delay_s", "residual_hz", "cfo_hz", "coherence", "linearized_coherence")
            ],
            expected,
            rtol=2e-10,
            atol=2e-12,
        )
        native_rejection = (32 if np.any(abs(native_correction) >= 0.25) else 0) | (
            64 if native_coherence < 0.05 else 0
        )
        assert native_rejection == estimate["rejection"]
        checked.append(
            dict(
                sequence=index,
                frame=estimate["frame"],
                native_start=head.start,
                native_coherence=native_coherence,
                native_energy_per_sample=head.observed_energy / n,
                native_matched_energy_per_sample=native_coherence * head.observed_energy / n,
                native_rejection=native_rejection,
                native_delay_ns=estimate["delay_s"] * 1e9,
                native_residual_hz=estimate["residual_hz"],
                coarse_fraction=fraction,
                coarse_reference_phase=phase,
                coarse_start_carry=carry,
                coarse_coherence=float(coherence),
                coarse_linearized_coherence=float(improved),
                coarse_energy_per_sample=energy,
                coarse_matched_energy_per_sample=float(coherence) * energy,
                coarse_rejection=rejected,
                coarse_delay_ns=float(np.clip(correction[0], -0.25, 0.25)) * 1000,
                coarse_residual_hz=float(np.clip(correction[1], -0.25, 0.25)) * 1000,
                timing_search_best=best,
                timing_search_scores=scores,
            )
        )
    return dict(
        status="pass",
        scope="same_pilot_coarse_iq_native_moment_comparison",
        rate=rate,
        pairs=len(checked),
        native_total_results=len(native["heads"]),
        native_moments_independently_recomputed=False,
        live_tracking_qualified=False,
        coarse_supported=sum(x["coarse_rejection"] == 0 for x in checked),
        native_supported=sum(x["native_rejection"] == 0 for x in checked),
        comparisons=checked,
        sha256={
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in (
                "native.coarse.ci16",
                "native.journal",
                "worker.jsonl",
                "operator.json",
                "stdout.json",
            )
        },
        reviewer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )


if __name__ == "__main__":
    root = Path(sys.argv[1])
    result = review(root)
    with (root / "paired-coherence-review.json").open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "comparisons"}))
