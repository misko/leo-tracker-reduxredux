"""Account for the maximum compiled factorization saving on the saved signed pairs."""

from gzip import decompress
from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FLOOR_NS = 500_000_000
KERNEL_SHA = "40888d6143f385c2146e5e2cb28ea99a96b2f1bb791fab4c22b5afaaa2b3a23b"
PINS = {
    "v3/measurements/signed-state-ceiling.json": "ee3c8012a47357b4196c01ca40e827cf51f45d9686ae58c4c54f768a6b950696",
    "v3/measurements/named-phase-reuse-0008.json.gz": "198d22b558217a511974671e96a6e181a6eeb25f757c54c936218da5c3d9765d",
    "v3/measurements/cold-kernel-price.json.gz": "28bb74ba394c42442ca4a007b2957acc4fc6c0a378a6fb9a5ed88ece87b8315c",
    "v3/measurements/conditioned-factor.json": "3a3d976324544ff286d0d6287664abc5796a38ab8ad6baf5a44b7090f67955f7",
    "single-core-2x/measurements/solver-wide-private-blocks.json": "ca8c10e68b1a59c7f107e1280e5689f69ee728e58e4f124c6ab5a93347ea3ae6",
    "single-core-2x/measurements/solver-schur-reuse-audit.json": "1df3eb7d2667498a9937a9f2ac76b614ee0d3f05cc1c060be595bc4bff547bb5",
    "single-core-2x/measurements/solver-posterior-handoff.json.gz": "b06127d3af5823269c3dfa006a9a30dcc241e91ab55439287af601b2d0c8003e",
}
DENSE_SAMPLE = "dense-likelihood-capture-0008/sample-01.npz"


def read(path, pin):
    data = path.read_bytes()
    if path.suffix == ".gz":
        data = decompress(data)
    if sha256(data).hexdigest() != pin:
        raise ValueError(f"Unexpected archived bytes at {path}")
    return json.loads(data)


def price(row):
    if not row["exact_original_readouts"]:
        raise ValueError("Compiled budget needs original signed parity")
    stages = row["stages"]
    curved, predictive = stages["curved_posterior"], stages["predictive_covariance"]
    objective = stages["paid_full_objective"]
    summary = curved.get("same_refresh", {})
    if curved["calls"] - summary.get("calls", 0) != objective["calls"] or predictive["calls"] != objective["calls"]:
        raise ValueError("Timed likelihood and prediction calls cross the original scope")
    whole = sum(row["observed_pair_cpu_ns"].values())
    if not (0 < curved["cpu_ns"] + predictive["cpu_ns"] < whole):
        raise ValueError("Disjoint calls exceed their enclosing instrumented signed pair")
    return dict(
        factor_and_all_curved_adapter_roof_ns=curved["cpu_ns"], curved_adapter_calls=curved["calls"],
        factor_roof_after_existing_summary_idea_ns=curved["cpu_ns"] - summary.get("cpu_ns", 0),
        all_predictive_covariance_roof_ns=predictive["cpu_ns"], predictive_covariance_calls=predictive["calls"],
        required_net_cpu_ns_per_predictive_call=round(FLOOR_NS / predictive["calls"]),
        signed_pair_cpu_ns=whole, signed_pair_after_free_curved_adapter_ns=whole - curved["cpu_ns"],
        archived_original_signed_refit=row["archived_signed_refit"], owner_rows=row["exact_owner_role_count"],
        original_exact_arms={arm: {name: fit[name] for name in ("latlon", "rf_rms_hz", "objective")}
                             for arm, fit in row["exact_readout"].items()},
        meets_factor_floor=curved["cpu_ns"] >= FLOOR_NS)


def report():
    sources = {Path(name).name: read(HERE.parent / name, pin) for name, pin in PINS.items()}
    installed = ROOT / "src/leo/analysis/localization_v4/native_bound.c"
    if sha256(installed.read_bytes()).hexdigest() != KERNEL_SHA:
        raise ValueError("Current native source differs from the audited release")
    current = sources["signed-state-ceiling.json"]["results"]
    current = {case: price(row) for case, row in current.items()}
    dense = sources["solver-wide-private-blocks.json"]["active_kernel_diagnostics"][DENSE_SAMPLE]
    prior = sources["solver-schur-reuse-audit.json"]["witnesses"]["dense-likelihood-capture-0008"]
    hard = sources["cold-kernel-price.json.gz"]["observations"]["DS30-0402"]["audit"]
    arms = sources["named-phase-reuse-0008.json.gz"]["pair"]["arms"]
    # The old dense trial explicitly interposed only these three disjoint subcalls.
    # Everything else within the objective is an upper bound for the dense Gram rebuild.
    remainder = sum(arm["counts"]["full_evaluation_cpu_ns"] - sum(arm["counts"][key] for key in (
        "curved_cpu_ns", "prepared_geometry_cpu_ns", "predictive_covariance_cpu_ns")) for arm in arms.values())
    cert = sources["conditioned-factor.json"]["dense"]
    grid_port = sources["solver-posterior-handoff.json.gz"]["DS30-0155"]
    stock_grid = grid_port["results"]["stock"]["timings"]
    gram_cpu_per_call = stock_grid["gram_or_check_cpu_ns"] / stock_grid["dense_calls"]
    return dict(
        current=current, floor_ns=FLOOR_NS, actual_released_c_sha256=KERNEL_SHA, archive_sha256=PINS,
        earlier_dense_native_state=dict(model_scope="original position, before the current signed pair",
            raw_input_sha256=prior["input_sha256"], rows=dense["rows"], columns=dense["columns"],
            groups=prior["observation_groups"], shared_columns=prior["shared_columns"],
            updates=dense["updates"], factorizations=prior["factorizations"], full_profile_cpu_ns=dense["profiled_cpu_ns"],
            phase_cpu_ns=dense["phase_cpu_ns"], exact_factor_delta_rank=prior["per_transition_ranges"]["binary64_matrix_update_rank_lower_bound"]),
        earlier_hard_native_state=dict(model_scope="exact cold finalists, before the current signed pair",
            calls=len(hard["native_calls"]), updates=sum(row["iterations"] for row in hard["native_calls"]),
            stock_cpu_ns=hard["kernel_stock_cpu_ns"], phase_cpu_ns=hard["phase_cpu_ns"]),
        earlier_condition_certificate=dict(cpu_s=cert["saving"]["ordinary_cpu_s"],
                                           counts=cert["native"]["ordinary"]),
        separate_signed_predictive_gram=dict(
            unattributed_dense_objective_ceiling_ns=remainder,
            distinct_grid_case="DS30-0155", grid_gram_cpu_ns=stock_grid["gram_or_check_cpu_ns"],
            grid_dense_calls=stock_grid["dense_calls"],
            projection_to_signed_calls_ns={case: round(gram_cpu_per_call * row["predictive_covariance_calls"])
                                          for case, row in current.items()}),
        new_kernels=0, new_solver_runs=0, waveform_reads=0)


if __name__ == "__main__":
    print(json.dumps(report(), sort_keys=True, indent=2, allow_nan=False))
