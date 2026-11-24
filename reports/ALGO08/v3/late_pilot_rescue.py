"""Capture and independently score one frozen within-visit pilot contrast."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes
import gzip
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ds30_0049_receiver_factorial import (  # noqa: E402
    ARMS, FULL, INSTALLED_SHA, PRIMARY, PRIMARY_PIN, SHORT, SHORT_PIN,
    choose, compare, digest, engines, input_scope, observation, read, runtime, write,
)
from mixed_aperture_receiver import StereoSchedule, strongest  # noqa: E402


CONTROL_NAMES = ("on_period", "off_period", "periodic", "hash")
LAGS = dict(on_period=40_000, off_period=38_976)
CASES = ("DS30-0049", "DS30-0016", "DS30-0008", "DS30-0169")
SOURCES = ("late_pilot_rescue.py", "late_pilot_rescue.c", "repeat_negative.c", "late-pilot-rescue-protocol.md",
           "ds30_0049_receiver_factorial.py", "mixed_aperture_receiver.py", "original_prefix_scaling.py")
CAPTURE_SHA = "7407689c2e8839edb281c505bcc6defc585ee24706522767edb8d6f3d9a27a5c"
DENSE_STOCK = (Path("/tmp/leo-v3-0008-prefix-transfer-result05/full-20/routed/candidate/fast-scan-automatic-work")
               / "algo08-v2-3dce9426edd1831eade2003d69a00297/detections.json")
MEDIUM = Path("/dev/shm/leo-receiver-ceiling-0169-results01")
STAGE = Path("/dev/shm/leo-v3-guarded-selective-0016-stage01")
MEDIUM_SCOPE = "95a438f0904e4568b6f2a3618b7fbf691c29d0e2d352fd3727cc83d35b72aa9a"
DENSE_MEMBER = Path("/dev/shm/leo-seekable-member-0008-case1/fast8-auto-20261113-075937-d9ab96ee-1-lower-segment-00000000")
DENSE_MANIFEST = "sha256:5ffe3ed98feb37f7f7ada44dbf34d2af9d3fcadce567fd3cdbb7e31965a02759"


def verified(path, pin):
    from empty_bootstrap import checked

    return json.loads(checked(path, pin.removeprefix("sha256:")))


def scopes(case):
    if case == "DS30-0049":
        identity = dict(session_id="fast-8243d304e0429146a7f7349b906b4643",
                        input_manifest_sha256="sha256:8243d304e0429146a7f7349b906b464366a93fd4008b0b87506575ec21cfe9ff")
        segment, pin, _, _ = input_scope(identity)
        return [(segment, pin, 384)]
    if case == "DS30-0016":
        from ds30_0016_full_primary_transfer import checked

        stage = checked(STAGE / "staging.json")
        files = stage["files"]["manifest"]
        return [(STAGE / Path(file).parent.parent.name / Path(file).parent.name, pin, count)
                for (file, _, pin), count in zip(sorted(files), (512, 296), strict=True)]
    if case == "DS30-0008":
        return [(DENSE_MEMBER, DENSE_MANIFEST, 64)]
    data = verified(MEDIUM / "scope.json", MEDIUM_SCOPE)["entry"]
    return [(Path(data["path"]), data["manifest_digest"], 64)]


def clock():
    return process_time_ns(), perf_counter_ns()


def elapsed(start):
    return [end - begin for begin, end in zip(start, clock(), strict=True)]


def build(library):
    command = ["cc", "-std=c11", "-O3", "-march=x86-64-v3", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
               str(HERE / "late_pilot_rescue.c"), "-o", str(library)]
    subprocess.run(command, check=True, timeout=10)
    return dict(compile=command, library_sha256=digest(library))


class Contrast:
    def __init__(self, library):
        self.call = ctypes.CDLL(str(library)).late_pilot_score
        self.call.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.call.restype = ctypes.c_double

    def run(self, samples, radio, lag):
        begin = clock()
        value = self.call(samples.ctypes.data, len(samples), radio, lag)
        paid = elapsed(begin)
        if not isfinite(value):
            raise ValueError("Nonfinite or invalid nominal-coherence score")
        return value, paid


def key(row):
    return row["visit_index"], row["receiver_id"]


def nomination(rows, mode):
    """Rank only metadata and the frozen scores of the already eligible rows."""
    chronological = sorted(rows, key=key)
    quota = len(chronological) // 4
    if mode == "periodic":
        return [key(chronological[(2 * j + 1) * len(chronological) // (2 * quota)]) for j in range(quota)]
    if mode == "hash":
        def order(row):
            visit, radio = key(row)
            return sha256(f"late-pilot-rescue-v1:{visit}:{radio}".encode()).digest(), visit, radio
    else:
        def order(row):
            return -row["scores"][mode], *key(row)
    return [key(row) for row in sorted(chronological, key=order)[:quota]]


def choices(rows):
    cohorts = {"misses": [], "positive_counterfactual": []}
    for row in rows:
        if not row["anchor"]:
            cohorts["positive_counterfactual" if row["short_positive"] else "misses"].append(row)
    result = {}
    for name, cohort in cohorts.items():
        result[name] = {}
        for mode in CONTROL_NAMES:
            start = clock()
            selected = nomination(cohort, mode)
            result[name][mode] = dict(nominations=selected, ordering_cpu_wall_ns=elapsed(start))
    return result


def source_specs(case):
    data = []
    from empty_bootstrap import checked

    for path, pin, count in scopes(case):
        if path.resolve(strict=True) != path or path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01"):
            raise ValueError("Expected a direct local stage")
        manifest_path = path / "manifest.json"
        if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", path], text=True).strip() != "tmpfs":
            raise ValueError("Require existing local tmpfs for every waveform member")
        manifest = json.loads(checked(manifest_path, pin[7:]))
        members = [row for row in manifest["chunks"] if row["first_sequence"] < count]
        files = [manifest_path, *(path / row[k] for row in members for k in ("index_relative_path", "payload_relative_path"))]
        if not members or sum(row["window_count"] for row in members) != count:
            raise ValueError("Expected only complete signed original members with a fixed frontier")
        if any(file.resolve(strict=True) != file for file in files):
            raise ValueError("Expected direct signed resident members without symlinks")
        data.append((path, pin, count, files))
    return data


def capture(case, root):
    import numpy as np

    symbols = runtime()
    from aperture_trial import machine
    from empty_bootstrap import checked
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support
    from leo.storage.fast_scan import FastSegmentSource
    from original_prefix_scaling import guard
    from visit_frame_raw_0016 import resident

    host = machine()
    if host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"] or set(host["threads"].values()) != {"1"}:
        raise ValueError("Expected the shared low-priority CPU2 slot")
    if root.parent != Path("/dev/shm") or root.exists():
        raise ValueError("Use a fresh private tmpfs output")
    spec = source_specs(case)
    files = [file for _, _, _, data in spec for file in data]
    before = resident(files)
    binaries = {FULL: INSTALLED_SHA, PRIMARY: PRIMARY_PIN, SHORT: SHORT_PIN}
    for path, pin in binaries.items():
        checked(path, pin)
    sys.addaudithook(guard(files))
    root.mkdir(mode=0o700)
    build_info = build(root / "coherence.so")
    write(root / "admission.json", dict(case=case, host=host, paths=[str(file) for file in files], resident=before,
          source_sha256={name: digest(HERE / name) for name in SOURCES}, feature=build_info,
          receivers={str(path): pin for path, pin in binaries.items()},
          scopes=[(str(path), pin, count) for path, pin, count, _ in spec]))
    contrast = Contrast(root / "coherence.so")
    short_rows, long_rows, hashes, invalid = [], [], [], []
    policy = FastScanPolicyV2()
    schedule = StereoSchedule(full_coverage=True)
    scan = clock()
    blocks = getrusage(RUSAGE_SELF).ru_inblock
    with ExitStack() as stack:
        bank = {}
        for directory, pin, stop, _ in spec:
            source = FastSegmentSource(dict(path=str(directory), manifest_digest=pin), stop_sequence=stop)
            for window in source.windows():
                target, acquisition = window.target, window.acquisition
                visit, rate = acquisition["global_visit"], window.sample_rate_hz
                if visit != len(hashes) or rate != 10_000_000 or source.receiver_ids != (0, 1):
                    raise ValueError("Original stereo clock or chronology changed")
                hashes.append(window.iq_sha256)
                if not valid_window_support(acquisition, rate, window.samples.shape, source.receiver_ids, policy):
                    invalid.append(visit)
                    continue
                if window.samples.shape != (200_000, 2, 2) or window.samples.dtype != np.dtype("<i2") or not window.samples.flags.c_contiguous:
                    raise ValueError("Expected unmodified 20 ms stereo CI16")
                edge = target["edge"]
                if edge not in bank:
                    bank[edge] = engines(stack, edge, symbols)
                _, mode = schedule.visit(edge, target, acquisition)
                anchor = mode == "full"
                center = target["rf_center_hz"] - target["lnb_lo_hz"] - acquisition["actual_if_center_hz"]
                raw = SimpleNamespace(acquisition=acquisition, target=target, sample_rate_hz=rate)
                for radio in (0, 1):
                    probe = symbols["_probe"](raw, radio, [])
                    order = ("20-two",) if anchor else ("8-primary", "20-primary", "20-two")
                    if not anchor and (visit + radio) % 2:
                        order = order[::-1]
                    estimates = {tag: bank[edge][tag].run(window.samples, radio, center) for tag in order}
                    narrow = estimates["20-two" if anchor else "8-primary"]
                    short_rows.append(short_row(contrast, window, probe, anchor, radio, narrow))
                    long_rows.append(long_row(probe, anchor, estimates, symbols["factor_candidate"]))
    scan_clock = elapsed(scan)
    after = resident(files)
    if before != after or len(hashes) != sum(stop for _, _, stop, _ in spec):
        raise ValueError("The enrolled signed stage or issued window count changed")
    nominations = choices(short_rows)
    write(root / "nominations.json", dict(choices=nominations, short=short_rows, hashes=hashes, invalid=invalid,
          scan_cpu_wall_ns=scan_clock, input_blocks=getrusage(RUSAGE_SELF).ru_inblock-blocks, resident_after=after))
    write(root / "sealed-nominations.json", {name: digest(root / name) for name in ("admission.json", "nominations.json")})
    write(root / "long-receiver.json", long_rows)
    write(root / "sealed-long-receiver.json", {name: digest(root / name) for name in
          ("sealed-nominations.json", "long-receiver.json")})


def short_row(contrast, window, probe, anchor, radio, short):
    order = tuple(LAGS) if (probe["visit_index"] + radio) % 2 == 0 else tuple(reversed(LAGS))
    scores = {} if anchor else {name: contrast.run(window.samples, radio, LAGS[name]) for name in order}
    return dict(visit_index=probe["visit_index"], receiver_id=radio, anchor=anchor,
                short_positive=bool(short[0]), short_cpu_wall_ns=short[1],
                scores={name: result[0] for name, result in scores.items()},
                feature_cpu_wall_ns={name: result[1] for name, result in scores.items()})


def long_row(probe, anchor, estimates, factor):
    alternatives = {name: [factor(rank, epoch, status="complete", offset=offset, cfo=hz, exact=exact, control=roll,
                              margin=exact-roll) for rank, epoch, offset, hz, exact, roll in output[0]]
                    for name, output in estimates.items()}
    return dict(opportunity=probe, anchor=anchor, alternatives=alternatives,
                full_cpu_wall_ns={name: estimates[name][1] for name in ("20-primary", "20-two") if name in estimates})


def originals(case):
    from ds30_0049_receiver_factorial import CROSSOVER, CROSSOVER_PIN, controls
    from leo.contracts.digests import canonical_digest

    if case == "DS30-0049":
        pair = controls()
        stock, result = pair["installed"]
        packet = pair["successor"][0]
        owner_rows = verified(CROSSOVER, CROSSOVER_PIN)["ordered_owner_rows"]["installed-installed"]
        if any(canonical_digest({row[0]: row[1] for row in owner_rows[arm]}) != result["evidence"]["owners"][arm]
               for arm in ARMS):
            raise ValueError("Original owners are not bound to the published control")
        return stock, packet, owner_rows
    if case == "DS30-0016":
        from empty_bootstrap import checked

        archive = HERE / "measurements/ds30-0016-full-primary-transfer.json.gz"
        contents = json.loads(gzip.decompress(checked(archive, "ace7652af6fa0945f28dd161d1b16ecb293f0ca7c8bdf8340dfeff610c87fd9c")))
        stock, packet = (contents["detector_packets"][mode]["document"] for mode in ("installed", "charted"))
        return stock, packet, contents["installed_owners"]
    if case == "DS30-0008":
        stock = verified(DENSE_STOCK, "2df28e68ea845576ea5e8a02057bce32983dbafb469fa2c4f710a3d89729fa85")
        if stock["provenance"]["detector_sha256"] != "sha256:" + INSTALLED_SHA:
            raise ValueError("Expected the installed detector, whose replay must agree exactly")
        return stock, None, {}
    medium = verified(MEDIUM / "1-stock.json", "b1d8a32033373c5996217fe3a70e9e7fe5ae58ba3f75439052eacd2ff55cb453")
    return medium["packet"], None, {}


def near(reference, alternative):
    return compare(reference, alternative) in {"matched", "exact"}


def scan_axes(rows, controller, short, owners):
    cases = {}
    for out, live, stock in zip(rows, short, controller, strict=True):
        row = out["opportunity"]
        if key(row) != key(live) or key(row) != key(stock) or out["anchor"] != live["anchor"]:
            raise ValueError("Original, late score and native timing lanes do not align")
        if row != dict(stock, candidates=[]):
            raise ValueError("The original physical opportunity fields changed")
        if out["anchor"]:
            continue
        picks = out["alternatives"]
        old = strongest(picks["8-primary"])
        primary, strongest_full = map(strongest, (picks["20-primary"], picks["20-two"]))
        if bool(old) != live["short_positive"] or picks["20-primary"] != [x for x in picks["20-two"] if x["candidate_rank"] == 0]:
            raise ValueError("The eligible short decisions or genuine 20 ms ranks changed")
        original = strongest(stock["candidates"])
        cases[key(row)] = (out, live, original, old, primary, strongest_full, owners.get(key(row), ()))
    return cases


def recovered(items):
    counts = Counter()
    for raw, _, original, _, candidate, complete, owned_by in items:
        counts.update(tested=1, only_native_20_if_stock_empty=candidate is not None and original is None,
                      twenty_primary_positive=candidate is not None, twenty_two_positive=complete is not None,
                      installed_positive=original is not None,
                      selected_primary_matches=near(original, candidate), selected_two_matches=near(original, complete),
                      two_available=any(near(original, value) for value in raw["alternatives"]["20-two"]))
        for arm in owned_by:
            counts.update({arm + "_owner_eligible": 1, arm + "_owner_primary": int(near(original, candidate)),
                           arm + "_owner_two": int(near(original, complete))})
    return dict(counts)


def replacements(items):
    counts = Counter()
    for _, _, original, short, long, _, owned_by in items:
        different = not near(short, long)
        counts.update(tested=1, dropped=long is None, displaced=different and long is not None,
                      strong_lost=different and short["fractional_margin"] >= .10,
                      installed_match_lost=near(original, short) and not near(original, long),
                      installed_match_gained=not near(original, short) and near(original, long))
        for arm in owned_by:
            counts.update({arm + "_owner_match_lost": int(near(original, short) and not near(original, long))})
    return dict(counts)


def costs(mode, short_only, eligible, nominated, ordering):
    feature = sum(item[1]["feature_cpu_wall_ns"][mode][0] for item in eligible) if mode in LAGS else 0
    retries = {role: sum(item[0]["full_cpu_wall_ns"][role][0] for item in nominated)
               for role in ("20-primary", "20-two")}
    return dict(short_only_cpu_ns=short_only, eligibility_feature_cpu_ns=feature, ordering_cpu_ns=ordering,
                retry_cpu_ns=retries, projected_receiver_cpu_ns={role: short_only + feature + ordering + value
                                                              for role, value in retries.items()})


def score(case, root):
    symbols = runtime()
    sealed = {}
    for filename in ("sealed-nominations.json", "sealed-long-receiver.json"):
        values = read(root / filename)
        if values != {name: digest(root / name) for name in values}:
            raise ValueError("Measured products changed after sealing")
        sealed[filename] = digest(root / filename)
    admitted = read(root / "admission.json")
    source_pins = {name: digest(HERE / name) for name in SOURCES}
    recorded = admitted["source_sha256"]
    # The later scorer only corrected the DS30-0008 reference from mixed-aperture to installed.
    admitted_capture = source_pins | {Path(__file__).name: CAPTURE_SHA}
    if (case != admitted["case"] or recorded not in (source_pins, admitted_capture)
            or admitted["feature"]["library_sha256"] != digest(root / "coherence.so")):
        raise ValueError("Scorer differs from the frozen admission")
    nomination_data = read(root / "nominations.json")
    short, long = nomination_data["short"], read(root / "long-receiver.json")
    stock, existing_short, stock_owners = originals(case)
    stop = len(nomination_data["hashes"])
    cutoff = [row for row in stock["source"]["probes"] if row["visit_index"] < stop]
    selected = choose(long, "20-two", "continuation", symbols["Continuation"])
    if selected != cutoff:
        raise ValueError("The measured 20 ms replay did not reproduce the original chronological control")
    if existing_short is not None:
        expected = [row for row in existing_short["source"]["probes"] if row["visit_index"] < stop]
        if choose(long, "8-primary", "strongest", symbols["Continuation"]) != expected:
            raise ValueError("The measured short path differs from the charted unfiltered original")
    owner_ids = {arm: {row[0] for row in data} for arm, data in stock_owners.items()}
    session = stock["source"]["session_id"]
    owners = {key(row): tuple(arm for arm, values in owner_ids.items() if observation(row, session) in values)
              for row in cutoff}
    joined = scan_axes(long, cutoff, short, owners)
    eligible = [item for item in joined.values() if item[3] is None]
    positive = [item for item in joined.values() if item[3] is not None]
    short_only = sum(row["short_cpu_wall_ns"][0] for row in short)
    nom = nomination_data["choices"]
    policy = {}
    for mode in CONTROL_NAMES:
        frozen, counter = (nom[cohort][mode] for cohort in ("misses", "positive_counterfactual"))
        chosen, replaced = ([joined[tuple(slot)] for slot in group["nominations"]] for group in (frozen, counter))
        if (len(chosen) != len({key(item[1]) for item in chosen}) or len(chosen) != len(eligible) // 4
                or any(item[3] is not None for item in chosen) or len(replaced) != len(positive) // 4
                or any(item[3] is None for item in replaced)):
            raise ValueError("A sealed decision violates the fixed matched nomination budget")
        policy[mode] = dict(result=recovered(chosen), counterfactual=replacements(replaced),
                            costs=costs(mode, short_only, eligible, chosen, frozen["ordering_cpu_wall_ns"][0]))
    write(root / "score.json", dict(case=case, sealed=sealed, scorer_sha256=source_pins[Path(__file__).name],
          visits=stop, admitted=len(short) // 2,
          excluded=len(nomination_data["invalid"]), anchors=len(short) - len(joined), enrolled_misses=recovered(eligible),
          actual_replacements_of_short_positive_lanes=0, policy=policy))


if __name__ == "__main__":
    from empty_bootstrap import PAYLOAD, RELEASE

    sys.path[:0] = [str(PAYLOAD), str(RELEASE / "src"), str(HERE.parents[2])]
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("capture", "score"))
    cli.add_argument("case", choices=CASES)
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    {"capture": capture, "score": score}[args.action](args.case, args.root)
