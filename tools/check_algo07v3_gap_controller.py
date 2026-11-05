"""External oracle for the complete ordered conditional-gap scientific controller.

The reference runs the frozen controller body and original numerical stage entry
points. Its legacy export/relocation ports are replaced with explicit immutable
fixture inputs. Candidate inference imports no old worker or filesystem adapter.
This qualifies a controller over a frozen context, not complete native inference.
"""

import argparse
import contextlib
import hashlib
import io
import json
import sys
import time
import traceback
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint

NUMERICAL_KEYS = (
    "reference_limit_s",
    "centered_lbfgsb",
    "extra_optimizer_rounds",
    "physical_priors_and_target_phase_support_unchanged",
    "reference_updates",
    "optimizer_calls",
    "problem_count",
)


def run(args):
    import numpy as np

    inputs = {}

    def read(path):
        path = Path(path)
        raw = path.read_bytes()
        inputs[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    def plain(value):
        return json.loads(
            json.dumps(value, default=lambda x: np.asarray(x).tolist(), allow_nan=False)
        )

    began = time.monotonic()
    inventory = read(args.inventory)
    decision = read(args.decision)
    observations = read(args.source / "observations.json")
    # This fixture protects the independently published original source support;
    # it is explicit, not inferred from whichever numerical trial happens to win.
    owners = {arm: row["owners"] for arm, row in decision["source_support"].items()}
    annotations = {}
    for attempt in decision["attempts"]:
        tid = attempt["track_id"]
        folder = args.decision.parent / tid / "annotation"
        if (folder / "result.json").exists():
            annotations[tid] = {
                key: read(folder / (key + ".json")) for key in ("protocol", "result")
            }
    numerical_receipts, stage_summary = [], []
    if args.side == "candidate":
        from check_algo07v3_track_preparation import deny_legacy

        sys.addaudithook(deny_legacy)
        from check_algo07v3_fixture_context import owned_context

        from leo.analysis.localization_v3.gap_controller import recover_gaps

        context = owned_context(args.source, inputs)

        def execute(name, operation, cap):
            # Every operation in this bounded fixture must finish successfully;
            # fail the comparison rather than hide a candidate exception.
            started = time.monotonic()
            value = operation()
            if time.monotonic() - started >= cap:
                raise TimeoutError("component exceeded its original stage cap")
            return True, value

        result = recover_gaps(
            context,
            inventory,
            observations,
            decision,
            annotations,
            owners,
            run_stage=execute,
            clock=time.monotonic,
            maximum_seconds=1200,
        )
        for row in result["stages"]:
            kind = row["name"].rsplit("-", 1)[1]
            stage_summary.append(
                dict(stage=kind, completed=row["status"] == "complete", cap=row["timeout_s"])
            )
            if kind != "prepare" and row["status"] == "complete":
                numerical_receipts.append(result["numerical_receipts"][row["name"]])
        targets = result.pop("targets")
        result.pop("numerical_receipts")
    else:
        sys.path[:0] = [str(args.runtime / "src"), str(args.runtime / "tools")]
        import algo05_gap_stage as stage_module
        import algo05_recovery_worker as controller
        import diagnose_all_large_tracks
        from benchmark_graph_covariance import load_case
        from debug_fast_graph_unassociated import write

        context = load_case(args.source.parent, args.source.name)
        work = args.output.parent / (args.output.stem + "-work")
        work.mkdir(exist_ok=False)
        export = work / "source-export"
        export.mkdir()
        write(
            export / "descriptor.json",
            dict(root=str(export), files={}, incumbent={}, source_recovery_root="explicit-fixture"),
        )

        # Only the legacy IO boundary is adapted. Current numerical inputs and
        # controller decisions are unchanged; no science is evaluated here.
        def relocate(*unused):
            current = work / "current"
            current.mkdir()
            inv = (
                current / "all-large-track-recovery" / inventory["job"]["job_id"] / "inventory.json"
            )
            inv.parent.mkdir(parents=True)
            write(inv, inventory)
            write(current / "decision.json", decision)
            for tid, annotation in annotations.items():
                (current / tid / "annotation").mkdir(parents=True)
                for key, value in annotation.items():
                    write(current / tid / "annotation" / (key + ".json"), value)
            return dict(explicit_fixture_io=True)

        def execute(command, *, log, timeout):
            script, arguments = command[3], command[4:]
            diagnose_all_large_tracks.context = lambda _: context
            saved_argv = sys.argv
            messages = io.StringIO()
            started = time.monotonic()
            try:
                with contextlib.redirect_stdout(messages), contextlib.redirect_stderr(messages):
                    if script == "prepare":
                        stage_module.prepare(read(arguments[0]), Path(arguments[1]))
                    else:
                        stage_module.execute(args.runtime / "tools" / script, arguments)
                if time.monotonic() - started >= timeout:
                    raise TimeoutError("reference component exceeded its original stage cap")
                if script != "prepare":
                    out = Path(arguments[arguments.index("--output") + 1])
                    receipt = read(out.parent / (out.name + "-numerics.json"))
                    numerical_receipts.append({key: receipt[key] for key in NUMERICAL_KEYS})
                return 0
            except Exception:
                traceback.print_exc(file=messages)
                raise
            finally:
                log.write(messages.getvalue().encode())
                sys.argv = saved_argv

        controller.read = read
        controller.relocate = relocate
        controller.owners = lambda _: owners
        controller.execute = execute
        controller.run(work, 1200)
        result = read(work / "decision.json")
        protocol = read(work / "protocol.json")
        targets = [{k: v for k, v in t.items() if k != "validation"} for t in protocol["targets"]]
        kind_by_script = dict(
            prepare="prepare",
            **{
                "annotate_predictive_only.py": "annotation",
                "include_predictive_annotations.py": "inclusion",
                "audit_shared_predictive_inclusion.py": "audit",
            },
        )
        for row in result["stages"]:
            stage_summary.append(
                dict(
                    stage=kind_by_script[row["command"][3]],
                    completed=row["returncode"] == 0,
                    cap=row["timeout_s"],
                )
            )
        for row in result["trials"]:
            row.pop("path")
        if result["selected"]:
            result["selected"].pop("path", None)
    result["stages"] = stage_summary
    result.update(targets=targets, numerical_receipts=numerical_receipts)
    # The controller's persisted contract is JSON, unlike the numerical-array
    # component oracle. Serialize arrays/scalars identically before bitwise checks.
    result = plain(result)
    args.output.write_text(json.dumps(fingerprint(result), sort_keys=True, allow_nan=False) + "\n")

    def binding(path):
        return dict(path=str(path), sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())

    for directory in (args.source, args.source.parent / "causal_prior" / args.source.name):
        for path in directory.iterdir():
            if path.is_file():
                inputs[str(path)] = binding(path)["sha256"]
    cavity = args.source.parent / "family_cavity/position" / f"{args.source.name}.json"
    inputs[str(cavity)] = binding(cavity)["sha256"]
    receipt = dict(
        side=args.side,
        seconds=time.monotonic() - began,
        inputs=inputs,
        modules={
            n: binding(m.__file__)
            for n, m in sys.modules.items()
            if getattr(m, "__file__", None)
            and (
                str(m.__file__).startswith(str(args.runtime))
                or "/src/leo/" in str(m.__file__)
                or n
                in (
                    "check_algo07v3_fixture_context",
                    "check_algo07v3_track_preparation",
                    "check_algo07v3_scan_likelihood",
                )
            )
        },
        tool=binding(__file__),
        output=binding(args.output),
        scope="Fresh ordered gap controller over a frozen context and explicit protected owners",
        full_pipeline_parity=False,
        ordinary_clock_equivalence=False,
        normalized_fields=[
            "trial/selected.path",
            "targets.validation",
            "stage.command",
            "stage.seconds",
            "generated provenance and JSON array serialization",
        ],
    )
    args.output.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                side=args.side,
                seconds=receipt["seconds"],
                targets=len(targets),
                stages=len(stage_summary),
                selected_branch=(result["selected"] or {}).get("branch_id"),
                output=receipt["output"],
            )
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", choices=["reference", "candidate"], required=True)
    for key in ("source", "inventory", "decision", "runtime", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".receipt.json").exists():
        raise ValueError("Controller output exists")
    run(args)
