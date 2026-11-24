"""Measure one saved charted publication on the exact installed field detector packet."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
from time import perf_counter, process_time, time_ns
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CHARTED = Path("/tmp/leo-v3-integrated-original-batch")
PANEL = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
CASES = {
    "DS30-0220": (Path("/dev/shm/leo-v3-three-quarter-0220-stage01"),
                  "d307ff5f4a02fe144eb1547574728a46bf19b4365d971687c471adea65aa4755"),
    "DS30-0086": (Path("/dev/shm/leo-v3-cfo-epoch-0086-saved01"),
                  "407765fa47754cc99556143888b286e88f4674ab21836d3f437ac8af4c2ca439"),
}
ARMS = ("c0", "fitted_c")
BUILD_PIN = "30cc3b044040f2519677d67abfde731f83693612744d2236d1ba71bb5a31e4ab"
BOUND_PIN = "4c6e5a2c9243f8b30b639d183360ca849d8c0c407ba546f74fef3af0a3253540"
REFERENCE_PIN = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"


def digest(body):
    return "sha256:" + sha256(body).hexdigest()


def check(path, pin):
    body = path.read_bytes()
    if digest(body) != "sha256:" + pin.removeprefix("sha256:"):
        raise ValueError(f"Permanently enrolled input changed: {path.name}")
    return body


def read(path, pin=None):
    return json.loads(path.read_bytes() if pin is None else check(path, pin))


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")


def deny_backing(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = Path(os.path.abspath(os.fsdecode(args[0])))
        if path.name.endswith(".ci16.zst") or path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01"):
            raise ValueError(f"Saved-only port cannot open a backing or waveform file: {path}")


def enroll(case):
    stage, pair_pin = CASES[case]
    original = PANEL / "cases" / case
    pair = read(original / "pair.json", pair_pin)
    if not pair["verified_pair"] or not pair["chronological"] or pair["generation"] != 1:
        raise ValueError("Only the frozen verified original may enter the saved port")
    attempt = original / "installed/attempt-000001"
    reference = read(attempt / "result.json", pair["attempt_result_sha256"]["installed"])
    authority = read(stage / "authority.json", pair["authority_sha256"])
    inventory = read(stage / "inventory.json", authority["inventory_sha256"])
    check(stage / "offer.json", authority["region_sha256"])
    if reference["raw_identity"] != authority or reference["outcome"] not in ("complete", "withheld"):
        raise ValueError("Installed original publication must identify this detached request")
    publication = attempt / "publication"
    (native_path,) = publication.glob("fast-scan-automatic-work/*/detections.json")
    native = read(native_path, reference["native_sha256"])
    check(publication / "fast-scan-inputs" / (authority["session_id"] + ".json"), authority["inventory_sha256"])
    return stage, pair, reference, authority, inventory, native


def worker(case, root):
    began, cpu = perf_counter(), process_time()
    sys.addaudithook(deny_backing)
    sys.path[:0] = [str(CHARTED / "reports/ALGO08/v3"), str(CHARTED), str(HERE), str(ROOT)]
    import empty_bootstrap as boot
    import integrated_original_batch as batch

    with patch.object(sys, "path", list(sys.path)):
        from ds30_0049_saved_crossover import charted
    from legacy_first_map_acceleration import checked_artifacts

    book, _, producer_cutoff = batch.load_build(PANEL / "frozen-build/build.json", BUILD_PIN)
    _, spec, sources, publication, _ = boot.load_runtime()
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_scan import FastSegmentSource
    from leo.storage.short_window import ShortWindowReader
    from unified_short_bootstrap import Handoff
    from visit_frame_raw_0016 import resident

    stage, pair, named, authority, inventory, native = enroll(case)
    recording, archive, offer = Path(authority["recording"]), stage / "tle", stage / "offer.json"
    batch.validate_case(authority, SimpleNamespace(recording=recording, region=offer))
    session, inventory_pin = authority["session_id"], authority["inventory_sha256"]
    batch.match_inventory(authority, session, inventory_pin, inventory)
    batch.match_native(authority, native)
    boot.bind_native(native, session, inventory_pin, spec["detector_sha256"], expected=named["native_sha256"])
    cutoff = authority["causal_cutoff_utc_ns"]
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    paths = [ref.path for ref in refs]
    if (len(paths) != 50 or not archive.is_relative_to("/dev/shm")
            or any(path.resolve(strict=True) != path or not path.is_relative_to(archive) for path in paths)
            or producer_cutoff >= cutoff or batch.archive_digest(archive, cutoff) != authority["archive_sha256"]):
        raise ValueError("Expected the same exact local causal archive and earlier verified portable producer")
    resident_before = resident(paths)
    portable, fast = (book["native"]["--" + flag] for flag in ("portable-orbit-index", "legacy-first-map-fast"))
    acceleration = checked_artifacts(Path(fast["path"]), fast["sha256"])
    output = root / "candidate"
    args = SimpleNamespace(recording=recording, archive=archive, region=offer, output=output,
                           archive_sha256=authority["archive_sha256"], history_risk_route=True,
                           portable_orbit_index=Path(portable["path"]), portable_orbit_index_sha256=batch.tagged(portable["sha256"]),
                           portable_orbit_producer_sha256=batch.tagged(book["portable_producer"]["sha256"])[7:],
                           cairo_six_sheets=True, cairo_residual_layout=False)
    handoff = Handoff(session, inventory_pin, spec["detector_sha256"], native)

    def refuse(*args, **kwargs):
        raise ValueError("Saved evaluation attempted raw windows")

    write(root / "admission.json", dict(case=case, raw_authority=authority, build_sha256=BUILD_PIN,
          authority_sha256=pair["authority_sha256"], installed_result_sha256=pair["attempt_result_sha256"]["installed"],
          native_sha256=named["native_sha256"], archive_count=len(paths), cache_before=resident_before,
          crossover_helper_sha256=digest((HERE / "ds30_0049_saved_crossover.py").read_bytes())))
    preamble = dict(cpu_s=process_time()-cpu, elapsed_s=perf_counter()-began)
    with patch.object(FastSegmentSource, "windows", refuse), patch.object(ShortWindowReader, "windows", refuse):
        receipt, owners, audit = charted(publication, spec, sources, args, handoff, authority, inventory, acceleration)
    (written_native,) = output.glob("fast-scan-automatic-work/*/detections.json")
    check(written_native, named["native_sha256"])
    check(output / "fast-scan-inputs" / (session + ".json"), inventory_pin)
    if handoff.calls != 1 or resident(paths) != resident_before or receipt["region"] != named["evidence"]["receipt"]["region"]:
        raise ValueError("Packet, original offer or cache diverged")
    write(output / "crossover-worker.json", dict(receipt=receipt, ordered_owners=owners, audit=audit,
          verified_handoffs=handoff.calls, waveform_reads=0, preamble=preamble,
          total_before_receipt=dict(cpu_s=process_time()-cpu, elapsed_s=perf_counter()-began)))


def quality(installed, candidate, distance_km, site):
    same = installed["decision"] == candidate["decision"]
    deltas, errors, rf, exact = {}, {}, {}, {}
    for arm in ARMS:
        old, new = (doc["arms"][arm] for doc in (installed, candidate))
        errors[arm] = [distance_km(site, arm_row["latlon"]) if arm_row["latlon"] is not None else None for arm_row in (old, new)]
        rf[arm] = [old["rf_rms_hz"], new["rf_rms_hz"]]
        if all(x is not None for x in errors[arm]):
            deltas[arm] = 1000 * (errors[arm][1]-errors[arm][0])
        exact[arm] = old == new
    if installed["decision"] == "complete":
        passed = same and set(deltas) == set(ARMS) and max(deltas.values()) <= 250.0
    else:
        passed = same and all(errors[arm] == [None, None] for arm in ARMS)
    return dict(qualified=passed, same_decision=same, error_delta_m=deltas, errors_km=errors, rf_rms_hz=rf, exact_arms=exact)


def launch(case, root, advance):
    if case == "DS30-0086":
        previous = read(advance / "score.json") if advance is not None else {}
        if previous.get("case") != "DS30-0220" or previous.get("qualification", {}).get("qualified") is not True:
            raise ValueError("The next prespecified case requires a sealed passing 0220 result")
    if os.sched_getaffinity(0) != {2} or os.nice(0) < 15 or not root.resolve().is_relative_to("/tmp"):
        raise ValueError("Require one natural low-priority CPU2 lease and a fresh local tmpfs result path")
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts"):
        (root / name).mkdir()
    command = [sys.executable, "-IB", str(Path(__file__).resolve()), "worker", case, str(root)]
    env = os.environ | {"TMPDIR": str(root / "tmp"), "MPLCONFIGDIR": str(root / "fonts")}
    before, clock, started_ns = resource.getrusage(resource.RUSAGE_CHILDREN), perf_counter(), time_ns()
    with (root / "stdout.log").open("x") as stdout, (root / "stderr.log").open("x") as stderr:
        done = subprocess.run(command, env=env, stdout=stdout, stderr=stderr, timeout=100, check=False)
    after, elapsed = resource.getrusage(resource.RUSAGE_CHILDREN), perf_counter()-clock
    user, system = after.ru_utime-before.ru_utime, after.ru_stime-before.ru_stime
    write(root / "process.json", dict(case=case, command=command, started_unix_ns=started_ns, elapsed_s=elapsed,
          cpu_s=user+system, user_s=user, system_s=system, max_rss_kib=after.ru_maxrss,
          input_blocks=after.ru_inblock-before.ru_inblock, major_faults=after.ru_majflt-before.ru_majflt,
          minor_faults=after.ru_minflt-before.ru_minflt, exit_code=done.returncode))
    if done.returncode:
        raise RuntimeError((root / "stderr.log").read_text()[-3000:])


def timer_model(installed_s, publication_wall_s, ingestion_cpu_s, projected_native_s):
    remaining = installed_s/2 - publication_wall_s - ingestion_cpu_s
    need = max(0.0, projected_native_s - remaining)
    return dict(required_native_before_2x_s=remaining, projected_full_native_s=projected_native_s,
                required_native_reduction_s=need, required_native_reduction_fraction=need/projected_native_s)


def score(case, root):
    sys.path[:0] = [str(ROOT / "src"), str(ROOT), str(HERE)]
    from ds30_0049_saved_crossover_score import publication
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.scoring import distance_km

    started, cpu = perf_counter(), process_time()
    _, _, named, authority, _, _ = enroll(case)
    bounds, = [r for r in read(HERE / "measurements/installed-receiver-field-budget.json", BOUND_PIN)["cases"] if r["case"] == case]
    admission, process = (read(root / (name + ".json")) for name in ("admission", "process"))
    installed = dict(named["evidence"]["receipt"], arms=named["evidence"]["arms"])
    output = root / "candidate"
    observed = publication(output, named)
    worker_receipt = read(output / "crossover-worker.json")
    if (process["exit_code"] or admission["native_sha256"] != named["native_sha256"]
            or admission["raw_authority"] != authority or observed["receipt"]["region"] != installed["region"]
            or bounds["installed_result_sha256"] != admission["installed_result_sha256"]):
        raise ValueError("Fresh saved output differs from the enrolled original comparator")
    anchor, = [r["reference"] for r in read(ROOT / "reports/2026_11_21_ds30_full/reference-audit.json", REFERENCE_PIN)["cases"]
               if r["dataset_label"] == case and r["authority_eligible"] and r["sealed_metadata_digests_verified"]]
    site = [anchor[k] for k in ("latitude_deg", "longitude_deg")]
    # The prediction terminal uses "ok" while the public disposition is "complete".
    candidate_status = observed["receipt"]["decision"]
    scientific = quality(installed, dict(observed["terminal"], decision=candidate_status), distance_km, site)
    ports = worker_receipt["audit"]
    inner = read(output / "exact-named-raw-witness.json")["timing"] if candidate_status == "complete" else {}
    pub = ports["saved_scientific_elapsed_s"]
    ingress_low = bounds["optimistic_ingress_remainder_s"]
    ingress_kept = (bounds["measured_mixed_acquisition"]["cpu_s"] - sum(bounds["measured_mixed_native_process_cpu_s"].values()))
    estimate = bounds["modeled_stock_native_s"]
    model = {label: timer_model(bounds["installed_s"], pub, time, estimate) | {"ingress_cpu_s": time}
             for label, time in (("free_ingress", 0), ("free_prefetch_and_wait", ingress_low),
                                 ("observed_other_acquisition_cpu", ingress_kept))}
    (native_path,) = output.glob("fast-scan-automatic-work/*/detections.json")
    terminal = output / "fast-scan-automatic-work" / observed["receipt"]["run_id"] / "terminal.json"
    file_boundaries = {key: (path.stat().st_mtime_ns - process["started_unix_ns"])/1e9
                       for key, path in (("native_file_s", native_path), ("terminal_file_s", terminal))}
    if not 0 < file_boundaries["native_file_s"] <= file_boundaries["terminal_file_s"] <= process["elapsed_s"]:
        raise ValueError("Saved publication file timings are outside the charged child")
    sidecars = {key: canonical_digest({k: v for k, v in observed[key].items() if k not in ("binding", "elapsed_seconds")})
                for key in ("grid", "path") if observed[key] is not None}
    named_figures = {row["name"]: (row["sha256"], "sha256:" + row["rgba_sha256"].removeprefix("sha256:")) for row in named["figures"]}
    verification = dict(cpu_s=process_time()-cpu, elapsed_s=perf_counter()-started)
    write(root / "score.json", dict(case=case, qualification=scientific, process=process, validation=verification,
          measured_preamble=worker_receipt["preamble"], measured_saved_publication=ports, inner=inner,
          named_raw_s=bounds["installed_s"], named_raw_process=named["process"], required_native_model=model,
          exact_owner_map={arm: observed["owners"].get(arm) == named["evidence"]["owners"].get(arm) for arm in ARMS},
          installed_ordered_rows_available=False, observed_owners={arm: len(rows) for arm, rows in observed["owner_rows"].items()},
          terminal_exact=observed["receipt"]["terminal_sha256"] == installed["terminal_sha256"],
          exact_positions={arm: observed["terminal"]["arms"][arm]["latlon"] == installed["arms"][arm]["latlon"] for arm in ARMS},
          exact_rf={arm: observed["terminal"]["arms"][arm]["rf_rms_hz"] == installed["arms"][arm]["rf_rms_hz"] for arm in ARMS},
          exact_numeric_sidecars={key: value == named["evidence"]["scientific_digests"][key] for key, value in sidecars.items()},
          exact_pngs={name: dict(encoded=record[0] == named_figures[name][0], pixels=record[1] == named_figures[name][1])
                      for name, record in observed["figures"].items()}, file_boundaries=file_boundaries,
          native_sha256=named["native_sha256"], installed_result_sha256=admission["installed_result_sha256"],
          candidate_grid_points=observed["grid"]["evaluated_points"] if observed["grid"] is not None else 0,
          candidate_pngs=observed["figures"], waveform_reads=0))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("launch", "worker", "score"))
    p.add_argument("case", choices=tuple(CASES))
    p.add_argument("root", type=Path)
    p.add_argument("--advance-from", type=Path)
    a = p.parse_args()
    if a.action == "launch":
        launch(a.case, a.root, a.advance_from)
    elif a.action == "worker":
        worker(a.case, a.root)
    else:
        score(a.case, a.root)
