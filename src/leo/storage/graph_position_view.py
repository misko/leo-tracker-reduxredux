"""Explicit ALGO02/ALGO03 presentation selection through their public ports."""

from leo.contracts.fast_graph_position import MODEL_VERSION as BASELINE_MODEL
from leo.contracts.fast_graph_position_v2 import MODEL_VERSION
from leo.storage.fast_graph_position import FastGraphPositionStore
from leo.storage.fast_graph_position_v2 import FastGraphPositionStoreV2
from leo.storage.fast_scan import safe_id


def summary(terminal):
    selected = terminal.get("selected")
    arms = (
        selected["arms"]
        if selected
        else terminal.get("arms", terminal.get("baseline", {}).get("arms", {}))
    )
    return dict(
        model_version=terminal["model_version"],
        state=terminal["state"],
        position=terminal.get("position"),
        arms={arm: dict(endpoint_latlon=value["endpoint_latlon"]) for arm, value in arms.items()},
    )


class GraphPositionView:
    def __init__(self, root, model_version, *, baseline=None, candidate=None):
        if model_version not in {MODEL_VERSION, BASELINE_MODEL}:
            raise ValueError("Unknown explicitly selected graph-position model")
        self.model_version = model_version
        self.baseline = baseline if baseline is not None else FastGraphPositionStore(root)
        self.candidate = (
            candidate
            if candidate is not None
            else FastGraphPositionStoreV2(root, baseline=self.baseline)
        )

    def detail(self, run_id):
        safe_id(run_id)
        source = next((j for j in self.baseline.inputs() if j["run_id"] == run_id), None)
        view = dict(
            run_id=run_id,
            selected_model=self.model_version,
            state="unavailable",
            baseline=None,
            selected=None,
            position=None,
            fallback=False,
            reason="Awaiting qualified ALGO02 baseline",
        )
        if source is None:
            return view
        try:
            baseline, _ = self.baseline.terminal(source)
        except (OSError, ValueError, KeyError):
            return view
        if baseline["state"] != "complete":
            return view
        view.update(
            state="complete",
            baseline=summary(baseline),
            selected=summary(baseline),
            position=baseline["position"],
            decision="ALGO02",
            reason=None,
        )
        if self.model_version == BASELINE_MODEL:
            return view
        view.update(
            fallback=True, decision="ALGO02_fallback", reason="Awaiting qualified ALGO03 result"
        )
        try:
            job = self.candidate.job(source)
            status = self.candidate.status(job["job_id"])
            if status is None:
                return view
            if status["state"] != "complete":
                view.update(
                    recovery_state=status["state"],
                    reason=status.get("failure") or "ALGO03 recovery pending",
                )
                return view
            terminal, _ = self.candidate.terminal(job)
            if terminal["state"] != "complete":
                return view
            view.update(
                selected=summary(terminal),
                position=terminal["position"],
                fallback=terminal["decision"] == "ALGO02_fallback",
                decision=terminal["decision"],
                reason=terminal.get("failure"),
                baseline_seconds=terminal["baseline_seconds"],
                recovery_seconds=terminal["recovery_seconds"],
            )
        except (OSError, ValueError, KeyError) as error:
            view["reason"] = f"ALGO03 result unavailable: {type(error).__name__}"
        return view
