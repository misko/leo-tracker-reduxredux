"""Inspect the installed DS30-0255 history stage on its original staged inputs."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import resource
import subprocess
import sys


HERE = Path(__file__).resolve().parent
JOB_SHA = "867b8b84d56e9fb11ea8650dda731d58583fe963d1ea765a44a1336fe475575d"
ACCEPTING = Path("/dev/shm/leo-v3-history-risk-0169-01/risk-route.json")
ACCEPTING_SHA = "6922f4bb992a339fae2bc532c69618d41243dbc24e6e3ddf8952410805421b30"


def run(output):
    from clean_saved_publication import installed, load_job
    from dense_geographic_trial import host
    from empty_bootstrap import checked, clock, load_runtime, now
    from exact_named_route import checked_catalogue, resident_path
    from history_risk_weak_physical import deny_original
    from nomination_handoff_0255 import BASE, BASE_PIN, saved

    sys.addaudithook(deny_original)
    begin = now()
    if resident_path(output.parent) != Path("/dev/shm") or output.exists():
        raise ValueError("Use a fresh private witness in tmpfs")
    output.mkdir(mode=0o700)
    _, _, _, _, source_check = load_runtime()
    from aperture_trial import write
    from empty_predictive_refit import HistoryComplete, measured_history
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    audit = dict(calls=[], sources={}, qualified=False, runtime_source_check=source_check)
    audit["implementation"] = {name: sha256((HERE/name).read_bytes()).hexdigest() for name in (
        Path(__file__).name, "empty_predictive_refit.py", "empty-predictive-refit-0255-protocol.md")}
    try:
        original = saved()
        machine = host()
        if machine != original["admission"]["machine"] or original["admission"]["job_sha256"] != JOB_SHA:
            raise ValueError("Use the original single-core timing controls and saved input")
        bound, req = load_job(BASE / "job.json", JOB_SHA)
        _, refs = checked_catalogue(bound, req, TleArchiveReader, canonical_digest)
        paths = [ref.path for ref in refs] + [Path(req[name]) for name in ("offer_file", "native_file")]
        residence = json.loads(subprocess.check_output(
            ["fincore", "--json", "--bytes", "-o", "RES,SIZE", *paths], text=True))["fincore"]
        if len(residence) != len(paths) or any(row["res"] < row["size"] for row in residence):
            raise ValueError("The staged catalogue, native detector or offer no longer fit the resident scope")
        stock = original["jobs"]["installed"]
        families = {arm: dict(Counter(row[2] for row in values))
                    for arm, values in stock["publication"]["selected_rows"].items()}
        accepting = json.loads(checked(resident_path(ACCEPTING), ACCEPTING_SHA))
        useful = accepting["solves"][0]["lean_final_fit"]["arms"]
        audit["binding"] = dict(original=BASE_PIN, job=JOB_SHA, native=req["native_sha256"],
                                offer=req["offer_sha256"], archive=req["local_archive"],
                                cutoff=req["causal_cutoff_utc_ns"], machine=machine,
                                resident_bytes=sum(row["size"] for row in residence))
        audit["stock"] = dict(clock=stock["clock"], solve=stock["publication"]["worker"]["solve"],
                              roles_by_arm=families, owners_source=BASE_PIN)
        audit["accepting_control"] = dict(case="DS30-0169", pin=ACCEPTING_SHA,
                                         predictive_by_arm={arm: dict(tracks=len(record["predictive"]), rows=sum(
                                             len(row["ids"]) for row in record["predictive"].values()))
                                             for arm, record in useful.items()})
        audit["preflight"] = clock(begin)
        start = now()
        with measured_history(audit):
            try:
                installed(bound, req, output/"candidate")
            except HistoryComplete as done:
                policy = done.result
            else:
                raise ValueError("Did not reach the installed readout after history policy")
        audit["slice"] = clock(start)
        audit["policy_status"] = policy["status"]
        audit["qualified"] = len(audit["calls"]) == 1 and audit["calls"][0]["compatible"]
        if not audit["qualified"]:
            raise ValueError("The original history fit was not measured")
    except Exception as error:
        audit["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        use = resource.getrusage(resource.RUSAGE_SELF)
        audit["through_witness"] = clock(begin)
        audit["rusage"] = dict(input_blocks=use.ru_inblock, major_faults=use.ru_majflt,
                               output_blocks=use.ru_oublock, max_rss_kib=use.ru_maxrss)
        write(output/"scope.json", audit)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
