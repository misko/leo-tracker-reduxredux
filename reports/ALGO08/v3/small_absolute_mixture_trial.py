"""Time a blind mixture before any saved publication or released fit runs."""

import argparse
from hashlib import sha256
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


class Complete(BaseException):
    """Do not let the research proposal enter the original output ports."""


def trial(case, output):
    import joint_publication as joint
    from aperture_trial import write
    from cumulative_grid_projection import worker as saved
    from dense_geographic_trial import host
    from doppler_difference_trial import enrollment

    parent = output.parent.resolve(strict=True)
    if parent.parent != Path("/dev/shm") or output.exists():
        raise ValueError("Use fresh private tmpfs output")
    job, request, pin = enrollment(case)
    run, result = joint.run, {}
    settings = host()

    def replace(_installed, _reader, _attempts, **_options):
        def inference(prepared, region, bound, _stages, **_evidence):
            ready = process_time_ns()
            from small_absolute_mixture import propose

            if prepared["status"] != "inputs_prepared":
                raise ValueError("The unchanged initial graph or geographic prerequisites failed")
            estimate = propose(prepared, region, bound)
            result.update(estimate, saved_prep_and_early_proof_cpu_ns=ready-started,
                          mixture_wall_scope_cpu_ns=process_time_ns()-ready,
                          elapsed_through_proposal_cpu_ns=process_time_ns()-started)
            raise Complete()
        return inference

    def capture(*args, **kwargs):
        from aperture_trial import archive_identity
        from leo.operations.tle_archive import TleArchiveReader
        from leo.storage.fast_scan import FastSegmentSource
        from named_constrained_research import deny_waveform

        archive = Path(request["archive"]["root"]).resolve(strict=True)
        if archive_identity(archive) != request["archive"]:
            raise ValueError("Expected the original causal catalogue")
        read = TleArchiveReader.read

        def local(reader, snapshot):
            if reader.root.resolve(strict=True) != archive or not snapshot.path.resolve(strict=True).is_relative_to(archive):
                raise ValueError("Use only the pre-staged causal bodies")
            return read(reader, snapshot)

        with (patch.object(FastSegmentSource, "windows", deny_waveform), patch.object(TleArchiveReader, "read", local),
              patch.object(joint, "full_catalogue_route", replace)):
            return run(*args, **kwargs)

    scratch = parent/f"{case}-scratch"
    started = process_time_ns()
    with patch.object(joint, "run", capture):
        try:
            saved(job, "combined", scratch)
        except Complete:
            pass
    if not result or any(scratch.glob("fast-scan-automatic-work/*/terminal.json")):
        raise ValueError("Only the original prepared numerical boundary may complete the diagnostic")
    sources = {name: sha256((HERE/name).read_bytes()).hexdigest() for name in (
        "small_absolute_mixture_trial.py", "small_absolute_mixture.py", "small-absolute-mixture-protocol.md")}
    write(output, dict(case=case, machine=settings, request_sha256=pin, native_sha256=request["native"],
                       archive=request["archive"], sources=sources, original_waveform_reads=0,
                       inference_before_original_owner_search=True, **result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=("physical", "north"))
    parser.add_argument("output", type=Path)
    trial(**vars(parser.parse_args()))
