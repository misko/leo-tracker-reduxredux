"""Explicit graph-position presentation selection through versioned public ports."""

from leo.contracts.fast_graph_position import MODEL_VERSION as BASELINE_MODEL
from leo.contracts.fast_graph_position_v2 import MODEL_VERSION
from leo.contracts.fast_graph_position_v3 import MODEL_VERSION as NUMERICAL_MODEL
from leo.storage.fast_graph_position import FastGraphPositionStore
from leo.storage.fast_graph_position_v2 import FastGraphPositionStoreV2
from leo.storage.fast_scan import safe_id


def summary(terminal):
    proof = terminal["candidate"] if terminal.get("decision") == "ALGO04_additive" else terminal
    selected = proof.get("selected")
    arms = (
        selected["arms"]
        if selected
        else proof.get("arms", proof.get("baseline", {}).get("arms", {}))
    )
    return dict(
        model_version=terminal["model_version"],
        state=terminal["state"],
        position=terminal.get("position"),
        arms={arm: dict(endpoint_latlon=value["endpoint_latlon"]) for arm, value in arms.items()},
    )


class GraphPositionView:
    def __init__(self, root, model_version, *, baseline=None, candidate=None, numerical=None):
        if model_version not in {MODEL_VERSION, BASELINE_MODEL, NUMERICAL_MODEL}:
            raise ValueError("Unknown explicitly selected graph-position model")
        self.model_version = model_version
        self.baseline = baseline if baseline is not None else FastGraphPositionStore(root)
        self.candidate = (
            candidate
            if candidate is not None
            else FastGraphPositionStoreV2(root, baseline=self.baseline)
        )
        self.numerical = numerical
        if model_version == NUMERICAL_MODEL and numerical is None:
            from leo.storage.fast_graph_position_v3 import FastGraphPositionStoreV3

            self.numerical = FastGraphPositionStoreV3(root, incumbent=self.candidate)

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
        view, job, terminal = self._candidate_detail(view, source)
        if self.model_version == NUMERICAL_MODEL:
            return self._numerical_detail(view, job, terminal)
        return view

    def _candidate_detail(self, view, source):
        """Retain the published ALGO03 presentation and obtain its public job."""
        job = None
        view.update(
            fallback=True, decision="ALGO02_fallback", reason="Awaiting qualified ALGO03 result"
        )
        try:
            job = self.candidate.job(source)
            status = self.candidate.status(job["job_id"])
            if status is None:
                return view, job, None
            if status["state"] != "complete":
                view.update(
                    recovery_state=status["state"],
                    reason=status.get("failure") or "ALGO03 recovery pending",
                )
                return view, job, None
            terminal, _ = self.candidate.terminal(job)
            if terminal["state"] != "complete":
                return view, job, None
            view.update(
                selected=summary(terminal),
                position=terminal["position"],
                fallback=terminal["decision"] == "ALGO02_fallback",
                decision=terminal["decision"],
                reason=terminal.get("failure"),
                baseline_seconds=terminal["baseline_seconds"],
                recovery_seconds=terminal["recovery_seconds"],
            )
            return view, job, terminal
        except (OSError, ValueError, KeyError) as error:
            view["reason"] = f"ALGO03 result unavailable: {type(error).__name__}"
        return view, job, None

    @staticmethod
    def _incumbent_fallback(view, incumbent):
        # The v2 proof can itself retain ALGO02. Label the actual endpoint,
        # while selected_model continues to identify the requested model.
        underlying_baseline = incumbent["decision"] == "ALGO02_fallback"
        view.update(
            selected=summary(incumbent["baseline"] if underlying_baseline else incumbent),
            position=incumbent["position"],
            fallback=True,
            decision="ALGO02_fallback" if underlying_baseline else "ALGO03_fallback",
        )

    def _numerical_detail(self, view, source_job, incumbent):
        waiting = "Awaiting qualified ALGO04 result"
        view["fallback"] = True
        if incumbent is None:
            view["reason"] = f"{waiting}; {view['reason']}"
            return view
        view["incumbent"] = summary(incumbent)
        self._incumbent_fallback(view, incumbent)
        view["reason"] = waiting
        try:
            job = self.numerical.job(source_job)
            status = self.numerical.status(job["job_id"])
            if status is None:
                return view
            if status["state"] != "complete":
                view.update(
                    recovery_state=status["state"],
                    reason=status.get("failure") or "ALGO04 numerical recovery pending",
                )
                return view
            terminal, _ = self.numerical.terminal(job)
            if terminal["state"] != "complete":
                return view
            if terminal["decision"] == "ALGO03_fallback":
                self._incumbent_fallback(view, terminal["incumbent"])
            else:
                view.update(
                    selected=summary(terminal),
                    position=terminal["position"],
                    fallback=False,
                    decision=terminal["decision"],
                )
            view.update(
                reason=terminal.get("failure"),
                incumbent_seconds=terminal["incumbent_seconds"],
                numerical_seconds=terminal["numerical_seconds"],
                total_seconds=terminal["total_seconds"],
            )
        except (OSError, ValueError, KeyError) as error:
            view["reason"] = f"ALGO04 result unavailable: {type(error).__name__}"
        return view
