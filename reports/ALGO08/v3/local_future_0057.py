"""Run the sealed DS30-0057 saved-input transfer on a single low-priority core."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
CASES = HERE / "measurements/short-raw-diagnostic.json"
CASES_SHA = "7b12b73f5e104a56d9da7c47641c6014e8003bed54efc4e4174b8c08abd35e67"
ORDER = ("forward", "stock", "repair")


def inputs(arm):
    from aperture_trial import read
    from short_stereo_trial import single_packet

    if sha256(CASES.read_bytes()).hexdigest() != CASES_SHA:
        raise ValueError("Saved raw comparison differs from the frozen DS30-0057 witness")
    data = read(CASES)
    row, = [row for row in data["cases"] if row["case"] == "DS30-0057"]
    key = "stock" if arm == "stock" else "candidate"
    raw_run = row["runs"][key]
    pin = raw_run.get("retained_handoff", raw_run)["native_sha256"]
    root = Path(data["raw_receipt"]["path"]).parent / row["case"] / key
    libs = data["native_libraries"]
    return row, pin, single_packet(root), Path(libs["geographic"]["path"]), Path(libs["regional"]["path"])


def worker(arm, output):
    from aperture_trial import read
    from full_short_run import geographic_projection
    from joint_publication import run
    from local_future_repair_trial import worker as repaired
    from north_factor_swap import continued

    row, pin, saved, geo, regional = inputs(arm)
    recording, archive, region = map(Path, (row["recording"], row["archive"]["root"], row["region_file"]))
    if arm == "repair":
        return repaired(saved, pin, output, recording, archive, region, geo, regional)
    options = SimpleNamespace(saved=saved, saved_digest=pin, output=output, recording=recording,
                              archive=archive, region=region, verify_images=True, stock_control=arm == "stock",
                              optimized_full_catalogue=arm == "forward")
    if arm == "stock":
        return run(options)
    receiver = read(saved)["provenance"]["detector_sha256"][7:]
    run(options, saved_receiver=receiver, early_regional=True,
        geographic_projector=lambda: geographic_projection(geo, regional), reuse_cold_rows=True,
        reuse_grid_phase_states=True, prepare_native_projection=lambda prepare, native, *a, **kw:
            prepare(continued(native), *a, **kw))


def changes(before, after):
    def index(rows):
        by_id = {oid: (sat, role) for oid, sat, role in rows}
        if len(by_id) != len(rows):
            raise ValueError("An observation has ambiguous owner rows")
        return by_id

    old, new = index(before), index(after)
    return dict(before=len(old), after=len(new), added=len(new.keys() - old.keys()),
                lost=len(old.keys() - new.keys()), changed=sum(old[k] != new[k] for k in old.keys() & new.keys()))


def trial(root):
    from aperture_trial import RELEASE, read, write
    from dense_full_short_raw import usage
    from dense_geographic_trial import host
    from full_short_physical import environment

    settings = host()
    root.mkdir(exist_ok=False)
    env = environment(root)
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    for arm in ORDER:
        before, start = usage(), perf_counter()
        command = [python, "-BPs", __file__, "worker", str(root / arm), arm]
        run = subprocess.run(command, capture_output=True, text=True, env=env, timeout=90)
        elapsed, after = perf_counter()-start, usage()
        clock = dict(elapsed_s=elapsed, **{k: after[k]-before[k] for k in before},
                     status=run.returncode, stderr_tail=run.stderr[-2400:], machine=settings)
        write(root / f"{arm}-clock.json", clock)
        if run.returncode:
            raise RuntimeError(f"{arm} failed: {clock['stderr_tail']}")


def score(root):
    from aperture_trial import archive_identity, read
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from mixture_score import section
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    if sha256(REFERENCE.read_bytes()).hexdigest() != REFERENCE_SHA256:
        raise ValueError("Unrecognized reference roster")
    ref, = [r for r in read(REFERENCE)["cases"] if r["dataset_label"] == "DS30-0057"
            and r["authority_eligible"] and r["sealed_metadata_digests_verified"]]
    truth = [ref["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    results, owners = {}, {}
    for arm in ORDER:
        row, pin, _, _, _ = inputs(arm)
        folder = root / arm
        trial = read(folder / "joint-research-receipt.json")
        receipt = trial["receipt"]
        terminal = read(folder / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json")
        evidence = artifacts(folder, receipt)
        if (trial["saved_digest"] != pin or terminal["native_sha256"] != pin or terminal["region"] != row["region"]
                or canonical_digest(terminal) != receipt["terminal_sha256"] or row["archive"] != archive_identity(Path(row["archive"]["root"]))
                or canonical_digest(evidence) != canonical_digest(trial["evidence"])):
            raise ValueError("Native input, terminal, publication, supplied region or causal archive changed")
        if receipt["decision"] == "complete" and not trial["solve"]["grid_complete"]:
            raise ValueError("Incomplete published grid")
        archive = row["archived_stock_publication"]
        if arm == "stock" and (receipt["terminal_sha256"] != row["runs"]["stock"]["retained_handoff"]["terminal_sha256"]
                or canonical_digest(evidence["images"]) != canonical_digest(archive["pngs"])):
            raise ValueError("Installed control differs from the verified raw witness")
        owners[arm] = trial["selected_rows"]
        result = section(terminal["arms"], truth, archive["arms"])
        results[arm] = dict(decision=receipt["decision"], terminal_sha256=receipt["terminal_sha256"], native_sha256=pin,
                            score=result, solve=trial["solve"], process=read(root / f"{arm}-clock.json"),
                            evidence=evidence, route=trial["route"], publication_cpu_s=trial["publication_cpu_s"],
                            repair=(trial["route_details"] or {}).get("local_future_repair"),
                            screen_passed=receipt["decision"] == "complete" and all(
                                a["delta_error_km"] <= .25 for a in result["arms"].values()))
    difference = {k: changes(owners["forward"].get(k, []), owners["repair"].get(k, [])) for k in ("c0", "fitted_c")}
    return dict(case=row["case"], roster_sha256=CASES_SHA, order=ORDER, runs=results, owner_changes=difference,
                driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                policy=read(root / "repair/local-future-policy.json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("trial", "worker", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("arm", nargs="?", choices=ORDER)
    args = parser.parse_args()
    if args.mode == "worker":
        worker(args.arm, args.root)
    elif args.mode == "trial":
        trial(args.root)
    else:
        json.dump(score(args.root), sys.stdout, sort_keys=True, allow_nan=False, indent=2)
