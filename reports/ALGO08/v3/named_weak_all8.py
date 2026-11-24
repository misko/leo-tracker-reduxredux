"""Pair the deployed and exact named publications on identical DS30-0016 20/8 ms input."""

import argparse
from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

from dense_hybrid_combined import data, pin
import named_hybrid_baseline as named
from preloaded_saved_worker import read, write

ADAPTIVE = Path("/dev/shm/leo-v3-weak-all8-adaptive-result01")
ARCHIVED_NAMED = Path("/dev/shm/leo-v3-raw-0016-best-results-01")
EXACT = Path("/dev/shm/leo-v3-exact-named-route")
ENROLLED_PACKET = "sha256:aeb4658b886daaa4f8a93e99224fb4471f032f91feaa5ce58be2361d7009b4ac"
ARCHIVE_EXECUTION = "ed85a78faf7b570215e9ae6565ba85834c9c20afd66390114b655fd4b637cfae"
ARCHIVE_SCORE = "d6d6066836cbebd604d839fb9f86103679e39773181f78d4ad63e3e7e94b099c"
NAMED_ARCHIVE = "33d6cab032ab19f6093d57d6017be32820d479e5e96c082a21b40d4ea75824c0"
PRODUCER_CLOCK = "ea78ecc07d20b61b5f3473d08f849efe178df093c53c095fa9a7a0d6152993f2"
COUNTS = (808, 1426, 506)
RECEIPT = ("run_id", "session_id", "window_count", "counts", "region", "decision", "terminal_sha256")
SOURCES = (Path(__file__), HERE/"named_hybrid_baseline.py", HERE/"named-weak-all8-protocol.md")
MODES = ("named", "exact")


def checkout(*arguments):
    return subprocess.check_output(["git", "-c", f"safe.directory={EXACT}", "-C", str(EXACT), *arguments])


def load_exact(commit, *, expected=None):
    sys.path.insert(0, str(EXACT/"reports/ALGO08/v3"))
    import exact_named_route

    if Path(exact_named_route.__file__).resolve().parent != EXACT/"reports/ALGO08/v3":
        raise ValueError("Expected the frozen exact named assembly")
    files = {}
    for path in exact_named_route.SOURCES:
        name = str(path.relative_to(EXACT))
        sha = expected[name] if expected is not None else sha256(checkout("show", f"{commit}:{name}")).hexdigest()
        if pin(path) != sha:
            raise ValueError(f"The exact route differs from its frozen source {name}")
        files[name] = sha
    return exact_named_route, files


def enrollment(commit):
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from empty_bootstrap import bind_native

    driver, files = load_exact(commit)
    from exact_solver_0057 import ARTIFACT, ARTIFACT_SHA, PRODUCER_SHA

    receipt = data(ADAPTIVE/"final-result.json", ARCHIVE_SCORE)
    hold = data(ADAPTIVE/"execution.json", ARCHIVE_EXECUTION)
    origin, chosen = hold["identity"], hold["selection"]
    packet = ADAPTIVE/"selected-detections.json"
    native = data(packet, ENROLLED_PACKET[7:])
    inventory = ADAPTIVE/"candidate/fast-scan-inputs"/(origin["session"]+".json")
    offer = ARCHIVED_NAMED/"offer.json"
    region = data(offer, origin["offer_sha256"])
    info = data(inventory, origin["inventory"][7:])
    archive = driver.resident_path(Path(origin["archive"]["root"]))
    recipe = chosen["receiver_recipe"]
    source = native["source"]
    bind_native(native, origin["session"], origin["inventory"], origin["detector"][7:], expected=ENROLLED_PACKET)
    if (canonical_digest(recipe) != origin["detector"] or origin["native_sha256"] != ENROLLED_PACKET
            or chosen["native_sha256"] != ENROLLED_PACKET or origin["selected"] != COUNTS[2]
            or (info["window_count"], len(source["probes"]), chosen["selected"]) != COUNTS
            or receipt["declared"] != dict(processed=713, invalid_capture=95, skipped_fast_score=0)
            or receipt["held"]["choice"] != chosen["choice"] or chosen["choice"]["route"] != "unfiltered"
            or chosen["refinement_calls"] or region != origin["original_offer"]
            or source["raw_recording_authority_digest"] != origin["authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != origin["cutoff_utc_ns"]):
        raise ValueError("Original held all-visit authority, waveform coverage or recipe changed")
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    for path in (packet, inventory, offer, ARTIFACT):
        driver.resident_path(path)
    meta = data(ARTIFACT.parent/"artifact-bind.json", PRODUCER_SHA)
    if (pin(ARTIFACT) != ARTIFACT_SHA[7:] or meta["portable_sha256"] != ARTIFACT_SHA
            or meta["source"]["cutoff_utc_ns"] >= origin["cutoff_utc_ns"]):
        raise ValueError("The exact portable index must have an authenticated earlier producer")
    producer = data(ARTIFACT.parent/"dense-export-clock.json", PRODUCER_CLOCK)
    if producer["exit_code"]:
        raise ValueError("The enrolled portable index producer did not complete")
    request = {key: origin[key] for key in ("session", "inventory", "archive", "offer_sha256", "recording",
                                           "authority", "cutoff_utc_ns", "detector")}
    request.update(native=ENROLLED_PACKET, packet=str(packet), saved_inventory=str(inventory), region=str(offer))
    bound = dict(archive=str(archive), portable=[str(ARTIFACT), ARTIFACT_SHA, PRODUCER_SHA])
    prep = dict(local_archive=dict(bytes=sum(r.byte_size for r in refs), snapshots=len(refs)),
                original_archive=origin["archive"], causal_cutoff_utc_ns=origin["cutoff_utc_ns"])
    driver.checked_catalogue(bound, prep, TleArchiveReader, canonical_digest)
    cache = subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE", *(r.path for r in refs)])
    rows = json.loads(cache)["fincore"]
    if len(rows) != len(refs) or any(row["res"] < row["size"] for row in rows):
        raise ValueError("Every original causal snapshot must be resident")
    return dict(request=request, recipe=recipe, actual_counts=COUNTS, portable=bound, catalogue=prep,
                producer_clock=producer, producer_cutoff=meta["source"]["cutoff_utc_ns"],
                exact_source_commit=commit, exact_sources=files, held_sha256=ARCHIVE_EXECUTION,
                held_choice=chosen["choice"], original_control_score_sha256=ARCHIVE_SCORE,
                sources={p.name: pin(p) for p in SOURCES})


def build_ports(output, exact, binding):
    from verified_png_reads import VerifiedPngReads

    audit = dict(rank=[], blocks=Counter(), graph={}, gates=Counter(), portable={}, png={}, verified_tle=Counter())

    def decode(data, digest):
        from joint_publication import figure_evidence

        return figure_evidence(data, digest)

    cache = VerifiedPngReads(output, decode, audit["png"])

    @contextmanager
    def prepare():
        from named_history_once import named_solve

        with named_solve(True, named.RELEASE, named.PAYLOAD) as history:
            audit["history"] = history
            yield

    @contextmanager
    def active():
        from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

        with exact.exact_ports(binding["portable"], binding["catalogue"], audit), cache.capture(FastStandardAnalysisStore):
            yield

    return SimpleNamespace(before_publication=prepare, analyze=active, verify_image=cache.read), audit


def worker(root, mode):
    binding = read(root/"binding.json")
    if binding["sources"] != {p.name: pin(p) for p in SOURCES} or mode not in MODES:
        raise ValueError("The enrolled saved comparison sources changed")
    output = root/mode
    if mode == "named":
        named.worker(root/"binding.json", output, input_sha=ENROLLED_PACKET, counts=COUNTS)
        return
    exact, files = load_exact(binding["exact_source_commit"], expected=binding["exact_sources"])
    if files != binding["exact_sources"]:
        raise ValueError("The exact solver differs from its enrollment")
    ports, audit = build_ports(output, exact, binding)
    named.worker(root/"binding.json", output, input_sha=ENROLLED_PACKET, counts=COUNTS, ports=ports)
    write(output/"ports.json", audit)


def launch(root, commit):
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    if root.parent.resolve(strict=True) != Path("/dev/shm") or root.exists() or not commit:
        raise ValueError("Use a new private tmpfs output")
    bound = enrollment(commit)
    root.mkdir()
    (root/"fonts").mkdir()
    (root/"tmp").mkdir()
    for path in (ADAPTIVE/"fonts").glob("fontlist-*.json"):
        (root/"fonts"/path.name).hardlink_to(path)
    commands = {mode: ["/usr/bin/timeout", "--kill-after=2s", "35s", RELEASE/"venv/bin/python", "-IB",
                       Path(__file__), "worker", root, mode] for mode in MODES}
    write(root/"binding.json", dict(bound, machine=host(), command={k:list(map(str, cmd)) for k,cmd in commands.items()}))
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    for mode in MODES:
        result = measure(commands[mode], env, root/mode)
        write(root/f"{mode}-clock.json", result)
        if result["exit_code"]:
            raise ValueError(f"Measured {mode} worker failed: {result['stderr_tail']}")


def verify(root):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from triage_bounds import calibration_comparison

    bound = read(root/"binding.json")
    timings = {k: read(root/f"{k}-clock.json") for k in MODES}
    work = {k: read(root/k/"named-saved-witness.json") for k in MODES}
    ports = read(root/"exact/ports.json")
    a, b = (work[k]["receipt"] for k in MODES)
    if (any(t["exit_code"] for t in timings.values()) or a["region"] != b["region"]
            or any(item["handoff"]["native"] != ENROLLED_PACKET or item["handoff"]["detector"] != bound["request"]["detector"]
                   for item in work.values()) or work["named"]["stock_specification"] != work["exact"]["stock_specification"]):
        raise ValueError("The deployed/exact workers did not use matched complete signed inputs and named settings")
    terminals = {k: read(root/k/"fast-scan-automatic-work"/work[k]["receipt"]["run_id"]/"terminal.json") for k in MODES}
    for k, terminal in terminals.items():
        if terminal["native_sha256"] != ENROLLED_PACKET or canonical_digest(terminal) != work[k]["receipt"]["terminal_sha256"]:
            raise ValueError("The terminal is not signed to its actual detector input")
    media = {k: work[k]["evidence"] for k in MODES}
    complete = a["decision"] == b["decision"] == "complete"
    grids = {}
    if complete:
        for mode in MODES:
            store = FastStandardAnalysisStore(root/mode)
            grid = store.position_grid(work[mode]["receipt"]["run_id"])
            grids[mode] = {k:v for k,v in grid.items() if k != "elapsed_seconds"}
    parity = dict(receipt=all(a[k] == b[k] for k in RECEIPT), terminal=terminals["named"] == terminals["exact"],
                  owners=media["named"]["owner_rows"] == media["exact"]["owner_rows"],
                  figures=media["named"]["images"] == media["exact"]["images"],
                  path=media["named"].get("sidecars", {}).get("path") == media["exact"].get("sidecars", {}).get("path"),
                  grid=not complete or grids["named"] == grids["exact"])
    named_raw = data(HERE/"measurements/raw-0016-best.json.gz", NAMED_ARCHIVE)
    original = named_raw["original"]["stock"]
    request = bound["request"]
    if (original["science"]["raw_authority"] != request["authority"] or a["region"] != original["science"]["receipt"]["region"]
            or named_raw["admission"]["inventory"] != request["inventory"]
            or named_raw["admission"]["cutoff_utc_ns"] != request["cutoff_utc_ns"]
            or named_raw["admission"]["archive"]["sha256"] != request["archive"]["snapshots_sha256"]):
        raise ValueError("The original deployed detector comparison has a different physical source, region or archive")
    history = {"deployed_v3_own_detector": original["science"]}
    history.update({k: terminals[k] for k in MODES if work[k]["receipt"]["decision"] == "complete"})
    fact = {k: {a: dict(Counter(r[2] for r in rows)) for a, rows in media[k]["owner_rows"].items()} for k in MODES}
    acquired = data(ADAPTIVE/"final-result.json", ARCHIVE_SCORE)["separate_clock_model"]["elapsed_s"]["historical_raw_acquisition_s"]
    first = timings["exact"]["elapsed_s"]+bound["producer_clock"]["elapsed_s"]
    archive_clock = original["process"]["clock"]
    exact_activation = not any(x["compatibility"]["fallback"] or x["loading"]["fallback"]
                               for x in ports["portable"]["transfers"])
    write(root/"result.json", dict(state={k: w["receipt"]["decision"] for k,w in work.items()}, output_parity=parity,
          exact_science=complete and all(parity.values()), exact_activation=exact_activation, source_bindings=bound,
          bindings_sha256=pin(root/"binding.json"), clocks=timings, terminals=terminals, evidence=work, ports=ports,
          geography=calibration_comparison(history, "DS30-0016"), role_counts=fact,
          original_named=dict(clock=archive_clock, terminal=original["science"]["arms"], owners=original["owner_counts"], factors=original["factors"]),
          original_waveform_reads=0, backing_archive_reads=0, timing=dict(
              matched_saved_ratio=timings["named"]["elapsed_s"]/timings["exact"]["elapsed_s"],
              first_use_saved_s=first, historical_acquisition_only_s=acquired,
              separate_clock_sum_s=acquired+timings["exact"]["elapsed_s"],
              separate_clock_ratio=archive_clock["elapsed_s"]/(acquired+timings["exact"]["elapsed_s"]))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "verify"))
    parser.add_argument("root", type=Path)
    parser.add_argument("argument", nargs="?")
    options = parser.parse_args()
    if options.action == "verify":
        verify(options.root)
    else:
        (launch if options.action == "launch" else worker)(options.root, options.argument)
