"""Run the original guarded selective raw entry with a scan-local cold orbit index."""

import argparse
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


@contextmanager
def bind_active_publication(audit):
    import joint_publication
    from historical_orbit_index import guarded_preparation

    original = joint_publication.run

    def run(*args, raw_context, **options):
        @contextmanager
        def bound(scan):
            from tools import algo08_position

            with raw_context(scan):
                prepare = guarded_preparation(algo08_position.prepare_native_scan, audit)
                with patch.object(algo08_position, "prepare_native_scan", prepare):
                    yield

        return original(*args, raw_context=bound, **options)

    with patch.object(joint_publication, "run", run):
        yield


@contextmanager
def bind_runtime(audit):
    import empty_bootstrap

    original = empty_bootstrap.load_runtime
    with ExitStack() as scope:
        def load():
            installed = original()
            scope.enter_context(bind_active_publication(audit))
            return installed

        scope.enter_context(patch.object(empty_bootstrap, "load_runtime", load))
        yield


def main(argv=None):
    from continued_cfo import raw_entry

    cli = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    cli.add_argument("--anchored-cfo-pack", type=Path, required=True)
    cli.add_argument("--output", type=Path)
    args, inherited = cli.parse_known_args(argv)
    if args.output is not None:
        inherited.extend(("--output", str(args.output)))
    audit = {}
    with bind_runtime(audit):
        raw_entry(None, inherited, guarded_pack=args.anchored_cfo_pack)
    audit["adapter_sha256"] = sha256((HERE/"historical_orbit_index.py").read_bytes()).hexdigest()
    with (args.output.parent/"orbits-indexed.json").open("x") as stream:
        json.dump(audit, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
