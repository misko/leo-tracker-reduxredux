"""Owned single-job composition; no earlier worker or scientific-result dependency."""

import hashlib
import importlib.metadata
import json
import math
import platform
import signal
import sys
import time
from contextlib import contextmanager
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path

from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.localization_v3 import require_digest, validate_identity

POLICY = "validation-all-work"
PACKAGES = ("numpy", "scipy", "sgp4", "matplotlib", "pillow")


class JobInterrupted(BaseException):
    """Must not become a scientific rejection through an `except Exception` gate."""


class StageDeadline(JobInterrupted):
    pass


def runtime_versions():
    return dict(
        python=platform.python_version(),
        **{name: importlib.metadata.version(name) for name in PACKAGES},
    )


def validate_request(request):
    required = {
        "schema_version",
        "execution_policy",
        "identity",
        "native_input",
        "track_config",
        "tle_root",
        "output_root",
        "search_center",
        "screen_center",
        "scan_identities",
        "title",
        "evaluation_reference",
        "runtime",
    }
    if not isinstance(request, dict) or set(request) != required or request["schema_version"] != 1:
        raise ValueError("Complete version-one native job request required")
    if request["execution_policy"] != POLICY:
        raise ValueError("Only explicit validation-all-work is currently qualified")
    validate_identity(request["identity"])
    for name in ("native_input", "track_config"):
        row = request[name]
        if (
            not isinstance(row, dict)
            or set(row) != {"path", "sha256"}
            or not isinstance(row["path"], str)
            or not Path(row["path"]).is_absolute()
        ):
            raise ValueError("Absolute, content-bound input required")
        require_digest(row["sha256"])
    if request["native_input"]["sha256"] != request["identity"]["input_sha256"]:
        raise ValueError("Native input identity binding differs")
    for name in ("tle_root", "output_root"):
        if not isinstance(request[name], str) or not Path(request[name]).is_absolute():
            raise ValueError("Explicit absolute archive/output roots required")
    if Path(request["output_root"]).resolve().is_relative_to("/mnt/qnap01"):
        raise ValueError("QNAP is read-only")
    if request["search_center"] != [37.906, -122.545]:
        raise ValueError("Current published figure contract requires the production regional frame")
    screen = request["screen_center"]
    if (
        not isinstance(screen, list)
        or len(screen) != 2
        or any(type(v) not in (float, int) or not math.isfinite(v) for v in screen)
        or not -90 < screen[0] < 90
        or not -180 <= screen[1] <= 180
    ):
        raise ValueError("Valid screening coordinates required")
    ids = request["scan_identities"]
    if (
        not isinstance(ids, list)
        or not ids
        or any(not isinstance(v, str) or not v for v in ids)
        or len(ids) != len(set(ids))
        or request["identity"]["session_id"] not in ids
    ):
        raise ValueError("Explicit unique native scan identities required")
    if not isinstance(request["title"], str) or not request["title"]:
        raise ValueError("Recording title required")
    reference = request["evaluation_reference"]
    if reference is not None:
        if not isinstance(reference, dict) or set(reference) != {"latitude_deg", "longitude_deg"}:
            raise ValueError("Explicit presentation-only reference required")
        lat, lon = reference["latitude_deg"], reference["longitude_deg"]
        if (
            any(type(v) not in (int, float) or not math.isfinite(v) for v in (lat, lon))
            or not -90 <= lat <= 90
            or not -180 <= lon <= 180
        ):
            raise ValueError("Invalid presentation reference")
    if (
        not isinstance(request["runtime"], dict)
        or set(request["runtime"]) != {"python", *PACKAGES}
        or any(not isinstance(v, str) or not v for v in request["runtime"].values())
    ):
        raise ValueError("Explicit numerical and rendering runtime pins required")
    return request


@contextmanager
def stage_deadline(seconds):
    """A Python interrupt plus the outer process supervisor's hard wall limit."""
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Positive finite stage deadline required")
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise RuntimeError("An existing process timer cannot be replaced")
    previous = signal.getsignal(signal.SIGALRM)

    def expired(*_):
        raise StageDeadline("Native job stage deadline exceeded")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def read_bound(record):
    raw = Path(record["path"]).read_bytes()
    if sha256_digest(raw) != record["sha256"]:
        raise ValueError("Native job input changed: " + record["path"])
    return json.loads(raw)


def source_bindings():
    return {
        name: dict(
            path=module.__file__,
            sha256=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(),
        )
        for name, module in sys.modules.items()
        if getattr(module, "__file__", None)
        and "/leo/" in str(module.__file__)
        and str(module.__file__).endswith((".py", *EXTENSION_SUFFIXES))
    }


def execute(request, *, resume_only=False, emit=lambda value: None):
    """Complete one native job, or resume its exact saved publication.

    The all-work policy matches the prior v3 qualification runs. It does not
    claim equivalence to the older wall-clock discovery-admission policy.
    """
    validate_request(request)
    if runtime_versions() != request["runtime"]:
        raise ValueError("Numerical/rendering runtime differs from the request pins")
    from leo.application.localization_v3_result import build_evidence, publish_saved
    from leo.storage.fast_standard_analysis import RENDER_REVISION, FastStandardAnalysisStore
    from leo.storage.localization_v3 import LocalizationV3Store

    started = time.monotonic()
    identity = request["identity"]
    request_sha = canonical_digest(request)
    results = LocalizationV3Store(request["output_root"])
    publication = FastStandardAnalysisStore(request["output_root"])
    try:
        results.receipt(identity["run_id"])
    except FileNotFoundError:
        if resume_only:
            raise ValueError("No committed native scientific result to resume") from None
    else:
        saved = results.load(identity["run_id"])
        if (
            saved["evidence"]["identity"] != identity
            or saved["evidence"]["provenance"].get("request_sha256") != request_sha
        ):
            raise ValueError("Saved result belongs to a different native request")
        manifest = publish_saved(identity["run_id"], results, publication)
        return dict(
            status="complete",
            resumed=True,
            request_sha256=request_sha,
            seconds=time.monotonic() - started,
            publication=manifest,
        )

    from dataclasses import asdict

    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.application.localization_v3_engine import ExecutionPorts, run_native
    from leo.operations.localization_v3_parallel import (
        map_all_target_training,
        map_annotation_training,
        map_grid_batches,
        map_initial_arms,
        map_initial_branches,
        map_predictive_folds,
    )
    from leo.operations.tle_archive import TleArchiveReader

    native = read_bound(request["native_input"])
    if native["source"]["session_id"] != identity["session_id"]:
        raise ValueError("Native source belongs to another session")
    config = TrackConfig(**read_bound(request["track_config"])["config"])

    def stage(name, operation):
        try:
            value = operation()
        except Exception as error:
            emit(
                dict(
                    event="recovery_stage",
                    stage=name,
                    status="failed",
                    error=f"{type(error).__name__}: {error}",
                )
            )
            return False, None
        emit(dict(event="recovery_stage", stage=name, status="complete"))
        return True, value

    def gap(name, operation, cap):
        with stage_deadline(cap):
            value = operation()
        return True, value

    ports = ExecutionPorts(
        stage, gap, lambda: True, lambda _: None, time.monotonic,
        map_initial_arms=map_initial_arms,
        map_initial_branches=map_initial_branches,
        map_predictive_folds=map_predictive_folds,
        map_family_arms=map_initial_arms,
        map_recovery_arms=map_initial_arms,
        map_conservative_arms=map_initial_arms,
        map_annotation_training=map_annotation_training,
        map_all_target_training=map_all_target_training,
        map_grid_batches=map_grid_batches,
    )
    result = run_native(
        native,
        TleArchiveReader(Path(request["tle_root"])),
        config,
        SearchRegion(tuple(request["search_center"])),
        identities=request["scan_identities"],
        execution=ports,
        screen_latitude_deg=request["screen_center"][0],
        screen_longitude_deg=request["screen_center"][1],
        title=request["title"],
        evaluation_reference=request["evaluation_reference"],
        on_stage=lambda row: emit(dict(event="stage", **row)),
    )
    if result["status"] != "figures_ready":
        return dict(
            status=result["status"],
            resumed=False,
            request_sha256=request_sha,
            seconds=time.monotonic() - started,
            published=False,
        )
    rendered_at = time.monotonic()
    modules = source_bindings()
    configuration = dict(request=request, track_config=asdict(config), grid_seconds=300.0)
    evidence = build_evidence(
        result,
        identity=identity,
        provenance=dict(
            request_sha256=request_sha,
            configuration=configuration,
            configuration_sha256=canonical_digest(configuration),
            runtime=runtime_versions(),
            implementation_sha256=canonical_digest({k: v["sha256"] for k, v in modules.items()}),
            modules=modules,
        ),
        title=request["title"],
        renderer_revision=RENDER_REVISION,
        evaluation_reference=request["evaluation_reference"],
    )
    for record in (request["native_input"], request["track_config"]):
        read_bound(record)
    if source_bindings() != modules:
        raise ValueError("Owned implementation changed during result projection")
    stored = results.save(evidence, result["products"])
    saved_at = time.monotonic()
    manifest = publish_saved(identity["run_id"], results, publication)
    finished = time.monotonic()
    return dict(
        status="complete",
        resumed=False,
        request_sha256=request_sha,
        seconds=finished - started,
        native_to_render_seconds=rendered_at - started,
        evidence_save_seconds=saved_at - rendered_at,
        publication_seconds=finished - saved_at,
        scientific_receipt=stored,
        publication=manifest,
        production_admission_qualified=False,
    )
