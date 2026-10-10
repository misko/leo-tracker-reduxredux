"""Inference-only public reconstruction with exact prior107 physical signatures."""

import hashlib
import json
from pathlib import Path


def inference_document(document):
    """Whitelist inference fields; no reference/error value is indexed or hashed."""
    configuration = document["configuration"]
    return dict(
        session_id=document["session_id"],
        input_manifest_sha256=document["input_manifest_sha256"],
        analysis_manifest_sha256=document["analysis_manifest_sha256"],
        evidence_sha256=document["evidence_sha256"],
        configuration={key: configuration[key] for key in ("prior", "scores", "run")},
    )


def validate_direct_metadata(document):
    """Regression precondition missed by129; historical derivation is explicit."""
    diagnostics = document.get("diagnostics") or {}
    bank = diagnostics.get("bank")
    if not diagnostics.get("snapshot_sha256"):
        raise ValueError("direct105 loader requires nonmissing snapshot authority")
    if not isinstance(bank, dict) or not bank.get("retained_numbers"):
        raise ValueError("direct105 loader requires nonmissing bank authority")


def observation_signature(observations, core):
    return core.canonical_digest(
        dict(
            window_ids=list(observations.window_ids),
            **{
                name: core.json_value(getattr(observations, name))
                for name in ("times_s", "measured_hz", "rf_hz", "receiver", "channel", "margin")
            },
        )
    )


class InferenceLoader:
    """Expose105 backend hooks; never invoke105/51 historical document loaders."""

    def __init__(self, repository, backend_load_case):
        self.repository = Path(repository)
        self.load_case = backend_load_case
        self.core = backend_load_case.__globals__["core"]

    def __call__(self, binding):
        core = self.core
        path = self.repository / binding["document_path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != binding["document_sha256"]:
            raise ValueError("sanitized inference document changed")
        document = inference_document(json.loads(path.read_text()))
        expected = binding["expected_input_binding"]
        model = binding["model_identity"]
        if (
            document["session_id"] != binding["session_id"]
            or model.get("session_id", binding["session_id"]) != binding["session_id"]
        ):
            raise ValueError("inference session changed")
        for field in ("input_manifest_sha256", "analysis_manifest_sha256", "evidence_sha256"):
            if document[field] != model[field]:
                raise ValueError("inference model identity mismatch: " + field)
        if (
            core.canonical_digest(document["configuration"]["prior"]) != model["prior_signature"]
            or core.canonical_digest(document["configuration"]["scores"])
            != model["score_signature"]
        ):
            raise ValueError("inference prior/score metadata changed")
        store = core.ScannerTrackingInputStore(Path("/srv/bulk/leo"))
        try:
            source = store.load(document["session_id"])
        finally:
            store.close()
        for field in ("input_manifest_sha256", "analysis_manifest_sha256"):
            if getattr(source, field) != document[field]:
                raise ValueError("public recording identity changed: " + field)
        prepared = core.prepare_position_windows(source)
        # Reject row/content/order substitution before any orbit-bank construction.
        observed = observation_signature(prepared.observations, core)
        if observed != expected["observation_order_signature"]:
            raise ValueError("historical observations/order changed")
        archive = core.TleArchiveReader(Path("/var/lib/leo/tle"))
        snapshot = archive.select_latest_before(prepared.start_utc_ns - 505_000_000_000)
        if snapshot.digest != model["snapshot_sha256"]:
            raise ValueError("causal snapshot authority changed")
        payload, _ = core.exclude_labelled_starlink_debris(archive.read(snapshot))
        catalogue = core.parse_element_sets(payload)
        indices = core.np.array(
            [i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")]
        )
        evidence = core.canonical_digest(
            dict(
                windows=prepared.evidence_sha256,
                tle=snapshot.digest,
                candidates=[int(catalogue.satellite_numbers[i]) for i in indices],
            )
        )
        if evidence != document["evidence_sha256"] or evidence != expected["evidence_digest"]:
            raise ValueError("compound inference evidence changed")
        prior = core.RegionalPrior(**document["configuration"]["prior"])
        if core.canonical_digest(core.json_value(core.HARD60_SCORE)) != core.canonical_digest(
            document["configuration"]["scores"]["V16"]
        ):
            raise ValueError("runtime score differs")
        bank, _ = core.build_regional_bank(
            catalogue,
            indices,
            prepared.start_utc_ns,
            prepared.observations,
            prior,
            maximum_seconds=180,
        )
        actual = dict(
            input_digest=document["input_manifest_sha256"],
            evidence_digest=evidence,
            observation_order_signature=observed,
            score_signature=core.canonical_digest(
                dict(prior=core.json_value(prior), score=core.json_value(core.HARD60_SCORE))
            ),
            bank_signature=core.canonical_digest(bank.numbers.tolist()),
        )
        if actual != expected or actual["bank_signature"] != model["bank_signature"]:
            raise ValueError("saved107 physical signatures differ")
        return dict(
            observations=prepared.observations,
            bank=bank,
            prior=prior,
            tracks=prepared.bootstrap_tracks,
            prepared=prepared,
            document=document,
            identity={
                field: document[field]
                for field in (
                    "input_manifest_sha256",
                    "analysis_manifest_sha256",
                    "evidence_sha256",
                )
            },
        )
