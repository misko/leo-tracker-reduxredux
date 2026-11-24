"""Seal candidate-only plans and score existing full-20 ms opportunity overlap."""

import argparse
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]
from anchor_exposure import bind, enroll
from continued_cfo_trial import rebinding
from empty_short_recheck import lane, plan, stream
from leo.contracts.digests import canonical_digest, sha256_digest


MEASUREMENTS = HERE/"measurements"
SPARSE = "c5b57b0602e81a6a85c14caf648eb12341f098d09915b4d3f705094ed309574c"
GENERIC_8 = "fe4ba7b7613654c268353f9e4a78c2bbb916904e06387ace304b0866818f0e3d"
FULL = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
CASES = ("DS30-0049", "DS30-0016", "DS30-0163", "DS30-0008")
ARMS = ("c0", "fitted_c")
SMOKE = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124/cases/DS30-0049")
WEAK = Path("/dev/shm/leo-v3-integrated-original-02/DS30-0016")
WEAK_STOCK = Path("/dev/shm/leo-v3-stock-raw-repeat-DS30-0016-01/stock")
MEMBER = Path("/tmp/leo-v3-0163-resumed-member-pair02")
DENSE = Path("/tmp/leo-v3-original-dense-intake-result01")
PIN = {
    "ds30-paired-smoke.json.gz": "c5d64fe44587aaef4663dbfafe2b02ac8a89b52e9670d90f50a21e3e4249200f",
    "integrated-original.json.gz": "eb115ec1dd7a734693e21d8be49e2f7de87fe48936b8db8d51e1216cf37a0dff",
    "stock-raw-repeat-0016.json.gz": "e852ffcf8b887e7cab66bcb5f8ad4911caaaa9398264d3b5f351b02862b17850",
    "first-member-0163-resume-acquisition.json.gz": "5cf1c7e7c785c84913851515242ddcd434b02ee4de33c1a244e3f53732ee7c8f",
    "first-member-0163-owner-join.json": "734c3e6150334513ac9df965f4b41f9b6c4f0c4998a1e6afc5792383f005882a",
    "attested-visit-detector-DS30-0163.json.gz": "efe1d63dc5fe6f81cf6730d01d18fc52406da9536f12ce5de1d3ae125f7e5dd9",
    "original-dense-intake.json.gz": "b6a9e50f5b3be9e4987e2bef3727931509a9a017ad4a3ae269d3eb390983c390",
    "track-quadrature.json.gz": "9ab0632563cc2ceacd043569956ef7fa1dfb9e24f26de370df57b8a19681221f",
    "receiver-mix-budget.json": "856694a1b8a26f74f172b58a9e3e5b1f1e1c5c1e10a8bc5b185c84456f1c2ffd",
    "short-rank-transfer-DS30-0008.json.gz": "362052fd7641a0b0175cf90da02234c612e04c6edbd34413c44632ee97c235bd",
}


def checked(path, pin=None):
    data = path.read_bytes()
    if pin is not None and sha256_digest(data)[7:] != pin.removeprefix("sha256:"):
        raise ValueError(f"Scored evidence hash changed at {path}")
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def historical(name):
    return checked(MEASUREMENTS/name, PIN[name])


def saved(folder, pin=None):
    path, = (folder/"fast-scan-automatic-work").glob("*/detections.json")
    return checked(path, pin)


def candidates(case):
    if case == "DS30-0049":
        root = SMOKE/"successor/attempt-000002"
        raw = checked(root/"publication/unified-short-bootstrap.json")
        return saved(root/"publication", raw["native_sha256"]), raw["held_anchor_route"], raw["receiver_audit"]["native"]
    if case == "DS30-0016":
        raw = checked(WEAK/"candidate/unified-short-bootstrap.json")
        return saved(WEAK/"candidate", raw["native_sha256"]), raw["held_anchor_route"], raw["receiver_audit"]["native"]
    if case == "DS30-0163":
        local = checked(MEMBER/"result.json")["result"]["integrated"]
        return (checked(MEMBER/"integrated/detections.json", local["packet_sha256"]),
                checked(MEMBER/"integrated-held-anchor-route.json"), local["receiver"]["native"])
    if case == "DS30-0008":
        local = checked(DENSE/"result.json")["pairs"][0]["first_use"]["source"]
        return (checked(DENSE/"1-first_use/detections.json", local["native"]),
                checked(DENSE/"1-first_use-held-anchor-route.json"), None)
    raise ValueError("Unenrolled source")


def base_packet(native, held, *, short_pin=SPARSE):
    recipe = held["receiver_recipe"]
    parent = {k: v for k, v in recipe.items() if k != "held_native_8ms"}
    rows = native["source"]["probes"]
    base = rebinding(native, rows, parent)
    positive = sum(len(row["candidates"]) for row in rows)
    if (held["choice"]["route"] != "unfiltered" or held["refinement_calls"]
            or held["selected"] != positive or held["observed"] != positive
            or parent["aperture_samples"] != [200_000, 80_000] or parent["shortened_sha256"] != short_pin
            or parent["installed_sha256"] != FULL or canonical_digest(recipe) != held["detector_recipe_sha256"]
            or native["provenance"]["detector_sha256"] != held["detector_recipe_sha256"]
            or canonical_digest(parent) != held["parent_detector_sha256"]
            or canonical_digest(native) != held["native_sha256"] or canonical_digest(base) != held["parent_native_sha256"]):
        raise ValueError("The published rows cannot be proven equal to all base measured sparse rows")
    return base


def dense_equivalence(native, apertures):
    """Match every short callback's original Factor ABI bytes to the measured sparse transfer."""
    report = historical("short-rank-transfer-DS30-0008.json.gz")
    source = report["source"]
    intake = checked(DENSE/"result.json", "add31a04da733a4c4cdaa87b613c8f8832aabb8c37aa55d278045c227f85cde6")
    inventory = intake["binding"]["inventory"]
    stage = checked(DENSE/"1-first_use/worker.json")
    if (report["build"]["pins"] != {"active": GENERIC_8, "matched": GENERIC_8, "sparse": SPARSE}
            or inventory["prefix_members"] != [source["member"]]
            or inventory["segments"][0]["manifest_digest"].removeprefix("sha256:") != source["manifest_sha256"].removeprefix("sha256:")
            or source["window_sha256"] != stage["first_use_iq"]
            or canonical_digest([intake["binding"]["digest"], stage["first_use_iq"]])
            != native["source"]["raw_recording_authority_digest"]):
        raise ValueError("The DS30-0008 sparse-equivalence trial measured a different original member")
    rows = [r for r, mode in zip(native["source"]["probes"], apertures, strict=True) if mode == "short"]
    raw = []
    for row, reference in zip(rows, report["records"], strict=True):
        factors = row["candidates"]
        if (lane(row) != (reference["visit"], reference["lane"]) or reference["center"] != 0
                or bool(factors) != reference["positive"] or len(factors) > 1):
            raise ValueError("Dense sparse equivalence changed the lane, aperture or signed base positive")
        factor, = factors or (None,)
        raw.append("" if factor is None else struct.pack(
            "<ii4d", factor["candidate_rank"], factor["integer_epoch_sample"], factor["fractional_epoch_offset_samples"],
            factor["fractional_tracking_cfo_hz"], factor["fractional_exact_score"], factor["fractional_control_score"]).hex())
    measured = sha256_digest(json.dumps(raw).encode())[7:]
    if measured != report["exact_raw_factor_sha256"]:
        raise ValueError("The measured sparse short raw factor bytes differ")
    return dict(short_lanes=len(rows), full_anchors="same original installed full receiver",
                native_factor_bytes_sha256=measured, source_sha256=PIN["short-rank-transfer-DS30-0008.json.gz"])


def prescription():
    results = {}
    for case in CASES:
        native, held, _ = candidates(case)
        base = base_packet(native, held, short_pin=GENERIC_8 if case == "DS30-0008" else SPARSE)
        apertures = ["full" if event[4] == "anchor" else "short" for event in enroll(base)]
        exact = dense_equivalence(base, apertures) if case == "DS30-0008" else None
        rows = base["source"]["probes"]
        empties = plan(rows, apertures)
        results[case] = dict(preheld_sha256=canonical_digest(base), published_sha256=canonical_digest(native),
                             issued=base["provenance"]["window_count"], apertures=apertures, empties=empties,
                             separately_verified_sparse_equivalence=exact)
    source_names = ("empty-short-recheck-protocol.md", "empty_short_recheck.py", Path(__file__).name)
    return dict(schema_version=1, sources={n: sha256_digest((HERE/n).read_bytes()) for n in source_names}, plans=results)


def observation_id(session, row):
    return sha256_digest(f'{session}:{row["receiver_id"]}:{row["valid_start_counter"]}'.encode())


def owner_ids(ordered, digests):
    owners = {}
    for arm in ARMS:
        rows = ordered[arm]
        mapping = {i: n for i, n, _role in rows}
        if canonical_digest(mapping) != digests[arm] or len(mapping) != len(rows):
            raise ValueError(f"Released original owner digest mismatch in {arm}")
        owners[arm] = set(mapping)
    return owners


def named(case, candidate):
    if case == "DS30-0049":
        sealed = historical("ds30-paired-smoke.json.gz")["cases"][case]
        for role in ("installed", "successor"):
            result = SMOKE/role/"attempt-000002/result.json"
            if checked(result, sealed["pair"]["attempt_result_sha256"][role]) != sealed["arms"][role]:
                raise ValueError("Corrected full pair differs from its verified results")
        installed = sealed["arms"]["installed"]
        if canonical_digest(candidate) != sealed["arms"]["successor"]["native_sha256"]:
            raise ValueError("Corrected successor native digest changed")
        packet = saved(SMOKE/"installed/attempt-000002/publication", installed["native_sha256"])
        exact = checked(Path("/tmp/leo-v3-0049-saved-cross-proof02/installed-installed/crossover-worker.json"),
                        "86d3b27db6e1bb85f69e180228ff6b7b977d4779f1b42c018ce054475c2c3141")
        if exact["submitted_native_sha256"] != installed["native_sha256"]:
            raise ValueError("Installed crossover changed the owner input")
        return packet, packet["source"]["session_id"], owner_ids(exact["ordered_owners"], installed["evidence"]["owners"])
    if case == "DS30-0016":
        integrated = historical("integrated-original.json.gz")["runs"]["positive_first"][case]["result"]["document"]
        if canonical_digest(candidate) != integrated["receiver"]["native_sha256"]:
            raise ValueError("Integrated weak control packet changed")
        stock = historical("stock-raw-repeat-0016.json.gz")["stock"]
        packet = saved(WEAK_STOCK, stock["digest"])
        original = checked(Path("/var/tmp/leo-full-short-DS30-0016-pair/stock/joint-research-receipt.json"),
                           "f6c56736b6382ca1c8fc062d49e5e2d9503230a3c6d82ede33cf607e5fe81bed")
        if original["receipt"]["terminal_sha256"] != stock["science"]["receipt"]["terminal_sha256"]:
            raise ValueError("Installed original and independent repeat owners are unmatched")
        return packet, packet["source"]["session_id"], owner_ids(original["selected_rows"], stock["science"]["owners"])
    if case == "DS30-0163":
        archive = historical("first-member-0163-resume-acquisition.json.gz")["documents"]
        if canonical_digest(candidate) != "sha256:"+archive["integrated/detections.json"]["sha256"]:
            raise ValueError("The independent original first member changed")
        packet = archive["named/detections.json"]["document"]
        owner = historical("first-member-0163-owner-join.json")
        # The archived exact join supplies lane keys, using the full-recording session.
        owned_lanes = {arm: {(row["visit"], row["receiver"]) for row in owner["comparable_nonempty_lanes"]
                            if arm in row["owners"]} for arm in ARMS}
        return packet, None, owned_lanes
    if case == "DS30-0008":
        pair = historical("original-dense-intake.json.gz")["pairs"][0]
        if canonical_digest(candidate) != pair["first_use"]["source"]["native"]:
            raise ValueError("The original first-member successor packet changed")
        packet = checked(DENSE/"1-named/detections.json", pair["named"]["source"]["native"])
        stock = historical("track-quadrature.json.gz")["runs"][case]["stock"]
        full = checked(Path("/tmp/ds30-v2-stage-all-6cdbac/DS30-0008/candidate/fast-scan-automatic-work/"
                            "algo08-v2-3dce9426edd1831eade2003d69a00297/detections.json"),
                       "2df28e68ea845576ea5e8a02057bce32983dbafb469fa2c4f710a3d89729fa85")
        if (stock["identity"]["native_sha256"] != canonical_digest(full)
                or [row for row in full["source"]["probes"] if row["visit_index"] < 64] != packet["source"]["probes"]
                or full["clock_anchor"] != packet["clock_anchor"] or full["delivery_clocks"][:64] != packet["delivery_clocks"]):
            raise ValueError("The first-member original rows do not match the full installed owner packet")
        return packet, full["source"]["session_id"], owner_ids(stock["selected_rows"], stock["owners"])
    raise ValueError("Unenrolled source")


def compare(empties, installed, ids, session):
    grouped = defaultdict(list)
    for row in empties:
        grouped[tuple(row["stream"])].append(row)
    scored = []
    for key, group in sorted(grouped.items()):
        count = sum(row["triggered"] for row in group)
        even_lanes = {tuple(group[((2*i+1)*len(group))//(2*count)]["lane"]) for i in range(count)}
        for row in group:
            opportunity = tuple(row["lane"])
            old = installed[opportunity]
            if old["valid_start_counter"] != row["counter"] or stream(old) != key:
                raise ValueError("Installed factor matches a different original hardware opportunity")
            owner_key = opportunity if session is None else observation_id(session, old)
            owners = {arm: owner_key in ids[arm] for arm in ARMS}
            if any(owners.values()) and not old["candidates"]:
                raise ValueError("Owner join claims an originally empty lane")
            scored.append(dict(row, installed_factors=len(old["candidates"]), installed_owner=owners,
                               even=opportunity in even_lanes, uniform_probability=count/len(group)))
    return scored


def totals(scored):
    trigger = [row for row in scored if row["triggered"]]
    even = [row for row in scored if row["even"]]
    counts = dict(short_empties=len(scored), checks=len(trigger),
                  lost_installed_lanes=sum(bool(row["installed_factors"]) for row in scored),
                  lost_installed_factors=sum(row["installed_factors"] for row in scored),
                  triggered_installed_lanes=sum(bool(row["installed_factors"]) for row in trigger),
                  triggered_installed_factors=sum(row["installed_factors"] for row in trigger),
                  triggered_installed_empty=sum(not row["installed_factors"] for row in trigger),
                  evenly_installed_lanes=sum(bool(row["installed_factors"]) for row in even),
                  uniform_expected_installed_lanes=sum(row["uniform_probability"] for row in scored if row["installed_factors"]))
    counts["owners"] = {
        arm: dict(lost=sum(row["installed_owner"][arm] for row in scored),
                  triggered=sum(row["installed_owner"][arm] for row in trigger),
                  evenly=sum(row["installed_owner"][arm] for row in even),
                  uniform_expected=sum(row["uniform_probability"] for row in scored if row["installed_owner"][arm]))
        for arm in ARMS}
    return counts


def costs(case, clocks, calls, added):
    if clocks is None:
        # The first-use dense receipt did not separate full and short CPU.
        docs = historical("receiver-mix-budget.json")["measured"]
        short = historical("short-rank-transfer-DS30-0008.json.gz")["ns_per_lane"]["sparse"]["cpu"]*1e-9
        prices = {row["name"]: dict(row["cpu_s_per_call"], short_primary=short) for row in docs}
        source = "sealed cross-recording full-20 donors and measured same-member sparse short CPU"
    else:
        expect = {"full": calls["full"], "short_primary": calls["short"]}
        if clocks["native_calls"] != expect or clocks["short_primary_sha256"] != SPARSE or clocks["installed_sha256"] != FULL:
            raise ValueError("Native clock denominators or receiver binary changed")
        prices = {case: {slot: clocks["native_cpu_ns"][slot]*1e-9/n for slot, n in expect.items()}}
        source = "same acquisition's measured mean CPU per lane"
    return {name: dict(full_s=cost["full"], short_s=cost["short_primary"], full_to_short=cost["full"]/cost["short_primary"],
                       projected_extra_native_s=added*cost["full"], source=source) for name, cost in prices.items()}


def detached(scored, installed, sparse):
    proof = historical("attested-visit-detector-DS30-0163.json.gz")
    held = {lane(row): row for row in sparse["source"]["probes"]}
    audit = {}
    for entry in proof["visits"]:
        for row in entry["lanes"]:
            key = entry["visit_index"], row["named_20ms"]["receiver_id"]
            if (row["named_20ms"] != installed[key] or row["mixed_20_8"]["candidates"] != held[key]["candidates"]):
                raise ValueError("Detached genuine candidate data differ from the sealed original member")
            audit[key] = len(row["named_continuation"]["probe_before_continuation"]["candidates"])
    nominated = [row for row in scored if row["triggered"]]
    measured = [audit[tuple(row["lane"])] for row in nominated if tuple(row["lane"]) in audit]
    return dict(signed_detached_lanes=len(audit), nominated_with_full_alternatives=len(measured),
                nominated_with_nonempty_alternatives=sum(bool(n) for n in measured),
                nominated_total=len(nominated))


def score(seal_path, seal_pin):
    sealed = checked(seal_path, seal_pin)
    if canonical_digest(sealed) != canonical_digest(prescription()):
        raise ValueError("Candidate-only sealed plan changed")
    results = {}
    for case, spec in sealed["plans"].items():
        sparse, _, clocks = candidates(case)
        stock, session, ids = named(case, sparse)
        bind(stock, sparse)
        identity = ("last_sample_counter", "clock_anchor", "delivery_clocks")
        support = ("window_count", "processed_windows", "invalid_capture", "excluded_windows")
        if (any(sparse[k] != stock[k] for k in identity) or
                any(sparse["provenance"][k] != stock["provenance"][k] for k in support)
                or stock["provenance"]["detector_sha256"] != "sha256:"+FULL):
            raise ValueError("The paired 20 ms and sparse packets have unequal original scopes")
        stock_rows = {lane(row): row for row in stock["source"]["probes"]}
        marked = compare(spec["empties"], stock_rows, ids, session)
        counts = totals(marked)
        calls = Counter(spec["apertures"])
        radios = {}
        for radio in sorted({row[1] for row in stock_rows}):
            radios[radio] = totals([r for r in marked if r["lane"][1] == radio])
            radios[radio]["all_short_calls"] = sum(mode == "short" and row["receiver_id"] == radio for mode, row in
                                                  zip(spec["apertures"], sparse["source"]["probes"], strict=True))
        results[case] = dict(issued=spec["issued"], calls=calls, totals=counts, radios=radios,
                             shortlisted=[r for r in marked if r["triggered"]], installed_sha256=canonical_digest(stock),
                             preheld_sha256=spec["preheld_sha256"], charge=costs(case, clocks, calls, counts["checks"]))
        if case == "DS30-0163":
            results[case]["detached_full"] = detached(marked, stock_rows, sparse)
    return dict(schema_version=1, plan_sha256=seal_pin, results=results)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("plan", "score"))
    cli.add_argument("--sealed-plan", type=Path)
    cli.add_argument("--seal-sha256")
    args = cli.parse_args()
    if args.action == "score" and (args.sealed_plan is None or args.seal_sha256 is None):
        cli.error("Scoring requires the independently sealed candidate-only plan")
    answer = prescription() if args.action == "plan" else score(args.sealed_plan, args.seal_sha256)
    print(json.dumps(answer, sort_keys=True, indent=2, allow_nan=False))
