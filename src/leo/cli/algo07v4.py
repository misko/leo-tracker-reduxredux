"""Build, run, or resume a pinned ALGO07v4 native job with a hard deadline."""

import argparse
import json
import os
import signal
import sys
from pathlib import Path

from leo.cli.algo07v3 import launch, write


def worker(args, *, _execute=None):
    from leo.operations.localization_v3_job import JobInterrupted
    from leo.operations.localization_v4_job import execute

    execute_job = execute if _execute is None else _execute

    def interrupted(signum, _):
        raise JobInterrupted(f"Native job cancelled by signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        result = execute_job(
            json.loads(args.request.read_bytes()),
            native_manifest=args.native_manifest,
            receipts=args.outcome.parent / "native-receipts",
            resume_only=args.resume_only,
            emit=lambda value: print(json.dumps(value), flush=True),
        )
    except JobInterrupted as error:
        write(args.outcome, dict(status="interrupted", error=str(error)))
        return 130
    except Exception as error:
        write(args.outcome, dict(status="failed", error=f"{type(error).__name__}: {error}"))
        return 1
    write(args.outcome, result)
    return 0 if result["status"] == "complete" else 2


def main(*, _module="leo.cli.algo07v4", _worker=worker, _validator=None,
         _description=__doc__):
    parser = argparse.ArgumentParser(description=_description)
    commands = parser.add_subparsers(dest="action", required=True)
    build = commands.add_parser("build-native")
    build.add_argument("--output", type=Path, required=True)
    for action in ("run", "resume"):
        command = commands.add_parser(action)
        command.add_argument("--request", type=Path, required=True)
        command.add_argument("--work-dir", type=Path, required=True)
        command.add_argument("--native-manifest", type=Path, required=True)
        command.add_argument("--timeout", type=float, default=1200.0)
    command = commands.add_parser("_worker", help=argparse.SUPPRESS)
    command.add_argument("--request", type=Path, required=True)
    command.add_argument("--outcome", type=Path, required=True)
    command.add_argument("--native-manifest", type=Path, required=True)
    command.add_argument("--resume-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "build-native":
            # Pin BLAS before importing the numerical runtime in this fresh CLI process.
            for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
                os.environ[name] = "1"
            from leo.analysis.localization_v4.backend import build_native

            path = build_native(args.output)
            print(json.dumps(dict(status="complete", native_manifest=str(path))), flush=True)
            return 0
        if args.action == "_worker":
            return _worker(args)
        from leo.analysis.localization_v4.backend import read_manifest
        from leo.operations.localization_v4_job import validate_request

        validator = validate_request if _validator is None else _validator

        manifest = read_manifest(args.native_manifest)

        def validate(request):
            validator(request)
            if request["backend_manifest"] != manifest:
                raise ValueError("Native manifest differs from request backend binding")
            return request

        return launch(
            args, _module=_module, _validator=validate,
            _worker_arguments=("--native-manifest", str(args.native_manifest.resolve())),
        )
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps(dict(status="failed", error=str(error))), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
