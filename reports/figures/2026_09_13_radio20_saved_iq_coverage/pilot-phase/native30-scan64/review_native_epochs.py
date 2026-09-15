"""Independent dense numerical review of every retained native episode.

Native raw IQ is unavailable: this checks estimates from retained moments,
not the FPGA moment accumulation or physical estimation accuracy.
"""

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from tools.review_glrt_cpu_live_epochs import review_epochs
from tools.starlink_glrt_tracking_journal import review
from tools.starlink_glrt_native_replay import coefficients
from tests.starlink_glrt.test_native_solver import dense_fit


def check_estimate(head, estimate, basis, gram, rate):
    n = len(basis)
    head.require_complete()
    assert head.reference_phase == 0 and head.count == n
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
    projected = basis @ np.linalg.solve(gram, p)
    correction, _, _ = dense_fit(basis, np.column_stack((projected.real, projected.imag)))
    np.testing.assert_allclose(basis.conj().T @ projected, p, rtol=2e-12, atol=2e-5)
    coherence = abs(p[0]) ** 2 / (gram[0, 0].real * head.observed_energy)
    direction = np.r_[1, np.clip(correction, -0.25, 0.25)]
    model = basis @ direction
    improved = abs(direction @ p) ** 2 / (np.vdot(model, model).real * head.observed_energy)
    step = head.phase_step if head.phase_step < 2**31 else head.phase_step - 2**32
    expected = [
        direction[1] * 1e-6,
        direction[2] * 1000,
        step * rate / 2**32 + direction[2] * 1000,
        coherence,
        improved,
    ]
    reported = [
        estimate[k]
        for k in ("delay_s", "residual_hz", "cfo_hz", "coherence", "linearized_coherence")
    ]
    np.testing.assert_allclose(reported, expected, rtol=2e-10, atol=2e-12)
    rejection = (32 if np.any(abs(correction) >= 0.25) else 0) | (64 if coherence < 0.05 else 0)
    assert estimate["rejection"] == rejection
    return dict(estimate, native_start=head.start, energy_per_sample=head.observed_energy / n)


def main(root):
    rows = [json.loads(x) for x in (root / "worker.jsonl").read_text().splitlines()]
    status = json.loads((root / "stdout.json").read_text())
    op = json.loads((root / "operator.json").read_text())
    rate = status["rate"]
    journals = {
        name: (root / name).read_bytes()
        for name, receipt in op["artifacts"].items()
        if receipt is not None and name.startswith("native") and name.endswith(".journal")
    }
    epochs = review_epochs((root / "capture.txt").read_text(), rows, journals, status)
    bank = Path(
        "/home/mouse9911/gits/plutosdr-fw-radio20-tracking/hdl/library/starlink_glrt/native_cubic_60000000_upper.mem"
    )
    raw = np.asarray(coefficients(bank.read_bytes(), rate_hz=rate), dtype=np.float64)
    n = len(raw)
    ref = raw[:, 0] + 1j * raw[:, 1]
    derivative = raw[:, 2] + 1j * raw[:, 3]
    basis = np.column_stack(
        (ref, -derivative, 1j * np.pi * 1000 / rate * (2 * np.arange(n) - (n - 1)) * ref)
    )
    gram = basis.conj().T @ basis
    episodes = []
    mutation_checks = 0
    for ep in epochs["episodes"]:
        if not ep["results"]:
            continue
        name = "native.journal" if ep["episode"] == 0 else f"native-{ep['episode']}.journal"
        checked = review(journals[name], epoch=ep["epoch"], rate=rate)
        fitted = [
            check_estimate(h, e, basis, gram, rate)
            for h, e in zip(checked["heads"], checked["estimates"], strict=True)
        ]
        if not mutation_checks:
            for field, delta in (("cfo_hz", 1), ("coherence", 0.01)):
                corrupt = dict(checked["estimates"][0])
                corrupt[field] += delta
                try:
                    check_estimate(checked["heads"][0], corrupt, basis, gram, rate)
                except AssertionError:
                    mutation_checks += 1
                else:
                    raise AssertionError("corrupted native estimate was accepted")
        proposals = [x for x in rows if x["kind"] == 4 and x["epoch"] == ep["epoch"]]
        last_supported = max(
            [proposals[-1]["last_supported"]] + [e["frame"] for e in fitted if e["rejection"] == 0]
        )
        terminal = next(
            x
            for x in rows
            if x["kind"] == "native_terminal" and x["native_episode"] == ep["episode"]
        )
        if terminal["result"] == -4:
            assert fitted[-1]["frame"] == last_supported + 32
        episodes.append(
            dict(
                episode=ep["episode"],
                epoch=ep["epoch"],
                results=len(fitted),
                supported=checked["supported"],
                controller_result=terminal["result"],
                first_frame=fitted[0]["frame"],
                final_frame=fitted[-1]["frame"],
                last_supported_frame=last_supported,
                horizon_exhausted=terminal["result"] == -4,
                estimates=fitted,
                journal_sha256=hashlib.sha256(journals[name]).hexdigest(),
            )
        )
    assert sum(ep["results"] for ep in episodes) == status["native_results"]
    result = dict(
        status="pass",
        scope="all_native_epoch_retained_moment_estimates_and_drain",
        rate=rate,
        native_moments_independently_recomputed=False,
        live_tracking_qualified=False,
        native_results=status["native_results"],
        supported=sum(ep["supported"] for ep in episodes),
        corruption_checks=mutation_checks,
        episodes=episodes,
        reference_sha256=hashlib.sha256(bank.read_bytes()).hexdigest(),
        reviewer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    with (root / "native-epoch-estimate-review.json").open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print(
        json.dumps(
            {
                **result,
                "episodes": [{k: v for k, v in ep.items() if k != "estimates"} for ep in episodes],
            }
        )
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
