"""Price a new exact derivative projection in the live named history refits."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import resource
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]
CONTRAST = Path("/dev/shm/leo-v3-nomination-handoff-0419-local01/result.json")
CONTRAST_PIN = "0e2bec8d6b8083976c9f0491dc65599d32a2c159e2a3d162eb3d9d4bc7dee7e9"
PRIOR = Path("/dev/shm/leo-v3-empty-predictive-0255-run02/scope.json")
PRIOR_PIN = "5e8fe1e75538d26e7862d7092167d56e4c0db0da45afaeaaab826246a91af5d5"
ORDER = {"c0": ("stock", "pair", "cache"), "fitted_c": ("cache", "pair", "stock")}


class Cut(BaseException):
    """The original bilateral gate completed, before signed work or publication."""


def study(policy, experiment, audit):
    import empty_bootstrap as boot
    from nomination_handoff import same

    operation = policy.history_policy
    original = policy.linear_refit

    def compare(scan, node, mask, powers, means, model, arm, entries):
        traces, records = {}, {}
        for mode in ORDER[arm]:
            with experiment.treatment(mode) as (counts, fingerprints):
                started = boot.now()
                records[mode] = original(scan, node, mask, powers, means, model, arm, entries)
                clocks = boot.clock(started)
            traces[mode] = dict(**clocks, counts=dict(counts), objective_digest=fingerprints.hexdigest())
        stock = records["stock"]
        for mode in ("pair", "cache"):
            traces[mode]["exact_record"] = same(stock, records[mode])
            traces[mode]["exact_objectives"] = traces[mode]["objective_digest"] == traces["stock"]["objective_digest"]
        audit["arms"][arm] = dict(treatments=traces, original_endpoint=stock["endpoint_east_north_km"],
                                  original_RF_RMS_Hz=stock["RMS_hz"], original_ELBO=stock["negative_twice_elbo"],
                                  active_points=stock["active_points"], original_gates=[
                                      row["compatible"] for row in stock["linear_gates"]])
        return stock

    def observed(*args, **kwargs):
        with patch.object(policy, "linear_refit", compare):
            result = operation(*args, **kwargs)
        audit["history"] = {field: result.get(field) for field in (
            "status", "linear_offered_tracks", "linear_offered_points", "linear_paired_valid", "fallback",
            "curved_gate_history")}
        raise Cut()

    return patch.object(policy, "history_policy", observed)


def sealed_scope(value):
    installed = value["jobs"]["installed"]
    pub = installed["publication"]["worker"]
    return dict(clock=installed["clock"], solve=pub["solve"], stage_design=pub["receipt"]["curved_design"],
                screen=pub["receipt"]["screened_nomination"])


def run(output):
    import empty_bootstrap as boot
    from clean_saved_publication import installed, load_job
    from dense_geographic_trial import host
    from empty_predictive_refit_trial import JOB_SHA
    from exact_named_route import checked_catalogue, resident_path
    from history_risk_weak_physical import deny_original
    from nomination_handoff_0255 import BASE, BASE_PIN, saved

    sys.addaudithook(deny_original)
    begin = boot.now()
    if output.exists() or resident_path(output.parent) != Path("/dev/shm"):
        raise ValueError("Use a fresh private tmpfs scope")
    output.mkdir(mode=0o700)
    runtime = boot.load_runtime()
    from aperture_trial import write
    from leo.analysis.localization_v3 import history_policy as policy
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from paired_secant_geometry import PairedProjection, binding, build

    usage_begin = resource.getrusage(resource.RUSAGE_CHILDREN)
    audit = dict(qualified=False, arms={}, sources={name: sha256((HERE/name).read_bytes()).hexdigest()
                 for name in (Path(__file__).name, "paired_secant_geometry.py", "paired_secant_geometry.c",
                              "paired-secant-geometry-protocol.md")})
    try:
        control = saved()
        if host() != control["admission"]["machine"] or control["admission"]["job_sha256"] != JOB_SHA:
            raise ValueError("Expected the same machine and previously sealed job")
        bound, request = load_job(BASE/"job.json", JOB_SHA)
        _, refs = checked_catalogue(bound, request, TleArchiveReader, canonical_digest)
        paths = [ref.path for ref in refs] + [Path(request[name]) for name in ("offer_file", "native_file")]
        residence = json.loads(subprocess.check_output(
            ["fincore", "--json", "--bytes", "-o", "RES,SIZE", *paths], text=True))["fincore"]
        if len(residence) != len(paths) or any(row["res"] < row["size"] for row in residence):
            raise ValueError("Require the complete saved scope resident at admission")
        previous = json.loads(boot.checked(resident_path(PRIOR), PRIOR_PIN))["calls"][0]
        contrast = json.loads(boot.checked(resident_path(CONTRAST), CONTRAST_PIN))
        audit["authority"] = dict(native=request["native_sha256"], offer=request["offer_sha256"],
                                  archive=request["local_archive"], cutoff=request["causal_cutoff_utc_ns"],
                                  job=JOB_SHA, stock=BASE_PIN, contrast=CONTRAST_PIN, prior=PRIOR_PIN,
                                  resident_bytes=sum(row["size"] for row in residence))
        audit["archived"] = {"DS30-0255": sealed_scope(control), "DS30-0419": sealed_scope(contrast)}
        audit["preflight"] = boot.clock(begin)
        library = output/"project.so"
        start = boot.now()
        start_child = resource.getrusage(resource.RUSAGE_CHILDREN)
        build(library)
        native = PairedProjection(library)
        end_child = resource.getrusage(resource.RUSAGE_CHILDREN)
        audit["setup"] = dict(**boot.clock(start), library_sha256=sha256(library.read_bytes()).hexdigest(),
                              build_child_cpu_s=(end_child.ru_utime + end_child.ru_stime
                                                 - start_child.ru_utime - start_child.ru_stime))
        start = boot.now()
        with (patch.object(boot, "load_runtime", return_value=runtime), binding(native) as experiment,
              study(policy, experiment, audit)):
            try:
                installed(bound, request, output/"candidate")
            except Cut:
                pass
            else:
                raise ValueError("The live original history decision was not reached")
        audit["slice"] = boot.clock(start)
        audit["upstream_optimizer"] = dict(experiment.samples["outside"])
        if (audit["history"]["status"] != "accepted" or set(audit["arms"]) != set(ORDER)
                or any(audit["history"][field] != previous[field] for field in (
                    "linear_offered_tracks", "linear_offered_points", "linear_paired_valid", "fallback", "curved_gate_history"))
                or any(row["original_endpoint"].tolist() != previous["linear"][arm]["endpoint"]
                       or row["original_RF_RMS_Hz"] != previous["linear"][arm]["rf_rms_hz"]
                       for arm, row in audit["arms"].items())):
            raise ValueError("Stock history slice differs from the sealed prior measurement")
        audit["qualified"] = all(value["treatments"][mode]["exact_record"] and value["treatments"][mode]["exact_objectives"]
                                 for value in audit["arms"].values() for mode in ("pair", "cache"))
        if not audit["qualified"]:
            raise ValueError("The candidate changed an exact objective or selected readout")
    except Exception as error:
        audit["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        children = resource.getrusage(resource.RUSAGE_CHILDREN)
        audit["witness_clock"] = boot.clock(begin)
        audit["child_cpu_s"] = (children.ru_utime + children.ru_stime - usage_begin.ru_utime - usage_begin.ru_stime)
        audit["kernel"] = dict(input_blocks=usage.ru_inblock, major_faults=usage.ru_majflt, max_rss_kib=usage.ru_maxrss)
        write(output/"scope.json", audit)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
