"""Compare authentic first-member aperture substitutions on one released physical packet."""

from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
STAGED = Path("/dev/shm/leo-receiver-ceiling-0169-results01")
FULL = Path("/dev/shm/leo-v3-family-endpoint-0169-results-01")
SOLVER = Path("/dev/shm/leo-v3-family-endpoint-transfer/reports/ALGO08/v3")
EIGHT = Path("/var/tmp/leo-v3-eight-ms-build-padded/8ms/short-primary.so")
EIGHT_SHA = "fe4ba7b7613654c268353f9e4a78c2bbb916904e06387ace304b0866818f0e3d"
VISITS = 64
ORDER = ("mixed12", "mixed8")
SCOPED_AUTHORITY = "sha256:089f67081dd421f5965c1fcf90bd7f7730c5edcdae20fc903c2c91600f72d309"
PINS = {
    STAGED / "scope.json": "95a438f0904e4568b6f2a3618b7fbf691c29d0e2d352fd3727cc83d35b72aa9a",
    STAGED / "1-stock.json": "b1d8a32033373c5996217fe3a70e9e7fe5ae58ba3f75439052eacd2ff55cb453",
    STAGED / "1-full-short.json": "2f9102ffead53766ccc71317243618ff415de7c537cd4bb81b7b8b57488eea13",
    STAGED / "2-full-short.json": "21f4e036e50a92fcfb32245590b6c76e0ed51b1514e0fd3c3ee101dcf3442f08",
    FULL / "request.json": "b8b16a93ef61b8c7daaa5ef327d005e53281972f1c1e72cb0e9bb15a3d09c3c8",
    FULL / "named-detections.json": "b185302560a9981a5624613ce39d358817c7a21edbb6778168e3d5dd3c8a5ffc",
    FULL / "inventory.json": "be9e6e39a10a89a298054d08ea51db53b5aec7667ecf9a725373582ac092972d",
    FULL / "operator-offer.json": "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236",
    SOLVER / "family_endpoint_transfer.py": "729bbae13c067741b629113b08a62e379161971121cd9e0af7a0c316c1bbe3d8",
    SOLVER / "prospective_0316_solver.py": "73e3fb562115933bd5f6fb28d7a3e281c11c8f11c834a45d4b1c0914c33a280c",
    Path("/dev/shm/leo-v3-family-endpoint-0169-final.json"): "005bfd26a0e7e7da2288f214781f7261f75f9a301760d97dd2db01c198c989bf",
}


def read(path, *, expected=None):
    data = path.read_bytes()
    pin = expected if expected is not None else PINS[path]
    if sha256(data).hexdigest() != pin:
        raise ValueError(f"A frozen source changed: {path}")
    return json.loads(data)


def prefix_rows(packet):
    return [row for row in packet["source"]["probes"] if row["visit_index"] < VISITS]


def opportunities(probes):
    return [dict(row, candidates=[]) for row in probes]


def verify_scope(full, stock, a):
    source, template = full["source"], stock["packet"]
    prefix = prefix_rows(full)
    if prefix != template["source"]["probes"]:
        raise ValueError("The named bounded replay does not reproduce the released prefix")
    member = a["packet"]
    if (opportunities(prefix) != opportunities(member["source"]["probes"])
            or a["iq"] != stock["iq"] or len(a["iq"]) != VISITS
            or member["source"]["session_id"] != source["session_id"]
            or member["source"]["input_manifest_sha256"] != source["input_manifest_sha256"]
            or member["source"]["raw_recording_authority_digest"] != SCOPED_AUTHORITY
            or member["clock_anchor"] != full["clock_anchor"] or member["delivery_clocks"] != full["delivery_clocks"][:VISITS]
            or member["provenance"]["excluded_windows"] != [row for row in full["provenance"]["excluded_windows"]
                                                             if row["visit"] < VISITS]):
        raise ValueError("Member opportunities, excluded slots or capture authorities disagree")
    if (member["provenance"]["window_count"], member["provenance"]["processed_windows"],
            member["provenance"]["invalid_capture"]) != (64, 51, 13):
        raise ValueError("The bounded member no longer has its signed original roster")


def verify_apertures(a, b):
    from leo.contracts.digests import canonical_digest

    modes = {"full": 16, "short_primary": 86}
    if any(job["native_schedule"]["native_calls"] != modes for job in (a, b)):
        raise ValueError("The opportunity streams disagree on the originated anchor schedule")
    left, right = (job["packet"]["source"]["probes"] for job in (a, b))
    for before, after, x, y in zip(left, right, a["trace"], b["trace"], strict=True):
        if x["mode"] != y["mode"] or (x["visit"], x["lane"]) != (y["visit"], y["lane"]):
            raise ValueError("The two measurements are not from the same stereo schedule")
        if x["mode"] == "full" and (before != after or canonical_digest(x["factors"]) != canonical_digest(y["factors"])):
            raise ValueError("A full two-scan anchor changed")
        if x["mode"] == "short_primary" and any(len(row["candidates"]) > 1 or any(
                candidate["candidate_rank"] != 0 or candidate["passed_fractional_margin_gate"] is not True
                for candidate in row["candidates"]) for row in (before, after)):
            raise ValueError("A short lane does not carry its original verified primary factor")


def substitution(full, measured):
    data = full["source"]["probes"]
    replacement = measured["source"]["probes"]
    prefix = prefix_rows(full)
    if prefix != data[:len(prefix)] or opportunities(prefix) != opportunities(replacement):
        raise ValueError("Substitution changes opportunities or chronology")
    return [*replacement, *data[len(replacement):]]


def residency(scope):
    segment = Path(scope["entry"]["path"])
    if segment.resolve(strict=True) != segment or not segment.is_relative_to(STAGED) or (
            segment.stat().st_dev != Path("/dev/shm").stat().st_dev):
        raise ValueError("Only the assigned resident tmpfs member may be opened")
    chunk = scope["member"]
    names = ("manifest.json", chunk["index_relative_path"], chunk["payload_relative_path"])
    rows = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,PAGES,SIZE,FILE",
                                              *(segment / name for name in names)]))["fincore"]
    if len(rows) != 3 or any(row["res"] < row["size"] for row in rows):
        raise ValueError("The three signed files must be fully resident before acquisition")
    return rows


def prepare(root):
    from continued_cfo_trial import rebinding
    from full_short_run import checked_recipe
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import immutable_json
    from reports.ALGO08.v3 import receiver_ceiling_0169 as original

    scope = read(STAGED / "scope.json")
    request = read(FULL / "request.json")
    full, stock, a, repeat = map(read, (FULL / "named-detections.json", STAGED / "1-stock.json",
                                       STAGED / "1-full-short.json", STAGED / "2-full-short.json"))
    verify_scope(full, stock, a)
    if a["packet"] != repeat["packet"] or a["iq"] != repeat["iq"]:
        raise ValueError("Archived measured 12 ms repeats disagree")
    if Path(request["local_archive"]["root"]).resolve(strict=True) != FULL / "tle":
        raise ValueError("The solver requires the original local-only verified archive view")
    before = residency(scope)
    # The existing measurement worker verifies both compressed and decoded bytes.
    # Switch only the pinned short binary and the recipe recording its identity.
    recipe8 = checked_recipe(eight_ms=True)
    with (patch.object(original, "ORIGINAL", EIGHT.parent), patch.object(original, "SHORT_SHA", EIGHT_SHA),
          patch.object(original, "recipe", lambda _detector: recipe8)):
        b = original.acquire(STAGED, "full-short")
    after = residency(scope)
    immutable_json(root / "measured8.json", b)
    verify_scope(full, stock, b)
    verify_apertures(a, b)
    if b["packet"]["provenance"]["detector_sha256"] != canonical_digest(recipe8):
        raise ValueError("The fresh native member lost its truthful aperture provenance")
    background = full["source"]["probes"][len(prefix_rows(full)):]
    results = {}
    for mode, measured in zip(ORDER, (a, b), strict=True):
        member = measured["packet"]
        probes = substitution(full, member)
        spec = dict(kind="saved first-member aperture intervention", issued_visits=[0, VISITS],
                    native_member_sha256=canonical_digest(member), member_detector=member["provenance"]["detector_sha256"],
                    full_background_sha256="sha256:" + PINS[FULL / "named-detections.json"],
                    short_aperture_ms=int(mode.removeprefix("mixed")), original_suffix_sha256=canonical_digest(background),
                    suffix="original released chronological continuation", held_eof_replay=False)
        native = rebinding(full, probes, spec)
        path = root / f"{mode}-detections.json"
        immutable_json(path, native)
        digest = canonical_digest(native)
        if digest != "sha256:"+sha256(path.read_bytes()).hexdigest() or probes[len(prefix_rows(full)):] != background:
            raise ValueError("Derived scientific packet changed outside the one staged member")
        job = dict(request, native_file=str(path), native_sha256=digest[7:], detector=canonical_digest(spec)[7:], label=mode)
        immutable_json(root / f"{mode}-request.json", job)
        results[mode] = dict(recipe=spec, native_sha256=digest, packet=str(path), member_job=mode,
                             member_selected=sum(len(row["candidates"]) for row in member["source"]["probes"]),
                             member_acquire_cpu_ns=measured["acquire_cpu_ns"], member_acquire_wall_ns=measured["acquire_wall_ns"],
                             native_schedule=measured["native_schedule"])
    immutable_json(root / "plan.json", dict(inputs={str(path): pin for path, pin in PINS.items()}, order=ORDER,
                   member_8_sha256=canonical_digest(b), member_scope=SCOPED_AUTHORITY,
                   source_pages=dict(before=before, after=after), complete_opportunity_rows=7054, capped_visits=VISITS,
                   background_issued=4155, scope="first-member only", arms=results))


def worker(root, mode):
    from empty_bootstrap import checked

    for name in ("family_endpoint_transfer.py", "prospective_0316_solver.py"):
        checked(SOLVER / name, PINS[SOLVER / name])
    import family_endpoint_transfer as reference

    job = root / f"{mode}-request.json"
    req = json.loads(job.read_bytes())
    plan = json.loads((root / "plan.json").read_bytes())["arms"][mode]
    if req["label"] != mode or req["native_sha256"] != plan["native_sha256"][7:] or req["inventory"] != (
            "sha256:" + PINS[FULL / "inventory.json"]):
        raise ValueError("Expected the sealed intervention and original complete inventory")
    description = f"DS30-0169 {mode} first-member only with unchanged released 20 ms suffix"
    with patch.object(reference, "worker", partial(reference.worker, detector=req["detector"], input_description=description)):
        reference.invoke(job, "combined", root / mode)


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    if root.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Use a new tmpfs output for this one scoped case")
    machine = host()
    root.mkdir()
    (root / "tmp").mkdir()
    (root / "fonts").mkdir()
    for item in (FULL / "fonts").glob("fontlist-*.json"):
        (root / "fonts" / item.name).hardlink_to(item)
    (root / "inventory.json").hardlink_to(FULL / "inventory.json")
    env = environment(root) | {"TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "tmp")}
    runtime = RELEASE / "venv/bin/python"
    checkout = HERE.parents[2]
    # Matches the prefix acquisition's checked origins. The solver uses -I
    # and reinstalls its own pinned publication package before reading science.
    env["PYTHONPATH"] = f"{HERE}:{RELEASE}/src:{checkout}:{checkout}/src:{RELEASE}"
    native = ["/usr/bin/timeout", "--kill-after=2s", "20s", runtime, "-BPs", __file__, "prepare", root]
    prep = measure(native, env, root / "member")
    write(root / "member-clock.json", dict(timing=prep, command=list(map(str, native)), machine=machine))
    if prep["exit_code"]:
        raise ValueError(f"No saved solve admitted after the authentic member preflight: {prep['stderr_tail']}")
    for mode in ORDER:
        cmd = ["/usr/bin/timeout", "--kill-after=2s", "40s", runtime, "-IB", __file__, "worker", root, mode]
        clock = measure(cmd, env, root / mode)
        write(root / f"{mode}-clock.json", dict(timing=clock, command=list(map(str, cmd))))


def score(root):
    from aperture_trial import write
    from empty_bootstrap import checked
    from family_endpoint_transfer import settings
    from leo.contracts.digests import canonical_digest
    from prospective_0316_solver import inspect, owner_delta
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    plan = json.loads((root / "plan.json").read_bytes())
    historical = read(Path("/dev/shm/leo-v3-family-endpoint-0169-final.json"))
    refs = json.loads(checked(REFERENCE, REFERENCE_SHA256))["cases"]
    (ref,) = [r["reference"] for r in refs if r["dataset_label"] == "DS30-0169"
              and r["authority_eligible"] and r["sealed_metadata_digests_verified"]]
    truth = [ref[key] for key in ("latitude_deg", "longitude_deg")]
    captures, rows = {}, {}
    for mode in ORDER:
        path = root / mode
        clock = json.loads((root / f"{mode}-clock.json").read_bytes())["timing"]
        if clock["exit_code"]:
            captures[mode] = dict(process=clock, decision="worker_failed")
            continue
        req = json.loads((root / f"{mode}-request.json").read_bytes())
        audit = json.loads((path / settings(req)["audit_name"]).read_bytes())
        description = f"DS30-0169 {mode} first-member only with unchanged released 20 ms suffix"
        found = inspect(path, mode, audit["receipt"], clock, req, **settings(req), detector=req["detector"],
                        input_description=description)
        if found["terminal"]["region"] != req["offer"]:
            raise ValueError("The original matched containing offer changed")
        rows[mode] = found.pop("selected_rows")
        scores = {arm: dict(horizontal_error_km=distance_km(truth, row["latlon"]) if row["latlon"] else None,
                             rf_rms_hz=row["rf_rms_hz"]) for arm, row in found["terminal"]["arms"].items()}
        witness = json.loads((path / "bound-package.json").read_bytes())
        captures[mode] = dict(found, scores=scores, entered_original_final_fit=witness["entered_fixed_final_fit"],
                              owners_sha256=canonical_digest(rows[mode]))
    differences = {} if len(rows) != 2 else {arm: owner_delta(*(rows[m].get(arm, []) for m in ORDER))
                                            for arm in ("c0", "fitted_c")}
    fig_a, fig_b = (captures[m].get("figures", {}) for m in ORDER)
    figure_parity = {name: canonical_digest(left) == canonical_digest(fig_b[name]) for name, left in fig_a.items()
                     if name in fig_b}
    write(root / "result.json", dict(case="DS30-0169", plan=plan, runs=captures, owner_change=differences,
                                    figures_equal=figure_parity, named_20ms_context=historical["scores"]["stock"],
                                    reference_sha256=REFERENCE_SHA256, waveform_member_traversals=1, saved_waveform_reads=0))


if __name__ == "__main__":
    mode, path, *extra = sys.argv[1:]
    if mode in ("worker", "score"):
        sys.path[:0] = [str(SOLVER), str(HERE)]
        if mode == "worker":
            worker(Path(path), extra[0])
        else:
            score(Path(path))
    else:
        sys.path.insert(0, str(HERE))
        {"launch": launch, "prepare": prepare}[mode](Path(path))
