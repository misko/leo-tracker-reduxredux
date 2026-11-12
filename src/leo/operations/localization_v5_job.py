"""ALGO07v5 composition over the owned full-budget native job."""

from copy import deepcopy
from pathlib import Path

from leo.analysis.localization_v5.initial_control import POLICY, initial_control
from leo.contracts import localization_v5
from leo.contracts.digests import canonical_digest
from leo.operations import localization_v3_job


def make_request(v3_request, backend_manifest):
    from leo.analysis.localization_v4.backend import read_manifest, validate_manifest

    localization_v3_job.validate_request(v3_request)
    manifest = validate_manifest(read_manifest(backend_manifest))
    job = deepcopy(v3_request)
    job["identity"]["run_id"] = "v5-" + canonical_digest(
        dict(request=v3_request, backend_manifest=manifest, initial_control_policy=POLICY)
    )[7:47]
    return validate_request(dict(
        schema_version=1,
        algorithm=localization_v5.MODEL,
        backend_manifest=deepcopy(manifest),
        initial_control_policy=POLICY,
        job=job,
    ))


def validate_request(request):
    from leo.analysis.localization_v4.backend import validate_manifest

    if (
        not isinstance(request, dict)
        or set(request) != {
            "schema_version", "algorithm", "backend_manifest", "initial_control_policy", "job"
        }
        or request["schema_version"] != 1
        or request["algorithm"] != localization_v5.MODEL
        or request["initial_control_policy"] != POLICY
    ):
        raise ValueError("Complete native ALGO07v5 request required")
    localization_v3_job.validate_request(request["job"])
    if not request["job"]["identity"]["run_id"].startswith("v5-"):
        raise ValueError("Native ALGO07v5 run namespace required")
    validate_manifest(request["backend_manifest"], check_artifacts=False)
    return request


def execute(request, *, native_manifest, receipts, resume_only=False, emit=lambda value: None):
    from leo.analysis.localization_v4.backend import ProcessBound, read_manifest
    from leo.storage.localization_v5 import LocalizationV5Store

    validate_request(request)
    manifest = request["backend_manifest"]
    if read_manifest(native_manifest) != manifest:
        raise ValueError("Native manifest differs from request backend binding")
    # Saved publication can complete without loading the native solver or reading inputs.
    store = LocalizationV5Store(request["job"]["output_root"])
    run_id = request["job"]["identity"]["run_id"]
    try:
        store.receipt(run_id)
    except FileNotFoundError:
        if resume_only:
            raise ValueError("No committed native scientific result to resume") from None
        backend = ProcessBound(manifest, Path(receipts))
    else:
        backend = None

    def check_saved(evidence):
        provenance = evidence["provenance"]
        if (
            provenance["algorithm"] != localization_v5.MODEL
            or provenance["native_backend"]["manifest"] != manifest
            or provenance["initial_control_policy"] != POLICY
        ):
            raise ValueError("Saved result belongs to a different native backend")

    return localization_v3_job._execute(
        request["job"], resume_only=resume_only, emit=emit,
        contract=localization_v5, results_factory=LocalizationV5Store,
        request_binding=request, bound=backend,
        check_saved=check_saved, initial_control=initial_control,
        extra_provenance=lambda: dict(
            algorithm=localization_v5.MODEL, native_backend=backend.provenance(),
            initial_control_policy=POLICY
        ),
    )
