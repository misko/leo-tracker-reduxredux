"""External joint-stage component oracle on explicit frozen numerical fixtures.

This deliberately supplies a saved cavity context and qualified target groups
to both sides. It is NOT a full-pipeline inference or a target-selection test.
Candidate numerical code owns its scan, likelihood, geometry, fit and audit;
legacy imports are allowed only on the separate reference side.
"""

import argparse
import hashlib
import inspect
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from algo07v3_inclusion_oracle import original_callable
from check_algo07v3_scan_likelihood import fingerprint


def run(args):
    if args.side == "candidate":
        from check_algo07v3_track_preparation import deny_legacy

        sys.addaudithook(deny_legacy)
        from leo.analysis.localization_v3.joint_recovery import audit_joint, fit_joint, joint_inputs
        from leo.analysis.localization_v3.new_family import NewFamily
        from leo.analysis.localization_v3.recovery_inventory import recovery_context
        from leo.analysis.localization_v3.region import SearchRegion
        from leo.analysis.localization_v3.scan import ScanLikelihood
    else:
        sys.path[:0] = [str(args.runtime / "src"), str(args.runtime / "tools")]
        import audit_two_predictive_families as original_audit
        import fit_two_predictive_families as original_fit
        import retry_two_family_positions as original_retry
        from benchmark_graph_covariance import load_case
        from predictive_new_family import NewFamily
        from probe_joint_predictive_families import joint_inputs
    import numpy as np

    started = time.monotonic()
    inputs = {}

    def read(path):
        raw = path.read_bytes()
        inputs[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    source = args.source
    metadata = read(source / "receipt.json")
    cavity_path = source.parent / "family_cavity/position" / f"{source.name}.json"
    cavity = read(cavity_path)
    protocol = read(args.probe / "protocol.json")
    probe_result = read(args.probe / "result.json")
    targets = protocol["targets"]
    if args.side == "candidate":
        with np.load(source / "bank.npz") as data:
            bank = dict(data)
        inputs[str(source / "bank.npz")] = hashlib.sha256(
            (source / "bank.npz").read_bytes()
        ).hexdigest()
        prior_root = source.parent / "causal_prior" / source.name
        previous = (prior_root / "previous.tle").read_bytes()
        provenance = read(prior_root / "previous_receipt.json")
        metadata = read(prior_root / "receipt.json")
        noise = read(source / "radio_noise.json")
        scan = ScanLikelihood(
            read(source / "tracks.json"),
            bank,
            read(source / "nominal_elements.json"),
            origin_utc_ns=metadata["origin_utc_ns"],
            regional_center=metadata["regional_center"],
            noise=noise,
            noise_sha256=inputs[str(source / "radio_noise.json")],
            search_region=SearchRegion((37.906, -122.545)),
            previous_tle=previous.decode(),
            previous_tle_sha256=hashlib.sha256(previous).hexdigest(),
            previous_sources=provenance["sources"],
        )
        inputs[str(prior_root / "previous.tle")] = hashlib.sha256(previous).hexdigest()
        context = recovery_context(scan, cavity)
    else:
        context = load_case(source.parent, source.name)
    fixture_inventory = read(args.inventory)
    probe = dict(
        protocol={
            k: v for k, v in protocol.items() if k not in ("job", "source_trials", "source_hashes")
        },
        result=probe_result,
    )
    families = [
        NewFamily(
            context["scan"],
            group,
            context["model"],
            phase_step=0.0625,
            allow_uncalibrated_label=True,
        )
        for group in targets
    ]
    geometry = {
        a: joint_inputs(families, p, x, context["powers"], context["entries"])
        for a, (p, x) in context["problems"].items()
    }
    records = {}
    for method in ("control", "factorized", "joint"):
        if args.method and method not in ("control", args.method):
            continue
        for arm in ("c0", "fitted_c"):
            if args.arm and arm != args.arm:
                continue
            key = method + "-" + arm
            if args.side == "candidate":
                trial = fit_joint(context, probe, arm, method, optimizer=args.optimizer)
                audit = audit_joint(
                    context,
                    fixture_inventory,
                    trial,
                    records.get("control-" + arm, {}).get("audit"),
                )
            else:
                # Original numeric run body from x initialization onward. IO,
                # job/hash receipts and elapsed seconds are excluded explicitly.
                import ast

                function = (original_fit if args.optimizer == "lbfgsb" else original_retry).run
                tree = ast.parse(inspect.getsource(function)).body[0]
                begin = next(
                    i
                    for i, n in enumerate(tree.body)
                    if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "x" for t in n.targets)
                )
                tree.body = tree.body[begin:]

                class NoIO(ast.NodeTransformer):
                    def visit_Expr(self, n):
                        if (
                            isinstance(n.value, ast.Call)
                            and isinstance(n.value.func, ast.Name)
                            and n.value.func.id in ("write", "print")
                        ):
                            return None
                        return self.generic_visit(n)

                    def visit_Assign(self, n):
                        if any(
                            isinstance(t, ast.Subscript)
                            and isinstance(t.slice, ast.Constant)
                            and t.slice.value == "seconds"
                            for t in n.targets
                        ):
                            return None
                        return self.generic_visit(n)

                    def visit_Call(self, n):
                        n = self.generic_visit(n)
                        if isinstance(n.func, ast.Attribute) and n.func.attr == "update":
                            n.keywords = [k for k in n.keywords if k.arg != "seconds"]
                        return n

                tree = NoIO().visit(tree)
                tree.body.append(ast.Return(value=ast.Name(id="result", ctx=ast.Load())))
                fs = [
                    NewFamily(
                        context["scan"],
                        group,
                        context["model"],
                        phase_step=0.0625,
                        allow_uncalibrated_label=True,
                    )
                    for group in targets
                ]
                namespace = dict(function.__globals__, d=context, families=fs)
                exec(
                    compile(
                        ast.fix_missing_locations(ast.Module(body=[tree], type_ignores=[])),
                        inspect.getsourcefile(function),
                        "exec",
                    ),
                    namespace,
                )
                result = namespace["run"](SimpleNamespace(method=method, arm=arm))
                pr = dict(
                    job=dict(job_id="fixture"),
                    targets=targets,
                    source_hashes={},
                    method=method,
                    arm=arm,
                    phase_step_s=0.0625,
                )
                saved = {
                    Path("/trial/protocol.json"): pr,
                    Path("/trial/result.json"): result,
                    Path("/" + f"control-{arm}" + "/audit.json"): records.get(
                        "control-" + arm, {}
                    ).get("audit"),
                }

                def load(path, saved=saved):
                    return fixture_inventory if path.name == "inventory.json" else saved[path]

                captured = {}
                original_callable(
                    original_audit.run,
                    read=load,
                    context=lambda _: context,
                    write=lambda path, value, captured=captured: captured.update(audit=value),
                )(
                    SimpleNamespace(
                        trial=Path("/trial"), study=Path("/study"), output=Path("/audit.json")
                    )
                )
                audit = {k: v for k, v in captured["audit"].items() if k != "source_hashes"}
                trial = dict(result=result)
            records[key] = dict(result=trial["result"], audit=audit)
            print(key, audit["RF_qualified_arm"], flush=True)
    result = dict(geometry=geometry, records=records)
    args.output.write_text(json.dumps(fingerprint(result), sort_keys=True, allow_nan=False) + "\n")

    def binding(path):
        return dict(path=str(path), sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())

    modules = {
        n: binding(m.__file__)
        for n, m in sys.modules.items()
        if getattr(m, "__file__", None)
        and (
            str(m.__file__).startswith(str(args.runtime))
            or "/src/leo/" in str(m.__file__)
            or n
            in (
                "algo07v3_inclusion_oracle",
                "check_algo07v3_scan_likelihood",
                "check_algo07v3_track_preparation",
            )
        )
    }
    # Reference context loader reads additional fixture files. Bind the complete
    # immutable snapshot rather than imply only the explicit reads matter.
    for directory in (source, source.parent / "causal_prior" / source.name):
        for path in directory.iterdir():
            if path.is_file():
                inputs[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = dict(
        side=args.side,
        seconds=time.monotonic() - started,
        inputs=inputs,
        modules=modules,
        tool=binding(__file__),
        output=binding(args.output),
        optimizer=args.optimizer,
        method=args.method,
        arm=args.arm,
        scope="Frozen-context joint stage component only",
        full_pipeline_parity=False,
    )
    args.output.with_suffix(".receipt.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    )
    print(json.dumps({k: receipt[k] for k in ("seconds", "output", "scope")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "probe", "inventory", "runtime", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--side", choices=["candidate", "reference"], required=True)
    parser.add_argument("--optimizer", choices=["lbfgsb", "powell"], default="lbfgsb")
    parser.add_argument("--method", choices=["control", "factorized", "joint"])
    parser.add_argument("--arm", choices=["c0", "fitted_c"])
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Output exists")
    run(args)
