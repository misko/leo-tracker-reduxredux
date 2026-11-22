"""Measure exact curved design preparation on archived deployed-margin solver inputs."""

import argparse
import json
import runpy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
OVERLAY = HERE.parents[2] / "tools/pipeline_eval/variants/algo08_curved_design.py"
SOURCE = HERE / "measurements/solver-deployed-margin-recovery.json"


def run(case, mode, staged, spec, output):
    from tools.pipeline_eval import qualification
    from tools.pipeline_eval.qualification import experimental_publication

    archived = json.loads(SOURCE.read_bytes())["cases"][case]
    prep = archived["prepared_input_differential"]
    archive = Path(prep["archive"]["root"])
    offer, baseline, candidate = (staged / f"{name}.json"
                                  for name in ("offer", "baseline", "candidate"))
    check = runpy.run_path(str(HERE / "residual_attribution_trial.py"))
    read = check["read"]
    control = staged / "terminal.json"
    control_digest = sha256(control.read_bytes()).hexdigest()
    if control_digest != archived["restored_terminal_sha256"]:
        raise ValueError("Expected the previously checked deployed-margin terminal")

    launch = experimental_publication.run
    counts = {}

    def measured_launch(args, specification):
        from leo.contracts.digests import canonical_digest
        from tools import algo08_position

        # Verify with the checkout's archived-pair helpers after the frozen
        # startup has installed its package hook, outside the solve clock.
        helper_path = OVERLAY.parents[1] / "qualification"
        with patch.object(qualification, "__path__", [*qualification.__path__, str(helper_path)]):
            from tools.pipeline_eval.qualification.paired_publication import (
                archive_identity,
                verify_sources,
            )

        for name, path in (("baseline", baseline), ("candidate", candidate)):
            if canonical_digest(read(path)) != prep["native"][name]:
                raise ValueError(f"The saved {name} detection document differs from the archive")
        if read(offer) != prep["offer"] or archive_identity(archive) != prep["archive"]:
            raise ValueError("Expected the archived offer and bound causal archive")
        original_spec = read(spec)
        if canonical_digest(original_spec) != archived["restored_native_specification"]:
            raise ValueError("Expected the frozen solver from the margin crossover")
        launcher = spec.parent / "reports/ALGO08/single-core-2x/run-candidate"
        verify_sources(launcher, original_spec["sources"])

        solve = algo08_position.solve

        def measured_solve(*args, **kwargs):
            measure = runpy.run_path(str(OVERLAY))["measured_curved_design"]
            with measure(enabled=mode == "direct") as work:
                decision = solve(*args, **kwargs)
            counts.update(work)
            return decision

        with patch.object(algo08_position, "solve", measured_solve):
            return launch(args, specification)

    margin_worker = runpy.run_path(str(HERE / "solver_deployed_margin_trial.py"))["cross_worker"]
    with TemporaryDirectory() as directory:
        terminal = Path(directory) / "terminal.json"
        with patch.object(experimental_publication, "run", measured_launch):
            margin_worker(candidate, baseline, spec, archive, offer, terminal)
        result = read(terminal)
    from leo.contracts.digests import canonical_digest

    reference = read(control)
    fields = ("status", "reason", "arms", "owners", "associated", "orbit_policy")
    checks = {name: result.get(name) == reference.get(name) for name in fields}
    for key in ("endpoint_reuse", "posterior_grid_handoff"):
        actual, expected = (
            {k: v for k, v in record[key].items() if not k.endswith(("_cpu_s", "_cpu_ns"))}
            for record in (result, reference)
        )
        checks[key + "_counts"] = actual == expected
    checks["both_arms_equal_deployed"] = result["arms"] == archived["published_deployed_arms"]
    evidence = {}
    for name, document in result.pop("evidence").items():
        clean = {k: v for k, v in document.items() if k not in ("binding", "elapsed_seconds")}
        expected = {k: v for k, v in reference["evidence"][name].items()
                    if k not in ("binding", "elapsed_seconds")}
        checks[name] = clean == expected
        evidence[name] = canonical_digest(clean)
    with output.open("x") as stream:
        json.dump(dict(case=case, mode=mode, timings=dict(counts), results=result,
                       checks_against_margin_control=checks, science=evidence,
                       specification=archived["restored_native_specification"],
                       native=prep["native"], archive=prep["archive"], offer=prep["offer"],
                       control_terminal_sha256=control_digest,
                       overlay_sha256=sha256(OVERLAY.read_bytes()).hexdigest()),
                  stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    if not all(checks.values()) or (mode == "direct" and not counts.get("direct_assembly_calls")):
        raise RuntimeError(f"Failed saved solver parity. See {output}.")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("case", choices=("DS30-0008", "south"))
    cli.add_argument("mode", choices=("stock", "direct"))
    for name in ("staged", "spec", "output"):
        cli.add_argument(name, type=Path)
    run(**vars(cli.parse_args()))
