"""Replay the locked secant fit on eight prespecified confirmation inputs."""

import argparse
from pathlib import Path
from tarfile import open as tar_open

from ..__main__ import implementation_digest, save_json
from ..variants import v5_secant_fit
from . import phase_confirmation as phase

METHOD = "v5_secant_fit"
REPORT = phase.REPORT.with_name("secant-confirmation")
SCRATCH = phase.SCRATCH.with_name("secant-confirmation")
TIMING = REPORT.with_name("position-fit")


def _cli_digest():
    return implementation_digest(METHOD, Path(v5_secant_fit.__file__))


def roster(inputs):
    original = phase.roster(inputs)
    ds26, ds29 = original["ds26_in_hash_order"][:4], original["ds29"][:4]
    cases = ds26 + ds29
    earlier = phase._read(phase.REPORT / "roster.json")
    if earlier != original:
        raise ValueError("secant selection differs from the frozen phase-confirmation roster")
    return dict(
        cases=cases,
        ds26_in_hash_order=ds26,
        ds29=ds29,
        timing_cases=original["timing_cases"],
        protocol_sha256=phase.digest(REPORT / "PROTOCOL.md"),
        parent_roster_sha256=phase.digest(phase.REPORT / "roster.json"),
        position_fit_source_receipt_sha256=phase.digest(TIMING / "seal.json"),
        cli_implementation_sha256=_cli_digest(),
        deadline_s=phase.CAP_S,
        case_bindings={ident: original["case_bindings"][ident] for ident in cases},
    )


def frozen_sources():
    original = phase._read(TIMING / "seal.json")
    source = original["compact_source_sha256"]
    with tar_open(TIMING / "sealed-solver-source.tar.gz", "r:gz") as archive:
        saved = {name: phase.corpus._sha(archive.extractfile(name).read()) for name in source}
    if (
        source != saved
        or source != phase.pinned_sources(METHOD)
        or original["frozen_v5_sha256"] != phase.v5_lean.SOURCE_SHA256
        or original["pair_limit_s"] != phase.CAP_S
    ):
        raise ValueError(
            "secant solver or compact dependencies differ from the six-case source lock"
        )
    return source


def _validate(row, ident, case, binding, sources):
    phase._validate_candidate(
        row, ident, case, binding, sources, method=METHOD, cli_digest=_cli_digest()
    )
    if row["result"]["status"] == "ok":
        metrics = row["result"]["metrics"]
        counts = metrics["initial_phase_refresh_counts"]
        if (
            not counts
            or not all(1 <= count <= 5 for count in counts)
            or metrics["position_optimizer"]["calls"] < 1
        ):
            raise ValueError(
                f"{ident} is missing the measured secant optimizer and original refresh history"
            )
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "seal", "score"))
    parser.add_argument("--work", type=Path, default=SCRATCH)
    parser.add_argument("--output", type=Path, default=REPORT)
    parser.add_argument("--cpus", type=int, nargs="+", default=[16, 17, 18, 19])
    args = parser.parse_args()
    if args.command == "run":
        source = frozen_sources()
        save_json(args.output / "roster.json", roster(phase.frozen_inputs()))
        save_json(args.output / "source-lock.json", source)
        phase.replay(args.work, args.cpus, source, method=METHOD, select=roster, validate=_validate)
    elif args.command == "seal":
        frozen_sources()
        phase.seal(args.work, args.output, method=METHOD, select=roster, validate=_validate)
    else:
        phase.score(args.output, candidate_method=METHOD)


if __name__ == "__main__":
    main()
