"""One bounded all-five original-endpoint information audit; never fits."""
# ruff: noqa: E402

import argparse
import importlib.util
import time
from pathlib import Path

import kernel
import numpy as np
from numpy.testing import assert_allclose

HERE = Path(__file__).resolve().parent
PUBLIC = HERE.parents[1] / "2026_10_17_dsx01_iteration6/full_joint_band"
SPEC = importlib.util.spec_from_file_location("original_no_reference_port", PUBLIC / "run_v2.py")
port = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(port)
from leo.analysis.hard60_score import predict_orbits


def clock_metadata(raw):
    clock = raw.base
    precision = np.asarray(clock.precision)
    second = np.diff(np.eye(len(clock.nodes)), n=2, axis=0) @ clock.null
    default = np.kron(
        np.eye(2), np.eye(clock.null.shape[1]) / 50.0**2 + second.T @ second / 25.0**2
    )
    factor = float(np.sum(default * precision) / np.sum(default * default))
    if factor <= 0:
        raise ValueError("Positive actual clock precision required")
    assert_allclose(precision, factor * default, atol=1e-14, rtol=1e-12)
    scale = float(1 / np.sqrt(factor))
    return dict(
        exact_precision=precision,
        node_times_s=clock.nodes,
        clock_basis_null=clock.null,
        node_second_difference_in_null=second,
        inferred_prior_scale=scale,
        amplitude_sigma_hz=50 * scale,
        second_difference_sigma_hz=25 * scale,
        precision_eigenvalues=np.linalg.eigvalsh(precision),
        semantics=(
            "Per-RX common-across-band clocks; null removes constant/linear modes; "
            "exact archived precision once"
        ),
    )


def freeze():
    port.verify()
    paths = [
        HERE / n for n in ("run.py", "kernel.py", "test_kernel.py", "test_run.py", "PROTOCOL.md")
    ]
    paths += [PUBLIC / "run_v2.py", PUBLIC / "protocol_v2.json"]
    binding = {str(path): port.digest(path) for path in paths}
    binding.update(port.read(PUBLIC / "protocol_v2.json")["source_sha256"])
    port.save(
        HERE / "plan.json",
        dict(
            source_sha256=binding,
            source_endpoint="ORIGINAL full endpoint from public replay; no position selection",
            sources=port.SOURCES,
            arms=["fitted-c", "deterministic-c0-zero-only"],
            objectives=10,
            explicit_orbit_predictor_calls=10,
            fits=0,
            maximum_seconds=180,
            outer_term_seconds=180,
            outer_kill_seconds=185,
            rank_rtol=1e-12,
            rank_sensitivity=[1e-10, 1e-14],
            no_window_selection=True,
            no_station_reference_read=True,
        ),
    )


def verify():
    port.verify_bindings(port.read(HERE / "plan.json")["source_sha256"])


def audit():
    begun = time.monotonic()
    verify()
    rows = []
    preparations = []
    for source in port.SOURCES:
        if time.monotonic() - begun >= 170:
            raise TimeoutError("Whole audit admission bound before next source")
        started = time.monotonic()
        ctx, original = port.prepare(source, "fitted-c")
        preparations.append(dict(source_id=source, elapsed_seconds=time.monotonic() - started))
        model = ctx.model
        raw = model.original
        obs = model.scored_observations
        if not model.mask.all() or raw.group_count != 0:
            raise ValueError("Original full model with frozen group contrasts required")
        assert_allclose(model.score.relative_sigma_s, 2.0, atol=0, rtol=0)
        assert_allclose(model.score.common_sigma_s, 3.0, atol=0, rtol=0)
        c = np.column_stack((raw.design[model.mask], raw.clock_design[model.mask]))
        if c.shape != (len(obs.times_s), 5 + model.clock_count):
            raise ValueError("Actual calibration5+clock dimensions mismatch")
        clock = clock_metadata(raw)
        precision = np.zeros((c.shape[1], c.shape[1]))
        precision[5:, 5:] = clock["exact_precision"]
        for arm in ("fitted-c", "deterministic-c0-zero-only"):
            if time.monotonic() - begun >= 178:
                raise TimeoutError("Whole audit bound before next endpoint")
            v, n = np.asarray(original[0]).copy(), np.asarray(original[1]).copy()
            if arm != "fitted-c":
                v[6] = 0.0
            ev, details = model.evaluate_details(v, n)
            terms = ev[3]
            sigma = np.asarray(details["sigma_hz"])
            if sigma.shape != (len(obs.times_s),):
                raise ValueError("Actual per-row sigma dimensions mismatch")
            weight = terms.responsibilities / sigma[:, None] ** 2
            delta = model.basis @ v[8:]
            tau = v[7] + delta
            _, _, spatial, timing = predict_orbits(ctx.bank, obs, ctx.prior, v[:2], tau)
            blocks = kernel.gram_blocks(spatial, timing, c, weight)
            information = kernel.compare(blocks, precision)
            restricted = None
            if arm != "fitted-c":
                restricted = kernel.compare(
                    blocks,
                    precision,
                    calibration_columns=np.r_[np.arange(4), np.arange(5, c.shape[1])],
                )
            clock_vector, group = raw.split(n[: model.base_nuisance_count])
            tail = n[model.base_nuisance_count :]
            qpenalty = 0.5 * float(tail @ (model.observation_precision * tail))
            clock_penalty = 0.5 * float(clock_vector @ clock["exact_precision"] @ clock_vector)
            timing_penalty = 0.5 * float(tau @ kernel.total_timing_precision(len(tau)) @ tau)
            expected = (
                clock_penalty + timing_penalty + qpenalty + model.fixed_contrast_prior_penalty
            )
            assert_allclose(expected, details["prior_penalty"], atol=1e-8, rtol=0)
            assert_allclose(
                terms.responsibilities.sum(axis=1) + terms.clutter_probability,
                1.0,
                atol=1e-12,
                rtol=0,
            )
            best = terms.responsibilities.max(axis=1)
            assigned = best > terms.clutter_probability
            if (
                arm == "fitted-c"
                and int(assigned.sum()) != port.source_rows()[source]["original_associated_count"]
            ):
                raise ValueError("Original fitted classification replay changed")
            result = dict(
                source_id=source,
                arm=arm,
                endpoint="original",
                numbers=ctx.bank.numbers,
                observations=len(obs.times_s),
                candidates=len(tau),
                clock_columns=model.clock_count,
                calibration_columns=c.shape[1],
                independent_total_timing_columns=len(tau),
                original_vector_sha256=__import__("hashlib")
                .sha256(np.asarray(original[0]).tobytes())
                .hexdigest(),
                geometry_changed=False,
                nuisance_changed=False,
                only_c_zeroed=arm != "fitted-c",
                calibration_labels=["a0_Hz", "b0_Hz_per_s", "a1_Hz", "b1_Hz_per_s", "c_Hz_per_GHz"]
                + [f"clock_{i}_Hz" for i in range(model.clock_count)],
                sigma_hz=sigma[0],
                responsibility_signal_mass=float(terms.responsibilities.sum()),
                clutter_mass=float(terms.clutter_probability.sum()),
                associated=int(assigned.sum()),
                q=details["detection_probability"],
                satellite_signal_mass=terms.responsibilities.sum(axis=0),
                soft_visibility_signal_mass_below_1e_6=float(
                    terms.responsibilities[details["visibility_weight"] < 1e-6].sum()
                ),
                soft_visibility_signal_mass_below_1pct=float(
                    terms.responsibilities[details["visibility_weight"] < 0.01].sum()
                ),
                hard_invisible_signal_mass=float(
                    terms.responsibilities[~details["hard_visible"]].sum()
                ),
                clock_prior=clock,
                calibration_prior_precision=precision,
                once_only_prior_ledger=dict(
                    clock=clock_penalty,
                    timing=timing_penalty,
                    q=qpenalty,
                    fixed_band=model.fixed_contrast_prior_penalty,
                    total=expected,
                ),
                information=information,
                c0_fixed_coefficient_projection=restricted,
                likelihood_nll=float(terms.nll),
                objective=float(ev[0]),
                posterior_policy="Own current posterior per arm; c0 changes weights, no refit",
                surrogate="Positive mean only; posterior/q/visibility and residual curvature omitted",
                constraint_scope="Unconstrained column span; ridge only actual clock/timing priors",
                no_covariance_or_truth_claim=True,
            )
            port.save(HERE / f"{source}_{arm}.json", result)
            rows.append(result)
            print(
                source,
                arm,
                "trace fractions",
                information["after_calibration"]["trace_fraction_of_raw"],
                information["after_calibration_and_timing"]["trace_fraction_of_raw"],
                flush=True,
            )
    verify()
    port.save(
        HERE / "summary.json",
        dict(
            rows=rows,
            preparations=preparations,
            elapsed_seconds=time.monotonic() - begun,
            explicit_objectives=10,
            explicit_orbit_derivative_predictor_calls=10,
            public_preparation_additional=True,
            fits=0,
            station_reference_read=False,
            requested_windows_used=False,
            primary_projection="Same5cal+clock both arms; fixed-c4coeff additionally reported",
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "run"))
    action = parser.parse_args().action
    if action == "freeze":
        freeze()
    else:
        try:
            audit()
        except Exception as error:
            port.save(
                HERE / "failure.json",
                dict(
                    state="stopped",
                    type=type(error).__name__,
                    reason=str(error),
                    fits=0,
                    partial_receipts_retained=True,
                ),
            )
            raise
