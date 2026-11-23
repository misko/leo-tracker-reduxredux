"""Rebuild one masked forward fit per recording and seal predictions before RF scoring."""

import argparse
from contextlib import ExitStack
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import RELEASE, archive_identity, read, write
from dense_full_short_raw import usage
from dense_geographic_trial import host
from erased_block_repair import central_block, clock, compare, guarded_selection, now, paired_rf_scores
from full_short_graph_transfer import inputs as weak_inputs
from full_short_physical import environment
from full_short_raw import RECIPE_SHA


HERE = Path(__file__).resolve().parent
CASES = ("DS30-0016", "DS30-0057")
COVERAGE = HERE / "measurements/crossfit-future-coverage.json.gz"
COVERAGE_PIN = "db0d5ab68802acb69bf2bebc3da75e33adda5bbf9b2d1d5ed65d16479240b736"
GEO = Path("/var/tmp/leo-dense-short-pins.0zaX7eSH/geographic.so")
REGIONAL = Path("/var/tmp/leo-regional-track.O238AD0C/scores.so")


def enrol(case):
    coverage = gzip.decompress(COVERAGE.read_bytes())
    if sha256(coverage).hexdigest() != COVERAGE_PIN:
        raise ValueError("Unexpected frozen future-only coverage witness")
    entry, = [row for row in json.loads(coverage)["cases"] if row["case"] == case]
    block = central_block(entry["blocks"])
    return dict(case=case, block=block["block"], seconds=block["seconds"], held_ids=block["held_ids"],
                original_detector_sha256=entry["source_sha256"],
                forward_rebuild_reference_cpu_s=entry["prior_forward_solve_cpu_s"],
                paired_refit_reference_cpu_s=entry["previous_full_repair_cpu_s"])


def inputs(case):
    if case == "DS30-0016":
        return (*weak_inputs("physical"), GEO, REGIONAL)
    from local_future_0057 import inputs as transfer_inputs

    row, pin, path, geo, regional = transfer_inputs("forward")
    return Path(row["recording"]), row["archive"], Path(row["region_file"]), path, pin, row["region"], geo, regional


class DiagnosticComplete(Exception):
    pass


class Fold:
    def __init__(self, plan):
        self.plan = plan
        self.record = {}

    def bind(self, native, assets):
        from leo.contracts.digests import canonical_digest
        from local_future_policy import TRACKS_SHA256

        self.start = now()
        if self.record or canonical_digest(native) != self.plan["original_detector_sha256"]:
            raise ValueError("The fold must reconstruct exactly one original sealed detector packet")
        if sha256((assets / "tracks.json").read_bytes()).hexdigest() != TRACKS_SHA256:
            raise ValueError("Changed installed graph in fold reconstruction")
        self.forward, self.training, self.held, regenerated = guarded_selection(native, self.plan)
        self.native = native
        self.record.update(selection=clock(self.start), forward_sha256=canonical_digest(self.forward),
                           erased_factors=len(self.held), original_probes=len(native["source"]["probes"]),
                           future_after_erasure=regenerated, future_after_guard=len(self.training))
        self.rebuild = now()

    def prepare(self, original, native, *args, **kwargs):
        if self.native is not native:
            raise ValueError("The masked fold does not bind the original signed handoff")
        return original(self.forward, *args, **kwargs)

    def repair(self, prepared, signed, measured):
        self.record["forward_rebuild"] = clock(self.rebuild)
        items = ("candidate_pre_evidence_clocks", "signed_total_clocks", "exterior_clocks")
        self.record["forward_stages"] = {key: measured[key] for key in items}
        self.record["causal_history_cutoff_utc_ns"] = prepared["sky"]["metadata"]["cutoff_utc_ns"]
        timer = now()
        self.record.update(compare(prepared, signed, self.training, self.held))
        self.record["forecast_and_repair"] = clock(timer)
        raise DiagnosticComplete

    def stop_before_grid(self, *_args):
        self.record.update(status="original_forward_fell_back_before_joint_forecast", forward_rebuild=clock(self.rebuild))
        raise DiagnosticComplete


def worker(case, output):
    import joint_publication
    from full_short_run import geographic_projection
    from local_future_pins import checked_dependencies

    started = now()
    recording, archive, region, saved, pin, offer, geo, regional = inputs(case)
    plan = enrol(case)
    if pin != plan["original_detector_sha256"]:
        raise ValueError("Held block was sealed for a different packet")
    dependencies = checked_dependencies()
    options = SimpleNamespace(saved=saved, saved_digest=pin, output=output, recording=recording, archive=Path(archive["root"]),
                              region=region, verify_images=False, optimized_full_catalogue=True)
    fold = Fold(plan)
    configuration = joint_publication.configuration
    with ExitStack() as scope:
        def setup():
            publication, specification = configuration()
            from leo.contracts.algo08_region import Algo08Region
            from tools import algo08_position

            if archive_identity(Path(archive["root"])) != archive or Algo08Region.parse(read(region)).document() != offer:
                raise ValueError("The fold's causal archive or original offer changed")
            scope.enter_context(patch.object(algo08_position, "selected_packet", fold.stop_before_grid))
            return publication, specification

        scope.enter_context(patch.object(joint_publication, "configuration", setup))
        try:
            terminal = joint_publication.run(options, early_regional=True, reuse_cold_rows=True,
                       local_future_policy=fold, saved_receiver=RECIPE_SHA,
                       geographic_projector=lambda: geographic_projection(geo, regional))
        except DiagnosticComplete:
            pass
        else:
            fold.record.update(status="original_forward_withheld", reason=terminal["route"], forward_rebuild=clock(fold.rebuild))
    write(output / "blind-forecast.json", dict(plan=plan, **fold.record, complete_worker=clock(started),
          source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
              "erased_block_repair.py", "erased_block_repair_trial.py", "erased-block-repair-protocol.md")},
          dependencies=dependencies, archive=archive, offer=offer, coverage_sha256=COVERAGE_PIN))


def run(case, directory):
    machine = host()
    directory.mkdir(exist_ok=True)
    output = directory / case
    started, wall = usage(), now()
    process = subprocess.run([RELEASE / "venv/bin/python", "-BPs", __file__, "worker", output, case],
                             env=environment(directory), timeout=60, capture_output=True, text=True)
    after = usage()
    write(directory / f"{case}-clock.json", dict(machine=machine, exit=process.returncode, elapsed_s=clock(wall)["elapsed_s"],
                     **{name: after[name]-value for name, value in started.items()}))
    (directory / f"{case}-stderr").write_text(process.stderr)
    if process.returncode:
        raise RuntimeError(process.stderr[-4000:])


def score(directory):
    from leo.analysis.localization_v3.tracks import winning_observations
    from leo.contracts.digests import canonical_digest

    host()
    sealed = {case: read(directory / case / "blind-forecast.json") for case in CASES}
    result = {}
    for case, forecasts in sealed.items():
        plan = enrol(case)
        clock_receipt = read(directory / f"{case}-clock.json")
        if forecasts["plan"] != plan or clock_receipt["exit"]:
            raise ValueError("Unexpected held forecast lineage or worker exit")
        digest = sha256((directory / case / "blind-forecast.json").read_bytes()).hexdigest()
        comparisons = None
        if forecasts["status"] == "paired_predictions_sealed":
            original = read(inputs(case)[3])
            if canonical_digest(original) != plan["original_detector_sha256"]:
                raise ValueError("Held signed measurements are from a different recording")
            rows = forecasts["held_predictions"]
            all_rows, _ = winning_observations(original)
            ids = {row["observation_id"] for row in rows}
            measured = {row["observation_id"]: row["measured_cfo_hz"] for row in all_rows if row["observation_id"] in ids}
            if measured.keys() != ids or not ids <= set(plan["held_ids"]):
                raise ValueError("The paired predictions do not cover the same sealed held rows")
            comparisons = paired_rf_scores(rows, measured)
        result[case] = dict(blind_sha256=digest, forecast=forecasts, process=clock_receipt, scores=comparisons)
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("run", "worker", "score"))
    cli.add_argument("directory", type=Path)
    cli.add_argument("case", nargs="?", choices=CASES)
    opts = cli.parse_args()
    if opts.mode == "run":
        run(opts.case, opts.directory)
    elif opts.mode == "worker":
        worker(opts.case, opts.directory)
    else:
        write(opts.directory / "result.json", score(opts.directory))
