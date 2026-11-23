"""Receiver-first inspection of a named ALGO08v3 acquisition, with same-process fallback."""

import argparse
import ast
import ctypes as ct
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import ModuleType
from unittest.mock import patch


BASELINE = Path("/opt/leo-algo08/algo08v3/run")
BASELINE_PIN = "fae032526227f55ca2419a0b29c69afc7fc97fa04508f33d0403802934f13448"
PAYLOAD = BASELINE.parent / "payload"
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
SCANNER = "tools/algo08_scan.py"
QUALIFICATION = "tools/pipeline_eval/qualification/"
RECEIVER = QUALIFICATION + "blind_compact_run.py"
FACTOR_RECORD = QUALIFICATION + "single_scan_position.py"
RECEIVER_ABI = QUALIFICATION + "single_scan_trial.py"
FACTOR_EXPORT = QUALIFICATION + "full_v5_check.py"
CONTINUATION = "tools/pipeline_eval/variants/carrier_continuation.py"
EXTRA_SOURCES = {
    SCANNER: "573d6608597f1619785688769e7504a4ad8ac30dd71fecd37876c678ed4aca53",
    RECEIVER: "2fd4596da78d6fd0a472b183c02e7636322eeb9cfb107d60df56424b38acfe85",
    FACTOR_RECORD: "690f2a72163b7bedb082999d0ee221607ab02270aace0a74b8703c14df00d432",
    RECEIVER_ABI: "022fae8bb43a4a11f039063df20a869dbff89017721cebc69e8ae2bdef3858cb",
    FACTOR_EXPORT: "90861af36b6e383d61cf2eb06ca27006110c62d01db9622cbea906b9429b775a",
    CONTINUATION: "f13fc2e02be5474de37b3efb5fba195e3a45daf534e3fa4e7d60c76500cef9ee",
}
DEFER = frozenset(("leo.operations.tle_archive", "leo.presentation.fast_standard_analysis",
                   "tools.algo08_position", "tools.pipeline_eval.qualification.blind_compact_run"))
SCIENTIFIC_IMPORTS = ("tools.algo08_position", "tools.pipeline_eval.variants.v5_core", "scipy", "matplotlib",
                      "leo.presentation.fast_standard_analysis")


def now():
    return process_time(), perf_counter()


def clock(start):
    return dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])


def checked(path, digest):
    data = path.read_bytes()
    if sha256(data).hexdigest() != digest:
        raise ValueError(f"Unreviewed bootstrap input: {path}")
    return data


def load_definitions(source, filename, names, namespace):
    tree = ast.parse(source, filename=str(filename))
    definitions = {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    exec(compile(ast.Module(body=[definitions[name] for name in names], type_ignores=[]), str(filename), "exec"), namespace)


def receiver_namespace(sources):
    from contextlib import contextmanager
    import numpy as np
    from tools.pipeline_eval.variants import carrier_continuation

    if Path(carrier_continuation.__file__).resolve() != PAYLOAD / CONTINUATION:
        raise ValueError("Expected the installed continuation module")
    scope = dict(__name__="_reviewed_receiver", ct=ct, np=np, Continuation=carrier_continuation.Continuation,
                 contextmanager=contextmanager)
    parsed = ast.parse(sources[FACTOR_EXPORT], filename=FACTOR_EXPORT)
    (margin,) = [node.value for node in parsed.body if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "MARGIN_GATE" for t in node.targets)]
    scope["MARGIN_GATE"] = ast.literal_eval(margin)
    for name, definitions in ((RECEIVER_ABI, ("Peak", "Native")), (FACTOR_RECORD, ("Factor",)),
                              (FACTOR_EXPORT, ("factor_candidate", "_probe")), (RECEIVER, ("detector",))):
        load_definitions(sources[name], PAYLOAD / name, definitions, scope)

    def stock_cancellation(method, edge, *, binary, pilot):
        if method != "cancellation" or binary is None or pilot is None:
            raise ValueError("Receiver-first path requires the installed cancellation assets")
        return scope["detector"](method, edge, binary=binary, pilot=pilot)

    return stock_cancellation


def staged_scanner(sources):
    tree = ast.parse(sources[SCANNER], filename=str(PAYLOAD / SCANNER))
    dropped = [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module in DEFER]
    if {node.module for node in dropped} != DEFER or len(dropped) != len(DEFER):
        raise ValueError("The installed scanner no longer has the reviewed import boundaries")
    tree.body = [node for node in tree.body if node not in dropped]
    scan = ModuleType("_reviewed_acquisition")
    scan.detector = receiver_namespace(sources)
    exec(compile(tree, str(PAYLOAD / SCANNER), "exec"), vars(scan))
    return scan


def empty_reason(native, validate_frequency):
    probes = native["source"]["probes"]
    if any(probe["candidates"] for probe in probes):
        return None
    if not probes:
        return "no valid receiver windows in the sealed recording"
    validate_frequency(native)
    return "no_active_curvature"


def check_inert_solver_assets(assets):
    manifest = json.loads(checked(assets / "native/manifest.json", "b40bc1f45368dd37ea39468117a77dae7b0e2672e411ba49a3ed50668238141c"))
    checked(assets / "projector.so", "7a183da26216e8d86c571aef8e48f29bade29a2c3b34bde56b26aebfefe6059d")
    paths = [(manifest[k], manifest[k+"_sha256"]) for k in ("source", "wrapper", "binary")]
    paths.append((manifest["provider"]["path"], manifest["provider"]["sha256"]))
    for name, expected in paths:
        with Path(name).open("rb") as stream:
            if file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError(f"Qualified numerical artifact changed: {name}")


def bind_native(native, session, inventory, digest, *, expected=None):
    from leo.contracts.digests import canonical_digest

    data = native["source"]
    raw = data["raw_recording_authority_digest"]
    if (data["session_id"] != session or data["input_manifest_sha256"] != inventory
            or data["qualified"] is not True or native["provenance"]["detector_sha256"] != "sha256:"+digest
            or data["analysis_manifest_sha256"] != canonical_digest(["cancellation", raw, digest, data["probes"]])
            or expected is not None and canonical_digest(native) != expected):
        raise ValueError("Staged detections differ from the original receiver or raw authority")


def receipt_zeros(publication):
    return dict(screened_nomination={}, sparse_rank_projection=[], graph_path={},
                tle_records=dict(catalogues=0, records=0, fallback=0),
                endpoint_reuse=dict(models=0, endpoint_calculations=0, repeated_endpoint_calls=0,
                                    other_coordinate_calls=0, context_rebuilds=0, unsupported_context_calls=0, endpoint_cpu_s=0.),
                recovery_reuse=dict(executed_gates=0, reused_pairs=0), curved_design={},
                member_lookahead=dict(attempts=0, submitted=0, submitted_bytes=0, cpu_ns=0, wall_ns=0),
                posterior_grid_handoff=dict(arithmetic=publication.POSTERIOR_GRID_ARITHMETIC))


def run(args):
    started = now()
    root = args.bulk_root.resolve(strict=True)
    if not root.is_dir() or any(root.iterdir()):
        raise ValueError("Receiver-first publication requires a new empty directory")
    checked(BASELINE, BASELINE_PIN)
    launcher = runpy.run_path(str(BASELINE))
    specification = launcher["checked_spec"](PAYLOAD)
    imports = [str(PAYLOAD), str(RELEASE / "src"), str(RELEASE)]
    sys.path[:0] = imports
    os.environ["PYTHONPATH"] = os.pathsep.join(imports)
    for name in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
        os.environ[name] = "1"
    sources = {name: checked(PAYLOAD / name, digest) for name, digest in EXTRA_SOURCES.items()}
    phases = {"source_checks": clock(started)}
    timer = now()
    from tools.pipeline_eval.variants.experimental.lean_startup import install
    install()
    from tools.pipeline_eval.qualification import experimental_publication as publication
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes
    from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer
    from leo.analysis.glrt_frequency_input import frequency_evidence

    if Path(publication.__file__).resolve() != PAYLOAD / "tools/pipeline_eval/qualification/experimental_publication.py":
        raise ValueError("Expected the installed numerical publication entry point")
    scan = staged_scanner(sources)
    offer = scan.Algo08Region.parse(json.loads(args.region.read_bytes()))
    phases["receiver_setup"] = clock(timer)
    lookahead = {}
    digest = specification["detector_sha256"]
    with TemporaryDirectory() as temporary:
        assets = Path(temporary)
        for name in (*scan.PINS, "native", "projector.so"):
            source = Path(specification["detector"]) if name == "cancellation-factors.so" else RELEASE / "assets" / name
            (assets / name).symlink_to(source)
        scan.PINS["cancellation-factors.so"] = digest
        for name, pin in scan.PINS.items():
            checked(assets / name, pin)
        paired = specification["paired_sha256"]
        library = assets / "paired-sha256.so"
        library.write_bytes(checked(Path(paired["library"]), paired["sha256"]))
        acquisition = publication._with_member_lookahead(scan.acquire, publication._checked_member_lookahead(specification), lookahead)
        cumulative = clock(timer)
        phases["receiver_asset_checks"] = {key: cumulative[key] - phases["receiver_setup"][key] for key in cumulative}
        timer = now()
        session, inventory_digest, inventory = scan.FastScanStore(root).inventory(args.recording, verify_windows=False)
        if args.saved is None:
            with compressed_input_buffer(), paired_decoded_hashes(library):
                native = acquisition(session, inventory_digest, inventory, assets)
        else:
            native = json.loads(args.saved.read_bytes())
        bind_native(native, session, inventory_digest, digest, expected=args.saved_digest)
        phases["authenticated_handoff"] = clock(timer)

        calls = 0

        def handoff(bound_session, bound_inventory, *_):
            nonlocal calls
            if calls or (session, inventory_digest) != (bound_session, bound_inventory):
                raise ValueError("Expected one verified handoff of the previously acquired packet")
            calls += 1
            return native

        timer = now()
        reason = empty_reason(native, frequency_evidence)
        before = [name for name in SCIENTIFIC_IMPORTS if name in sys.modules]
        if reason is None:
            from tools import algo08_scan

            # The stock launcher installs exactly the same lazy facade loader above.
            with patch.object(algo08_scan, "acquire", handoff):
                result = publication.run(args, dict(specification, startup="stock"))
            route = "ordinary_installed_fit"
        else:
            check_inert_solver_assets(assets)
            scan.acquire = handoff
            scan.TleArchiveReader = lambda path: path
            scan.solve = lambda *_: (dict(status="withheld", reason=reason,
                                         arms={arm: {"latlon": None} for arm in ("c0", "fitted_c")}), None, "stock")
            result = scan.analyze(args.recording, root, assets, args.archive, offer)
            result.update(receipt_zeros(publication))
            route = "authenticated_empty"
        if calls != 1:
            raise ValueError("The original installed publication did not consume the authenticated acquisition once")
        if args.saved is None:
            result["member_lookahead"] = lookahead
        phases["decision_and_publication"] = clock(timer)
    after = [name for name in SCIENTIFIC_IMPORTS if name in sys.modules]
    if reason is not None and any(name in after for name in ("tools.algo08_position", "matplotlib", "leo.presentation.fast_standard_analysis")):
        raise ValueError("The empty route imported deferred scientific modules")
    audit = dict(schema_version=1, bootstrap="receiver-first research", route=route,
                 original_receiver_sha256=digest, original_frozen_specification="sha256:"+launcher["FINGERPRINT"],
                 named_launcher_sha256=BASELINE_PIN, source_sha256=EXTRA_SOURCES,
                 experiment_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                 solver_modules_before_decision=before, solver_modules_after_publication=after,
                 raw_acquisitions=int(args.saved is None), verified_handoffs=calls,
                 probes=len(native["source"]["probes"]), factors=sum(len(p["candidates"]) for p in native["source"]["probes"]),
                 phases=phases, measured_before_audit_write=clock(started))
    (root / "empty-bootstrap.json").write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("recording", "archive", "region", "bulk-root"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--saved", type=Path)
    parser.add_argument("--saved-digest")
    sub = parser.parse_args()
    if bool(sub.saved) != bool(sub.saved_digest):
        parser.error("--saved and --saved-digest must be used together")
    print(json.dumps(run(sub)))
