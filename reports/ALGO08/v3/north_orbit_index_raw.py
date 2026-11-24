"""Run the original guarded selective raw entry with a scan-local cold orbit index."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main(argv=None):
    from active_preparation_trial import bind_preparation
    from continued_cfo import raw_entry
    from historical_orbit_index import guarded_preparation

    cli = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    cli.add_argument("--anchored-cfo-pack", type=Path, required=True)
    cli.add_argument("--output", type=Path)
    args, inherited = cli.parse_known_args(argv)
    if args.output is not None:
        inherited.extend(("--output", str(args.output)))
    audit = {}
    with bind_preparation(guarded_preparation, audit):
        raw_entry(None, inherited, guarded_pack=args.anchored_cfo_pack)
    audit["adapter_sha256"] = sha256((HERE/"historical_orbit_index.py").read_bytes()).hexdigest()
    with (args.output.parent/"orbits-indexed.json").open("x") as stream:
        json.dump(audit, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
