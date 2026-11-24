"""Replay the exact saved owner captures and seal blind contrast fits."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
REQUESTS = {
    "physical": ("weak", "ffe5c64a84d5a119e9c22ad7a9283164308b5f9c486acf747c02fd379fc72c97"),
    "north": ("north", "db4f9cbea446e9e9cbb03701ce57cb903c163921334cb54eff34eca9787e10b7"),
}
PREVIOUS = "1e28c18d4d6fa16102abee15252500289bd2223caf39f97c1b581d740f29a305"


class Finish(BaseException):
    """Stop before any map or publication after the genuine owner handoff."""


def checked(path, digest):
    data = path.read_bytes()
    if sha256(data).hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError(f"Changed archived evidence at {path}")
    return data


def enrollment(case):
    from aperture_trial import archive_identity

    name, request_pin = REQUESTS[case]
    job = Path(f"/dev/shm/leo-v3-owned-cfo-{name}01/request.json")
    request = json.loads(checked(job, request_pin))
    archive = Path(request["archive"]["root"])
    paths = [archive, Path(request["packet"]), Path(request["saved_inventory"]), Path(request["region"])]
    if any(subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", path.resolve(strict=True)], text=True).strip() != "tmpfs"
           for path in paths):
        raise ValueError("Every original sampled input must be staged on tmpfs")
    if archive_identity(archive) != request["archive"]:
        raise ValueError("The original chronological causal archive changed")
    for field, pin in (("packet", "native"), ("region", "offer_sha256"), ("saved_inventory", "inventory")):
        checked(Path(request[field]), request[pin])
    return job, request, request_pin


def trial(case, output):
    import joint_publication as joint
    from aperture_trial import write
    from cumulative_grid_projection import worker as saved
    from dense_geographic_trial import host

    if output.parent.resolve(strict=True).parent != Path("/dev/shm") or output.exists():
        raise ValueError("Use a fresh direct tmpfs research folder")
    job, request, request_pin = enrollment(case)
    prior = json.loads(gzip.decompress(checked(HERE/"measurements/centre-oracle-step.json.gz", PREVIOUS)))["complete"][case]
    if (request["native"] != prior["binding"]["native_sha256"]
            or request["archive"]["snapshots_sha256"] != prior["binding"]["archive"]["snapshots_sha256"]):
        raise ValueError("The previous witness did not use these exact original causal inputs")

    class Oracle:
        result = None

        def bind(self, native, _assets):
            from leo.contracts.digests import canonical_digest

            if canonical_digest(native) != request["native"]:
                raise ValueError("The saved path supplied a different signed receiver packet")

        def prepare(self, operation, *args, **kwargs):
            return operation(*args, **kwargs)

        def repair(self, _prepared, signed, measured):
            from doppler_difference_fit import arm_fit
            from fixed_causal_estimation import flatten
            from local_future_repair import memberships

            owner_cpu_ns = process_time_ns()-started
            arms = ("c0", "fitted_c")
            rows = {arm: flatten(memberships(signed, arm)) for arm in arms}
            aliases = dict(conditional_aliases=list(signed["node"]["aliases"]),
                           predictive_aliases={entry["component"]: entry["alias"] for entry in signed["entries"]})
            if (any(rows[arm] != list(map(tuple, prior["oracle_rows"])) for arm in arms)
                    or aliases != prior["oracle_aliases"]):
                raise ValueError("The genuine current saved handoff changed its previous exact owners or signed aliases")
            operands = tuple(signed[key] for key in ("scan", "node", "keep", "entries", "means", "model"))
            start = process_time_ns()
            fits = {arm: arm_fit(*operands, arm) for arm in arms}
            self.result = dict(owner_provider_cpu_ns=owner_cpu_ns, paired_diagnostic_cpu_ns=process_time_ns()-start,
                               fit=fits, oracle_rows=rows["c0"], oracle_aliases=aliases,
                               owner_provider_signed=measured.get("named_survivor_fit", {}).get("status"))
            raise Finish()

    policy = Oracle()
    run = joint.run

    def capture(*args, **kwargs):
        from leo.operations.tle_archive import TleArchiveReader
        from leo.storage.fast_scan import FastSegmentSource
        from named_constrained_research import deny_waveform

        archive = Path(request["archive"]["root"]).resolve(strict=True)
        read = TleArchiveReader.read

        def local(reader, snapshot):
            if reader.root.resolve(strict=True) != archive or not snapshot.path.resolve(strict=True).is_relative_to(archive):
                raise ValueError("Only use the pre-staged original causal archive")
            return read(reader, snapshot)

        with patch.object(FastSegmentSource, "windows", deny_waveform), patch.object(TleArchiveReader, "read", local):
            return run(*args, local_future_policy=policy, **kwargs)

    machine = host()
    started = process_time_ns()
    scratch = output.with_name(f"{case}-scratch")
    with patch.object(joint, "run", capture):
        try:
            saved(job, "combined", scratch, named_survivor_finish=True)
        except Finish:
            pass
    if policy.result is None or any(scratch.glob("fast-scan-automatic-work/*/terminal.json")):
        raise ValueError("No completed owner capture at the pre-publication boundary")
    sources = {name: sha256((HERE/name).read_bytes()).hexdigest() for name in (
        "doppler_difference_fit.py", "doppler_difference_trial.py", "doppler-differences-protocol.md")}
    write(output, dict(case=case, sources=sources, machine=machine, request_sha256=request_pin, previous_sha256=PREVIOUS,
                       original_native_sha256=request["native"], archive=request["archive"], raw_reads=0, **policy.result))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("case", choices=("physical", "north"))
    cli.add_argument("output", type=Path)
    trial(**vars(cli.parse_args()))
