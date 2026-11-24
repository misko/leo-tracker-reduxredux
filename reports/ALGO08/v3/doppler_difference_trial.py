"""Replay the exact saved owner captures and seal blind contrast fits."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch


def trial(case, output):
    import centre_oracle_iterative_trial as original
    from aperture_trial import write
    from doppler_difference_fit import arm_fit

    if output.parent.resolve(strict=True).parent != Path("/dev/shm") or output.exists():
        raise ValueError("Use a fresh direct tmpfs research folder")
    sealed = output.with_name(f"{case}-matched-owner.json")
    with patch.object(original, "arm_iterative", arm_fit):
        original.trial(case, sealed)
    data = json.loads(sealed.read_bytes())
    data["sources"].update({name: original.file_sha(original.HERE / name) for name in (
        "doppler_difference_fit.py", "doppler_difference_trial.py", "doppler-differences-protocol.md")})
    write(output, data)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("case", choices=("physical", "north"))
    cli.add_argument("output", type=Path)
    trial(**vars(cli.parse_args()))
