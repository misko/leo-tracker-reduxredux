"""Read-only TLE composition for a padded, fixed-provenance orbital phase bank."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import ElementSetCatalogue
from tools.evaluate_sparse_glrt import local_output, states, write_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    args = p.parse_args()
    local_output(args.bundle)
    meta = json.loads((args.bundle / "input-receipt.json").read_text())
    chosen = causal_catalogue(TleArchiveReader(args.tle_root), meta["causal_cutoff_utc_ns"])
    lookup = {n: i for i, n in enumerate(chosen.catalogue.satellite_numbers)}
    indexes = []
    for expected in meta["satellite_provenance"]:
        i = lookup[expected["norad"]]
        if chosen.provenance[i] != expected:
            raise ValueError("archived element selection changed")
        indexes.append(i)
    c = chosen.catalogue
    bank = ElementSetCatalogue(
        tuple(c.names[i] for i in indexes),
        tuple(c.satellite_numbers[i] for i in indexes),
        tuple(c.satellites[i] for i in indexes),
    )
    nodes = np.arange(-21, meta["duration_s"] + 21.25, 0.25)
    utc = meta["anchor_utc_ns"] + np.rint(nodes * 1e9).astype(np.int64)
    position, velocity, usable = states(bank, utc)
    if not usable.all():
        raise ValueError("phase propagation failed")
    path = args.bundle / "orbit-phase-bank.npz"
    if path.exists():
        raise FileExistsError(path)
    np.savez_compressed(
        path,
        position=position,
        velocity=velocity,
        nodes_s=nodes,
        norad=np.array(bank.satellite_numbers),
    )
    write_json(
        args.bundle / "orbit-phase-receipt.json",
        dict(
            digest=hashlib.sha256(path.read_bytes()).hexdigest(),
            count=len(bank),
            node_step_s=0.25,
            support_s=[float(nodes[0]), float(nodes[-1])],
            original_orbit_digest=meta["orbit_bank_sha256"],
            scope=(
                "same archived element choices; ephemeris phase uncertainty; "
                "receiver UTC anchor fixed"
            ),
        ),
    )
    print(json.dumps(dict(count=len(bank), nodes=len(nodes))), flush=True)


if __name__ == "__main__":
    main()
