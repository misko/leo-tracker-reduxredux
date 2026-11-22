"""Apply the released signed prior to the accepted collapsed likelihood."""

from contextlib import contextmanager
from functools import wraps
from time import process_time
from unittest.mock import patch

from tools.pipeline_eval.variants import algo08_collapsed, algo08_collapsed_salvage


def apply_signed(prepared, accepted):
    from leo.analysis.localization_v3.signed_context import signed_context

    raw = prepared["phase_history"]
    history_sha = algo08_collapsed.digest(raw)
    forecast = prepared["phase_forecast"]
    if forecast.get("history_sha256", history_sha) != history_sha:
        raise ValueError("causal phase history has changed")
    forecast = dict(forecast, history_sha256=history_sha)
    family = dict(
        status="accepted", mask=accepted["keep"], weights=accepted["powers"],
        hyperparameters_from_pre_RF_TLE_only=accepted["model"],
        linear_entries=accepted["entries"], linear_paired_valid=bool(accepted["entries"]),
        policy_arms=accepted["arms"],
    )
    result = signed_context(
        accepted["scan"], {"final_node": accepted["node"]}, family, raw, forecast,
        prepared["tracks"]["observations"], case="SCAN", history_sha256=history_sha,
        cutoff_utc_ns=prepared["sky"]["metadata"]["cutoff_utc_ns"],
    )
    if result["signed"]["accepted"]:
        accepted = dict(accepted, arms=result["arms"], means=result["means"])
    return accepted, result["signed"]


@contextmanager
def signed_finish():
    """Install one signed-context update before guard and evidence callbacks."""
    original_infer = algo08_collapsed.infer
    original_recover = algo08_collapsed_salvage.recover

    @wraps(original_infer)
    def infer(prepared, *args, **kwargs):
        @wraps(original_recover)
        def recover(*recover_args, **recover_kwargs):
            accepted, detail = original_recover(*recover_args, **recover_kwargs)
            began = process_time()
            updated, signed = apply_signed(prepared, accepted)
            timing = dict(cpu_s=process_time() - began, accepted=signed["accepted"],
                          qualified=signed["selection"]["qualified"])
            return updated, dict(detail, signed_finish=timing)

        with patch.object(algo08_collapsed_salvage, "recover", recover):
            return original_infer(prepared, *args, **kwargs)

    with patch.object(algo08_collapsed, "infer", infer):
        yield
