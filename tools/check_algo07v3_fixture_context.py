"""Explicit frozen numerical fixture loader, never a production input adapter."""

import hashlib
import json


def owned_context(source, bindings):
    import numpy as np

    from leo.analysis.localization_v3.recovery_inventory import recovery_context
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.localization_v3.scan import ScanLikelihood

    def read(path, *, raw=False):
        value = path.read_bytes()
        bindings[str(path)] = hashlib.sha256(value).hexdigest()
        return value if raw else json.loads(value)

    prior_root = source.parent / "causal_prior" / source.name
    metadata = read(prior_root / "receipt.json")
    previous = read(prior_root / "previous.tle", raw=True)
    provenance = read(prior_root / "previous_receipt.json")
    noise = read(source / "radio_noise.json")
    read(source / "bank.npz", raw=True)
    with np.load(source / "bank.npz") as data:
        bank = dict(data)
    scan = ScanLikelihood(
        read(source / "tracks.json"),
        bank,
        read(source / "nominal_elements.json"),
        origin_utc_ns=metadata["origin_utc_ns"],
        regional_center=metadata["regional_center"],
        noise=noise,
        noise_sha256=bindings[str(source / "radio_noise.json")],
        search_region=SearchRegion((37.906, -122.545)),
        previous_tle=previous.decode(),
        previous_tle_sha256=hashlib.sha256(previous).hexdigest(),
        previous_sources=provenance["sources"],
    )
    cavity = read(source.parent / "family_cavity/position" / f"{source.name}.json")
    return recovery_context(scan, cavity)
