"""Publish one requested calibration after the compact paired scientific decision."""

import argparse
import json
import runpy
import shutil
import subprocess
import sys
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

ARMS = ("c0", "fitted_c")
PUBLICATIONS = ("paired", "paired-interior")
SOURCE = "leo/analysis/localization_v3/conservative_recovery.py"
BEGIN = '    original_ids = {o["observation_id"] for o in observations}\n'
END = '    return dict(\n        status="complete" if stable else "gate_refit_unstable",\n'
SCHEMA = "compact-selected-calibration-v1"
PROJECTED_SOURCE_SHA = "98b3c4f3ee012dc62c4ebb6bae660e23f4f686aecfb0348399d97bf34390c8a8"


def strip_reporting(text):
    """Omit the terminal association report unused by the standalone compact pipeline."""
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError("unrecognized conservative recovery source")
    first = text.index(BEGIN)
    last = text.index(END)
    removed = text[first:last]
    if not (
        first < last
        and removed.count("extend_associations(") == 1
        and removed.count('["association_tracks"] =') == 1
        and removed.count('["association"] =') == 1
        and removed.count("    for arm in ARMS:") == 1
    ):
        raise ValueError("conservative recovery changed beyond its terminal reporting seam")
    return text[:first] + text[last:]


def install(base, target):
    from .. import whole_iq
    from ..__main__ import local_output, save_json, write
    from ..original_receiver import receiver_assets

    target = local_output(target)
    programs = receiver_assets(base)
    mapping = {**programs, **whole_iq.native_sources(base)}
    shutil.copytree(base, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    write(target / SOURCE, strip_reporting((base / SOURCE).read_text()).encode())
    backend = target / "native/manifest.json"
    manifest = whole_iq.read(backend)
    for key in ("source", "wrapper", "binary"):
        manifest[key] = str(target / Path(manifest[key]).relative_to(base.resolve()))
    save_json(backend, manifest)
    installed = {**whole_iq.receiver_identity(target), **whole_iq.native_sources(target)}
    for name, digest in mapping.items():
        if name not in (SOURCE, "native/manifest.json") and installed[name] != digest:
            raise ValueError(f"selected-arm installation changed {name}")
    save_json(
        target / "arm-install.json",
        dict(base=str(base.resolve()), base_files=mapping, installed_files=installed),
    )
    return installed


def verify_install(root):
    from .. import whole_iq
    from ..__main__ import encoded
    from ..original_receiver import CALIBRATION_SHA, NUMERIC_SOURCES

    identity = whole_iq.read(root / "arm-install.json")
    expected = identity["base_files"]
    base_programs = {
        k: v
        for k, v in expected.items()
        if k not in NUMERIC_SOURCES and k != "native/manifest.json"
    }
    if sha256(encoded(base_programs)).hexdigest() != CALIBRATION_SHA:
        raise ValueError("unqualified paired release in the selected-arm installation")
    native = whole_iq.native_sources(root)
    installed = {**whole_iq.receiver_identity(root), **native}
    if native != NUMERIC_SOURCES or identity["installed_files"] != installed:
        raise ValueError("selected-arm release differs from its installation receipt")
    if expected.keys() != installed.keys() or any(
        installed[key] != digest
        for key, digest in expected.items()
        if key not in (SOURCE, "native/manifest.json")
    ):
        raise ValueError("selected-arm release has unexpected changed sources")
    if installed[SOURCE] != PROJECTED_SOURCE_SHA:
        raise ValueError("selected-arm release changed conservative science")
    return installed


class PhaseViews:
    """Own only the exact immutable phase-width and receipt views of one scan."""

    def __init__(self, operation):
        self.operation = operation
        self.scan = None
        self.views = {}
        self.calls = 0
        self.reused = 0
        self.computed_cpu_s = 0.0

    def __call__(self, scan, labels):
        if self.scan is not scan:
            self.scan = scan
            self.views.clear()
        key = tuple(labels)
        self.calls += 1
        if key not in self.views:
            start = process_time()
            self.views[key] = self.operation(scan, labels)
            self.computed_cpu_s += process_time() - start
        else:
            self.reused += 1
        widths, receipts = self.views[key]
        return widths.copy(), [dict(row) for row in receipts]


def _worker(root, request):
    entry = runpy.run_path(str(root / "__main__.py"))
    entry["validate_region"](request["tile"], request["screen_center"], request["width_km"])
    entry["activate"](root)
    from leo.analysis.localization_v3 import (
        conservative_recovery,
        family_cavity,
        family_weighting,
        history_policy,
        signed_context,
    )

    from tools.pipeline_eval.variants import v5_direct_cavity

    if family_weighting.phase_widths is not signed_context.phase_widths:
        raise ValueError("expected the same direct causal phase-width operation")
    views = PhaseViews(signed_context.phase_widths)
    proof = {}
    conservative = conservative_recovery.conservative_recovery
    family = history_policy.history_policy
    signed = signed_context.signed_context
    nominate = family_cavity.nominate_families
    cavity = family_cavity.cavity_policy

    def trace_conservative(*args, **kwargs):
        result = conservative(*args, **kwargs)
        proof["conservative"] = dict(
            status=result["status"],
            before=result.get("exclusion_history"),
            after=result.get("post_salvage_history"),
            returned_arms=sorted(result.get("arms", {})),
        )
        if any(
            "association" in row or "association_tracks" in row
            for row in result.get("arms", {}).values()
        ):
            raise ValueError(
                "selected-arm package unexpectedly produced the unused association report"
            )
        return result

    def trace_family(*args, **kwargs):
        result = family(*args, **kwargs)
        proof["family"] = dict(
            status=result["status"],
            reason=result.get("reason"),
            linear_paired_valid=result.get("linear_paired_valid"),
            steps=result.get("curved_gate_history"),
        )
        return result

    def trace_signed(*args, **kwargs):
        result = signed(*args, **kwargs)
        proof["signed"] = dict(accepted=result["signed"]["accepted"], arms=sorted(result["arms"]))
        return result

    def trace_nomination(*args, **kwargs):
        result = nominate(*args, **kwargs)
        proof["nomination"] = dict(
            status=result["status"], families=len(result.get("families", []))
        )
        return result

    def trace_cavity(*args, **kwargs):
        result = cavity(*args, **kwargs)
        proof["cavity"] = dict(
            status=result["status"],
            accepted=result.get("accepted"),
            trials=[
                dict(paired_valid=row["paired_valid"], arms=sorted(row["arms"]))
                for row in result.get("trials", [])
            ],
        )
        return result

    with ExitStack() as stack:
        for module, name, function in (
            (conservative_recovery, "conservative_recovery", trace_conservative),
            (history_policy, "history_policy", trace_family),
            (signed_context, "signed_context", trace_signed),
            (family_cavity, "nominate_families", trace_nomination),
            (family_cavity, "cavity_policy", trace_cavity),
            (family_weighting, "phase_widths", views),
            (signed_context, "phase_widths", views),
        ):
            stack.enter_context(patch.object(module, name, function))
        result = v5_direct_cavity.run(**request)
    entry["verify_project_modules"](root)
    return dict(
        numerical=result,
        trace=proof,
        phase_views=dict(
            calls=views.calls,
            reused=views.reused,
            computed_cpu_s=views.computed_cpu_s,
        ),
    )


def selected(result, arm, tile, publication):
    from ..scoring import validate_result
    from .final_region import publish

    if arm not in ARMS or publication not in PUBLICATIONS:
        raise ValueError("choose a real calibration and explicit paired publication policy")
    validate_result(result)
    if set(result.get("arms", {})) != set(ARMS):
        raise ValueError("selected calibration requires the original two-arm decision")
    guarded = publish(result, tile, enabled=publication == "paired-interior")
    outcome = guarded["arms"][arm]
    return dict(
        schema=SCHEMA,
        calibration=arm,
        publication=publication,
        status=guarded["status"],
        reason=guarded.get("reason"),
        fit=outcome,
        paired_decision_sha256=sha256(
            json.dumps(
                {k: guarded.get(k) for k in ("status", "reason", "arms")},
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest(),
        frequency_score=guarded["metrics"].get(f"{arm}_frequency_score"),
        guard_margin_km=guarded["metrics"].get("exact_tile_margin_km", {}).get(arm),
    )


def arguments(compact, receiver):
    return dict(
        compact,
        native_backend=str(receiver / "native/manifest.json"),
        library=str(receiver / "projector.so"),
    )


def solve_selected(receiver, compact, arm, publication, *, timeout_s=None):
    start = perf_counter()
    result = subprocess.run(
        [
            sys.executable,
            "-IB",
            str(Path(__file__).resolve()),
            "worker",
            str(receiver),
        ],
        input=json.dumps(arguments(compact, receiver)),
        text=True,
        stdout=subprocess.PIPE,
        check=True,
        timeout=timeout_s,
    )
    raw = json.loads(result.stdout)
    tile = dict(center=compact["tile"], width_km=compact["width_km"])
    return dict(
        raw,
        selected=selected(raw["numerical"], arm, tile, publication),
        wrapper_wall_s=perf_counter() - start,
    )


def main(argv=None):
    from .. import whole_iq
    from ..__main__ import THREAD_ENV, local_output

    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    build = actions.add_parser("install")
    build.add_argument("--base", type=Path, required=True)
    build.add_argument("--out", type=local_output, required=True)
    run = actions.add_parser("select")
    run.add_argument("--receiver", type=Path, required=True)
    run.add_argument("--request", type=Path, required=True)
    run.add_argument("--request-sha256", required=True)
    run.add_argument("--calibration", choices=ARMS, required=True)
    run.add_argument("--publication", choices=PUBLICATIONS, required=True)
    run.add_argument("--timeout", type=int, choices=range(1, 601), default=180)
    args = parser.parse_args(argv)
    if args.action == "install":
        install(args.base.resolve(strict=True), args.out)
        return
    import os

    os.environ.update(THREAD_ENV)
    path = whole_iq.checked(args.request, args.request_sha256)
    request = whole_iq.read(path)
    archive = Path(request["compact"]["archive"])
    actual = {p.name: whole_iq._sha(p) for p in archive.rglob("*.tle")}
    if not actual or actual != request["causal_snapshots"]:
        raise ValueError("causal catalogue differs from the authenticated request")
    receiver = args.receiver.resolve(strict=True)
    verify_install(receiver)
    result = solve_selected(
        receiver, request["compact"], args.calibration, args.publication, timeout_s=args.timeout
    )
    print(json.dumps(result["selected"], allow_nan=False))


if __name__ == "__main__":
    if sys.argv[1:2] == ["worker"] and len(sys.argv) == 3:
        print(
            json.dumps(_worker(Path(sys.argv[2]).resolve(), json.load(sys.stdin)), allow_nan=False)
        )
    else:
        main()
