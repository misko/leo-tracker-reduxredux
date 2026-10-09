"""Minimal explicit freezer. No reconstruction, orbit calls or fits on import."""

import hashlib
import json
from pathlib import Path

from coarse_import import source_check
from driver import append, verify_plan

from leo.contracts.digests import canonical_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PILOT_SESSION = "scan-fw-f1a32cacd910c005"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_plan(document_path, imports_path, verified_identity, *, repository=ROOT):
    """Requires future authorized full-array preflight, never invents its hashes."""
    repository = Path(repository)
    document = json.loads(Path(document_path).read_text())
    imported = json.loads(Path(imports_path).read_text())
    if document["session_id"] != PILOT_SESSION or imported["session_id"] != PILOT_SESSION:
        raise ValueError("only the previously specified consumed DS18-022 pilot is authorized")
    ignored = source_check(document, repository)
    if imported["bank_numbers"] != document["diagnostics"]["bank"]["retained_numbers"]:
        raise ValueError("import bank mismatch")
    points = document["methods"][0]["points"]
    if len(imported["records"]) != len(points) or [r["point"] for r in imported["records"]] != [
        [p["east_km"], p["north_km"]] for p in points
    ]:
        raise ValueError("ordinary point coverage changed")
    if not verified_identity or any(
        not verified_identity.get(k) for k in ("observations_sha256", "bank_sha256", "prior_sha256")
    ):
        raise ValueError("authorized reconstructed-array preflight identity is required")
    for key in ("input_manifest_sha256", "analysis_manifest_sha256", "evidence_sha256"):
        if verified_identity.get(key) != document[key]:
            raise ValueError("preflight input identity mismatch")
    previous = json.loads(
        (repository / "reports/2026_10_09_position_error_iter107/protocol.json").read_text()
    )
    names = {
        n
        for n in previous["source_sha256"]
        if Path(n).suffix in (".py", ".cpp", ".h", ".hpp", ".so")
    }
    names.update(str(p.relative_to(repository)) for p in HERE.glob("*.py"))
    names.update(
        str(p.relative_to(repository))
        for p in (
            HERE / "README.md",
            HERE / "PROVENANCE.md",
            HERE / "IMPORT_PREFLIGHT.md",
            HERE.parent / "2026_10_09_position_error_iter113/SEARCH_COMPARISON_DRAFT.md",
            HERE.parent / "2026_10_09_position_error_iter114/fixed_bank.py",
        )
    )
    loader = "reports/2026_10_09_position_error_iter105/run.py"
    names.add(loader)
    inputs = {
        str(Path(p).resolve().relative_to(repository.resolve())): sha(p)
        for p in (document_path, imports_path)
    }
    provenance = imported["baseline_trace_source"]
    if sha(repository / provenance["path"]) != provenance["sha256"]:
        raise ValueError("baseline provenance source changed")
    inputs[provenance["path"]] = provenance["sha256"]
    previous_path = "reports/2026_10_09_position_error_iter107/protocol.json"
    inputs[previous_path] = sha(repository / previous_path)
    binding = dict(
        session_id=PILOT_SESSION,
        document_path=str(Path(document_path).resolve().relative_to(repository.resolve())),
        document_sha256=sha(document_path),
        loader_source=loader,
        loader_sha256=sha(repository / loader),
        imports_path=str(Path(imports_path).resolve().relative_to(repository.resolve())),
        imports_sha256=sha(imports_path),
    )
    plan = dict(
        pilot="DS18-022",
        exposure="consumed mechanism pilot; not validation",
        slice_count=12,
        slice_seconds=500,
        source_sha256={n: sha(repository / n) for n in sorted(names)},
        input_sha256=inputs,
        binding=binding,
        identity=verified_identity,
        native_baseline=imported["native_baseline"],
        ignored_nonnumeric_source_mismatches=ignored,
        policy=(
            "pre-recovery native fits; whole-prior plug-in queue rescore; matched c arms; "
            "no post-search recovery or localization claim"
        ),
        imported_receipts_sha256=canonical_digest(imported),
    )
    verify_plan(plan, repository)
    return plan


def publish_protocol(plan, destination, *, repository=ROOT):
    """Explicit caller action only, after independent review and authorization."""
    verify_plan(plan, repository)
    append(destination, plan)
