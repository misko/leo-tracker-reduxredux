"""Apply the sealed short-primary stage shares to two complete publications."""

import argparse
from hashlib import sha256
import gzip
import json
from pathlib import Path

from .short_primary_fusion_profile import HERE, projection


ARCHIVES = {
    "north": ("continued-cfo-north.json.gz", "3b39eb1bcb201d3b53a73a85345934a4dc6b524b9bd3386c6feb7402c803fe3c"),
    "DS30-0008": ("dense-full-short-raw.json.gz", "51521b26848532823922cc43a198b7f91d59d3f1d81e155e5862b04b53193f38"),
}
PROFILE = "69613fd69b62395f285d153381bb2a57c07210eedf86f732173e9ad60508dca7"


def price(path):
    content = path.read_bytes()
    if path.suffix == ".gz":
        content = gzip.decompress(content)
    if sha256(content).hexdigest() != PROFILE:
        raise ValueError("The resident signed profile differs from the frozen evidence")
    audit = json.loads(content)
    result = dict(inputs=dict(profile_sha256=PROFILE, publications={}), projections={})
    for label, (name, pin) in ARCHIVES.items():
        archive = (HERE / "measurements" / name).read_bytes()
        if sha256(archive).hexdigest() != pin:
            raise ValueError(f"Archived complete publication changed for {label}")
        baseline = json.loads(gzip.decompress(archive))
        if label == "north":
            sealed = baseline["sealed"]
            native = sealed["raw"]["receiver_audit"]["native"]
            candidate, named = sealed["clock"], sealed["controls"]["named_clock"]
        else:
            native = baseline["candidate"]["recipe"]["receiver_audit"]["native"]
            candidate, named = baseline["process"], baseline["baseline"]["clocks"]
        result["inputs"]["publications"][label] = dict(archive=name, sha256=pin, candidate=candidate, named=named)
        extents = projection(audit["profile"], native["factors"]["short_primary"], native["native_calls"]["short_primary"],
            native["native_cpu_ns"]["short_primary"] / 1e9, candidate["elapsed_s"], named["elapsed_s"], candidate["cpu_s"], named["cpu_s"])
        extents["short_copy_only_cpu_grant_s"] = extents["attributed_s"]["verifier_load"]
        extents["short_verify_whole_cpu_grant_s"] = sum(extents["attributed_s"][name] for name in (
            "verifier_load", "integer_stencil", "fractional_vertex", "fractional_correlations", "fractional_spectrum_guard", "residual_readout",
        ))
        result["projections"][label] = extents
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("profile", type=Path)
    print(json.dumps(price(cli.parse_args().profile), sort_keys=True, indent=2, allow_nan=False))
