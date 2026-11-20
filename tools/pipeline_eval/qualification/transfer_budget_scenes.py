"""Draw and seal a geographically disjoint transfer case using the established simulator."""

from pathlib import Path

import numpy as np

from ..__main__ import encoded
from ..scoring import distance_km
from . import clock_transfer_inputs as inputs
from . import compact_transfer as compact
from .fresh_scenes import _new, _read

SITE = (47.0, 72.0)
ROLES = ("original", "near-outside", "far-outside")


def generate(root, seed):
    generator = np.random.default_rng(int.from_bytes(seed, "big"))
    old = inputs._prior_sites()
    previous = _read(compact.prior.REPORT / "truth.json")
    old.update(tuple(r["latlon"]) for r in previous.values() if r["latlon"] is not None)
    previous_draws = _read(compact.prior.REPORT / "draws.json")
    used = {
        row[key]["sha256"] for row in previous_draws.values() for key in ("causal", "trajectory")
    }
    old.add(
        tuple(
            compact.portable.references("ds26-common127", [compact.portable.ROOF_CASE])[1][0][
                "truth"
            ]
        )
    )
    for _ in range(12):
        site = tuple(generator.uniform(-2, 2, size=2) + SITE)
        if min(distance_km(site, r) for r in old) >= 1_000:
            break
    else:
        raise ValueError("new site exceeds the disjointness draw budget")
    for _ in range(8):
        earlier, later, anchor = inputs._history(inputs.snapshots(), used, generator)
        bank = inputs._true_bank(
            inputs._tle(earlier), inputs._tle(later), anchor, later["received"]
        )
        try:
            probes, counter, info = inputs.cold._generate_capture(bank, anchor, site, generator)
        except ValueError as exc:
            if str(exc) != "insufficient visible causal orbit opportunities":
                raise
        else:
            break
    else:
        raise ValueError("fresh simulation exceeds the visibility draw budget")
    pool, receipts = inputs.empirical.donors()
    disturbance = inputs.empirical._inject(
        dict(probes=probes, first_counter=counter), pool, generator
    )
    case = generator.bytes(12).hex()
    native = inputs._native(case, anchor, counter, probes)
    raw = encoded(native)
    available = dict(inputs._offers(site, generator))
    plan = [dict(id=available[role]["id"], tile=available[role]) for role in ROLES]
    private, public = root / "private", root / "public"
    private.mkdir(mode=0o700)
    public.mkdir()
    inputs.cold._new(private / "seed.bin", seed)
    _new(
        private / "truth.json",
        dict(
            location=site,
            roles={item["id"]: role for role, item in zip(ROLES, plan, strict=True)},
            nearest_prior_km=min(distance_km(site, r) for r in old),
            trajectory=later,
            emitter_ids=info["emitters"],
            disturbed_lanes=disturbance,
        ),
    )
    inputs.cold._new(public / "native.json", raw)
    _new(
        public / "cases.json",
        dict(
            source=earlier,
            cutoff=anchor,
            capture_id=case,
            offers=plan,
            sha256=inputs.cold._sha(raw),
            donor_receipts=receipts,
        ),
    )


def jobs(root: Path):
    public = root / "public"
    manifest = _read(public / "cases.json")
    data = (public / "native.json").read_bytes()
    if manifest["sha256"] != inputs.cold._sha(data):
        raise ValueError("fresh public native input differs from its sealed digest")
    document = compact.complete_native(_read(public / "native.json"))
    earlier = manifest["source"]["sha256"]
    history, objects, inventory = compact.history_at(manifest["cutoff"], earlier)
    jobs = [
        compact.bound_job(
            dict(
                id=row["id"],
                capture_id=manifest["capture_id"],
                native_sha256=manifest["sha256"],
                catalog_sha256=earlier,
            ),
            document,
            row["tile"],
            history,
            objects,
        )
        for row in manifest["offers"]
    ]
    return jobs, inventory
