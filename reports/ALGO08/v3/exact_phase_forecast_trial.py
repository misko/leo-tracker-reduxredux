"""Time the forecast on the genuine weak history and verify complete saved parity."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

import cumulative_grid_projection as prior
from aperture_trial import RELEASE, read, write
from exact_phase_forecast import forecast


JOB = Path("/dev/shm/leo-cumulative-grid-projection-01/weak-pair/binding.json")
MODES = ("stock", "candidate")


class MicroComplete(Exception):
    pass


def serialized_hash(document):
    from leo.application.localization_v3_engine import _json_value

    data = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False,
                      default=_json_value).encode()
    return sha256(data).hexdigest()


def timed(original, history, mode):
    cpu, elapsed = process_time_ns(), perf_counter_ns()
    value, counters = forecast(original, history) if mode == "candidate" else (original(history), {})
    return value, dict(cpu_ns=process_time_ns()-cpu, elapsed_ns=perf_counter_ns()-elapsed,
                       **counters)


def micro(original, history):
    samples, pin = [], None
    for order in (MODES, MODES[::-1], MODES, MODES[::-1]):
        clocks = {}
        for mode in order:
            value, data = timed(original, history, mode)
            found = serialized_hash(value)
            if pin is not None and found != pin:
                raise ValueError("The complete canonical forecast changed")
            pin = found
            clocks[mode] = data
        samples.append(dict(order=order, **clocks))
    median_saving = median(s["stock"]["cpu_ns"] - s["candidate"]["cpu_ns"] for s in samples)
    return dict(
        pairs=samples, forecast_sha256=pin, history_sha256=serialized_hash(history),
        history_norads=len(history["past_versions"]),
        history_snapshots=len(history["sources"]),
        history_versions=sum(map(len, history["past_versions"].values())),
        transitions=len(value["transitions"]),
        median_paired_saving_ns=median_saving, passed=median_saving >= 40_000_000,
    )


def worker(job, mode, output):
    import unified_short_bootstrap as cumulative

    publish = cumulative.publish_active
    audit = {}
    held = {}

    def observed(*args, **kwargs):
        # The original bootstrap has already installed its lazy facades at this boundary.
        from leo.application import localization_v3

        original = localization_v3.forecast

        def measure(history):
            if audit:
                raise ValueError("Expected one original causal forecast")
            if mode == "micro":
                audit.update(micro(original, history))
                raise MicroComplete()
            result, clocks = timed(original, history, mode)
            held["forecast"] = result
            audit.update(clocks)
            return result

        with patch.object(localization_v3, "forecast", measure):
            return publish(*args, **kwargs)

    with patch.object(cumulative, "publish_active", observed):
        try:
            # "combined" opts into the same exact Graph and evidence libraries in both arms.
            prior.worker(job, "combined", output)
        except MicroComplete:
            if mode != "micro":
                raise
            output.mkdir(exist_ok=True)
    if not audit:
        raise ValueError("Missing live saved forecast")
    if mode != "micro":
        audit["forecast_sha256"] = serialized_hash(held["forecast"])
    audit.update(
        mode=mode,
        source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest()
                       for name in ("exact-phase-forecast-protocol.md", "exact_phase_forecast.py",
                                    "exact_phase_forecast_trial.py")},
    )
    write(output / "forecast-audit.json", audit)


def matched_science(output, expected, request, clock):
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from short_raw_diagnostic import pairs

    worker_receipt = read(output / "cumulative-grid-worker.json")
    receipt = worker_receipt["receipt"]
    research = read(output / "joint-research-receipt.json")
    science = pairs.evidence(output, receipt, clock["started_unix_ns"], read_only=True)
    images = artifacts(output, receipt)["images"]
    grid = FastStandardAnalysisStore(output).position_grid(receipt["run_id"])
    (regional,) = research["early_regional"]
    if (any(science[key] != expected[key] for key in ("arms", "owners", "scientific_digests"))
            or receipt["terminal_sha256"] != expected["terminal_sha256"]
            or research["selected_rows"] != expected["owner_rows"]
            or prior.proof_fields(regional) != expected["proof"]
            or science["raw_authority"] != request["authority"]
            or sha256(native_packet(output).read_bytes()).hexdigest() != request["native"][7:]
            or not grid["complete"] or grid["evaluated_points"] != 179
            or canonical_digest(images) != canonical_digest(expected["figures"]) or len(images) != 8
            or worker_receipt["waveform_calls"] or worker_receipt["handoffs"] != 1
            or not worker_receipt["graph"]["enabled"]
            or worker_receipt["projection"]["calls"].get("native_selection") != 356):
        raise ValueError("Complete saved evidence differs from the pinned official layout and science")
    return dict(arms=science["arms"], owners=science["owners"],
                ordered_roles_sha256=canonical_digest(research["selected_rows"]),
                scientific_digests=science["scientific_digests"], images=images,
                regional=prior.proof_fields(regional), terminal_sha256=receipt["terminal_sha256"],
                proof_probes=regional["result"]["probes_evaluated"], grid_points=grid["evaluated_points"],
                numerical=worker_receipt["solve"], publication=worker_receipt["complete_publication"],
                forecast=read(output / "forecast-audit.json"), process=clock)


def run(root):
    from aperture_trial import archive_identity
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent],
                               text=True).strip() != "tmpfs":
        raise ValueError("Use a private tmpfs parent")
    request, packet, expected = prior.enrolled("weak")
    staged_job = read(JOB)
    if (request != {key: staged_job[key] for key in request}
            or sha256(packet.read_bytes()).hexdigest() != request["native"][7:]
            or archive_identity(Path(request["archive"]["root"])) != request["archive"]):
        raise ValueError("The existing saved complete pair or signed weak input changed")
    root.mkdir()
    (root / "tmp").mkdir()
    job = root / "binding.json"
    write(job, staged_job)
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    result = {}
    for mode in ("micro", *MODES):
        output = root / mode
        command = [python, "-IB", __file__, "worker", job, mode, output]
        clock = measure(command, env, output)
        write(root / f"{mode}-clock.json", dict(timing=clock, command=list(map(str, command))))
        if clock["exit_code"]:
            raise RuntimeError(clock["stderr_tail"])
        if mode == "micro":
            micro_receipt = read(output / "forecast-audit.json")
            if not micro_receipt["passed"]:
                break
        else:
            result[mode] = matched_science(output, expected, request, clock)
            write(root / f"{mode}-verified.json", result[mode])
    if result and (len(result) != 2 or any(
        row["forecast"]["forecast_sha256"] != micro_receipt["forecast_sha256"]
        for row in result.values()
    )):
        raise ValueError("The two live complete runs changed their actual forecast")
    write(root / "result.json", dict(machine=host(), binding=staged_job, micro=micro_receipt,
                                     complete=result, waveform_reads=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.argv[1:2] == ["worker"]:
        parser.add_argument("job", type=Path)
        parser.add_argument("mode", choices=("micro", *MODES))
        parser.add_argument("output", type=Path)
        worker(**vars(parser.parse_args(sys.argv[2:])))
    else:
        parser.add_argument("root", type=Path)
        run(**vars(parser.parse_args()))
