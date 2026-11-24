"""Account for lossless packed first analysis from frozen clocks and signed extents."""

from collections import Counter
import gzip
from hashlib import sha256
import json
from math import fsum
from pathlib import Path
from statistics import median
import sys

from all_full_receiver_frontier import PINS as FIELD_PINS, load
from first30_empty_call_roof import SPARSE, wall_gate
from field_speed_reachability import checked


HERE = Path(__file__).resolve().parent
ROWS = "2994fe3bd068dc661fb7c4a6f9667e370218acae226106f7dd0b05636d71f8c5"
SEAL = "84fc1193f55485f66a20b703fc52540fb8c94301937769759e4ed07a75b3af92"
MANIFEST = "a4ce879975be0593f1adeb7c106f31660c6c423f17e2c7858985244530dc0eb8"
PINS = {
    "eight-first-use.json.gz": "cd2b81b6e628ef6c42db0c2b6684b7186fb0f1f014553fbde4d358e151b7c898",
    "eight-first-use-held.json.gz": "d83d09a6e54a6e5b15d0fdfb296fe475ccff47b79660ed1b05640d881b6b3a81",
    "seekable-eight-raw.json.gz": "fd9905df130cf94c157efdc3ce5ee2b2cc57968a5dd077fd814f105701000300",
    "integrated-packed-full.json.gz": "de21badbdc5c310748401bad3ca485463c49d633e016b4317b87f7ac9c5287be",
    "integrated-packed-cost.json": "7b7726fac74294b1a4564048a63b1f2ef3bfb82ef977e42643a868f4c33546e9",
    "strict-cairo-0016.json.gz": "92eb659eeb74b1e1ec90cdf083673fb75f9e4640324aaf0cd976b143337e64a7",
}
FULL = 1_600_000
SHORT = 640_000
MEMBER = 64 * FULL
DIRECT_LIMIT = 4096
MEMBER_FIELDS = {
    "chunk_index": "chunk_index", "first_sequence": "first_sequence", "window_count": "windows",
    "compressed_bytes": "encoded", "uncompressed_bytes": "decoded", "compressed_sha256": "member_sha256",
    "uncompressed_sha256": "raw_sha256", "index_sha256": "index_sha256",
}


def saved(name):
    body = checked(HERE / "measurements" / name, PINS[name])
    return json.loads(gzip.decompress(body) if name.endswith(".gz") else body)


def descriptor(acquisition):
    clock, = (v for k, v in acquisition["released_member_descriptors"].items() if k.startswith("iq-"))
    return clock


def prospective(dense, held, seekable):
    old = seekable["dense_named_and_verified_held_named"]["result"]
    clean = descriptor(old["stock"])
    records = []
    for archive in (dense, held):
        result = archive["result"]
        if not all(result[k] for k in ("exact_20_8_factors_and_selector", "exact_opportunities", "no_backing_waveform_access")):
            raise ValueError("First-use comparison requires the same verified detector input scope")
        for order, arm in enumerate(result["arms"], 1):
            ordinary, packed = (arm[k] for k in ("ordinary8", "packed8"))
            stock, newer = ordinary["acquisition"], packed["acquisition"]
            if (stock["detector_sha256"] != newer["detector_sha256"]
                    or stock["original_member_sha256"] != newer["original_member_sha256"]
                    or any(a["reads"]["decoded_bytes"] != MEMBER or a["reads"]["full_checks"] != 64 for a in (stock, newer))
                    or newer["reads"]["encoded_blocks_preverified"] != 128):
                raise ValueError("First readback must verify both apertures of all windows")
            if result["case"] == "DS30-0008" and old["stock"]["original_member_sha256"] != stock["original_member_sha256"]:
                raise ValueError("Dense historical clean descriptor must refer to the exact same member")
            encoded = descriptor(stock)
            clocks = {}
            for key in ("wall_ns", "cpu_ns"):
                raw = stock["timing"][key]-newer["timing"][key]
                clocks[key] = dict(ordinary_acquire=stock["timing"][key], packed_acquire=newer["timing"][key],
                                   ordinary_descriptor=encoded[key], historical_dense_descriptor=clean[key],
                                   acquire_saving=raw, normalized_acquire_saving=raw-encoded[key]+clean[key],
                                   write_saving=ordinary["capture"]["timing"][key]-packed["capture"]["timing"][key],
                                   joint_saving=ordinary["through_first_complete_verified_output"][key]-packed["through_first_complete_verified_output"][key])
            records.append(dict(case=result["case"], order=order, clocks=clocks,
                                detector=archive["binding"]["receiver_recipe"]["shortened_sha256"],
                                ordinary_encoded=stock["reads"]["payload_bytes"], packed_encoded=newer["reads"]["payload_bytes"]))
    return records


def footprint(chunks, witness):
    total = Counter()
    final = None
    for offset, (signed, paid) in enumerate(zip(chunks, witness, strict=True)):
        if (not paid["complete_encoded_auth"]
                or any(signed[k] != paid[v] for k, v in MEMBER_FIELDS.items())):
            raise ValueError("The paid reader does not match the ordered signed manifest")
        count, size = paid["windows"], paid["decoded"]
        if not (0 < count <= 64 and 0 <= size <= count*FULL and 0 <= paid["largest_sample_window_bytes"] <= FULL):
            raise ValueError("Unexpected stereo member geometry")
        total.update(members=1, visits=count, decoded=size, encoded=paid["encoded"])
        variable = size != count*FULL
        if variable:
            total.update(variable=1, variable_decoded=size)
        if count < 64:
            kind = "final" if offset == len(chunks)-1 else "nonfinal"
            total.update({f"{kind}_partial": 1, f"{kind}_partial_decoded": size})
            if variable:
                total[f"{kind}_partial_variable"] += 1
        if offset == len(chunks)-1:
            final = dict(visits=count, decoded=size, encoded=paid["encoded"])
    if not total["members"]:
        raise ValueError("Expected a nonempty recording")
    return dict(total), final


def case_budget(case, amount):
    modes = case["modes"]
    full, short = (modes[mode].get("visits", 0) for mode in ("full", "short_primary"))
    admitted = full + short
    requested = full*FULL + short*SHORT
    native = fsum(v["elapsed_ns"]/1e9 for v in modes.values())
    paid = case["acquisition"]["elapsed_s"]
    if not (case["admitted"] == admitted <= amount["visits"] == case["issued"]
            and requested <= amount["decoded"] and 0 <= native <= paid <= case["paid_candidate_s"]):
        raise ValueError("Requested apertures and nested acquisition must fit the signed source")
    return dict(requested_decoded=requested, skipped_decoded=amount["decoded"]-requested,
                native_wall_s=native, outer_acquisition_s=paid-native,
                direct_geometry=amount["visits"] <= DIRECT_LIMIT and not amount.get("variable"))


def read_population(snapshot, campaign):
    field = load("first30-empty-call-roof")
    seal = json.loads(checked(snapshot / "rows-with-relocations-seal.json", SEAL))
    if field["rows_sha256"] != ROWS or seal["combined_sha256"] != "sha256:"+ROWS or len(field["cases"]) != 30:
        raise ValueError("Expected the same frozen 30-pair export")
    rows = {(r["case"], r["algorithm"]): r for r in map(json.loads, checked(snapshot / "rows-with-relocations.jsonl", ROWS).splitlines())}
    path = HERE.parents[1] / "2026_11_20_ds30_fast/dataset/manifest.json.gz"
    manifest = gzip.decompress(path.read_bytes())
    if sha256(manifest).hexdigest() != MANIFEST:
        raise ValueError("Signed DS30 dataset manifest changed")
    originals = {m["dataset_label"]: m for m in json.loads(manifest)["members"]}
    population = []
    for case in field["cases"]:
        row = rows[case["case"], "successor"]
        original = originals[case["case"]]
        if (not row["verified_pair"] or row["attempt_result_sha256"] != case["candidate_join_sha256"]
                or original["raw_authority_digest"] != row["manifest_raw_authority_sha256"]):
            raise ValueError("Original archive metadata does not bind the frozen enrolled pair")
        attempt = (campaign / row["attempt"]).resolve(strict=True)
        if not attempt.is_relative_to(campaign) or attempt.name != "result.json":
            raise ValueError("Only local official attempt metadata belongs in this assay")
        result = json.loads(checked(attempt, case["candidate_join_sha256"]))
        path = attempt.parent / "publication/legacy-original-acquisition.json"
        if not path.resolve(strict=True).is_relative_to(campaign):
            raise ValueError("Only local official acquisition metadata belongs in this assay")
        body = path.read_bytes()
        legacy = json.loads(body)
        raw = result["raw_identity"]
        authorized = dict(raw_authority=raw["raw_authority_sha256"], inventory=raw["inventory_sha256"],
                          session=raw["session_id"], windows=raw["window_count"])
        if (legacy["authority_mode"] != "verified-once" or legacy["verified_source"] != authorized
                or legacy["finished_raw_authority"] != authorized["raw_authority"]
                or raw["raw_authority_sha256"] != row["raw_authority_sha256"]
                or result["native_sha256"] != case["native_sha256"]):
            raise ValueError("Acquisition sidecar is for a different signed source")
        amount, final = footprint(original["raw_recording"]["chunks"], legacy["members"])
        decoded_work = sum(m["native_read_wall_ns"] + m["hash_wall_ns"] for m in legacy["members"])/1e9
        population.append(dict(case, amount=amount, final_member=final, **case_budget(case, amount),
                               decode_and_raw_hash_wall_s=decoded_work,
                               legacy_sha256=sha256(body).hexdigest(), raw_authority=authorized["raw_authority"],
                               signed_manifest_authority=original["raw_authority_digest"]))
    return population


def scenario(cases, credits):
    limit = [min(c["outer_acquisition_s"], credit) for c, credit in zip(cases, credits, strict=True)]
    value = wall_gate(cases, limit)
    return dict(value, capped_cases=sum(a != b for a, b in zip(credits, limit)),
                gap_to_half_total_s=value["candidate_s"]-fsum(c["paid_installed_s"] for c in cases)/2)


def assess(cases, donors, integrated, historical, conversion):
    positive = integrated["cases"]["DS30-0016"]
    result = positive["result"]["document"]
    admission = positive["admission"]["document"]
    stored = result["storage"]
    apertures = stored["apertures"]
    if (not result["qualified"] or result["receipts"]["receiver_recipe"]["shortened_sha256"] != SPARSE
            or not conversion["qualified"] or not conversion["conversion"]["independent_check"]
            or admission["conversion_sha256"] != conversion["admission"]["conversion_sha256"]
            or apertures["full"]*FULL+apertures["short_primary"]*SHORT != stored["decoded"]):
        raise ValueError("Prepared full case must use the exact field sparse detector")
    decoded = admission["issued"]*FULL
    strict = result["receipts"]["phases"]["authenticated_raw_acquisition"]["elapsed_s"]
    old = [p["observed_acquisition_s"][0] for p in historical["modeled_integrated"].values()]
    rates = [(v-strict)/(decoded-stored["decoded"]) for v in old]
    readiness = admission["source_check"]["elapsed_s"]
    conversion_receipt = conversion["conversion"]
    legacy_cost = conversion_receipt["total_including_compiler_and_verification"]["wall_ns"]/1e9
    compile_once = conversion_receipt["compiler"]["wall_ns"]/1e9
    migration = [(legacy_cost-compile_once)*c["amount"]["decoded"]/decoded for c in cases]
    migration[0] += compile_once
    models = {"observed": scenario(cases, [0.]*len(cases))}
    models["free_original_decode_and_raw_hash"] = scenario(cases, [c["decode_and_raw_hash_wall_s"] for c in cases])
    for scope in ("direct_geometry", "all_if_supported"):
        volumes = [c["amount"]["decoded"]/MEMBER if c["direct_geometry"] or scope == "all_if_supported" else 0. for c in cases]
        for treatment in ("acquire_saving", "normalized_acquire_saving"):
            samples = [d["clocks"]["wall_ns"][treatment]/1e9 for d in donors]
            for label, ms in (("low", min(samples)), ("median", median(samples)), ("high", max(samples))):
                models[f"{scope}_{treatment}_{label}"] = scenario(cases, [ms*n for n in volumes])
    for rate, name in ((min(rates), "low"), (max(rates), "high")):
        prepared = [min(c["outer_acquisition_s"], rate*c["skipped_decoded"])-readiness for c in cases]
        models[f"prepared_{name}"] = scenario(cases, prepared)
        models[f"legacy_first_{name}"] = scenario(cases, [p-m for p, m in zip(prepared, migration, strict=True)])
        models[f"prepared_native_free_{name}"] = wall_gate(cases, [p+c["native_wall_s"] for p, c in zip(prepared, cases, strict=True)])
    census = Counter()
    for c in cases:
        census.update(c["amount"])
    return dict(scenarios=models, census=dict(census), direct_cases=[c["case"] for c in cases if c["direct_geometry"]],
                direct_decoded=fsum(c["amount"]["decoded"] for c in cases if c["direct_geometry"]),
                requested_decoded=sum(c["requested_decoded"] for c in cases), skipped_decoded=sum(c["skipped_decoded"] for c in cases),
                excessive_visits=sum(c["issued"] > DIRECT_LIMIT for c in cases), variable_cases=sum(bool(c["amount"].get("variable")) for c in cases),
                native_work=fsum(c["native_wall_s"] for c in cases), outside_acquisition=fsum(c["outer_acquisition_s"] for c in cases),
                prepared_donor=dict(total_original_decoded=decoded, strict_decoded=stored["decoded"], strict_encoded=stored["encoded"],
                                    strict_acquisition_s=strict, original_acquisition_s=old, seconds_per_omitted_byte=rates,
                                    ready_s=readiness, conversion_s=legacy_cost, compile_once_s=compile_once),
                legacy_conversion_projected_s=fsum(migration),
                case_0049=next(dict(case=c["case"], native_free_to_half_s=c["paid_candidate_s"]-c["native_wall_s"]-c["paid_installed_s"]/2,
                                    prepared_savings_s=[r*c["skipped_decoded"]-readiness for r in rates]) for c in cases if c["case"] == "DS30-0049"))


def run(snapshot, campaign):
    cases = read_population(snapshot.resolve(strict=True), campaign.resolve(strict=True))
    dense, held, seek = (saved(f"{n}.json.gz") for n in ("eight-first-use", "eight-first-use-held", "seekable-eight-raw"))
    donors = prospective(dense, held["data"]["held"], seek)
    integrated = saved("integrated-packed-full.json.gz")
    old = saved("integrated-packed-cost.json")
    conversion = saved("strict-cairo-0016.json.gz")
    return dict(schema="packed-first30-intake-v1", inputs=dict(ROWS=ROWS, SEAL=SEAL, MANIFEST=MANIFEST,
                **PINS, **{"first30-empty-call-roof.json.gz": FIELD_PINS["first30-empty-call-roof"]}), cases=cases,
                sources=donors, selective_member=old["sampled_member_costs"], **assess(cases, donors, integrated, old, conversion))


if __name__ == "__main__":
    print(json.dumps(run(Path(sys.argv[1]), Path(sys.argv[2])), sort_keys=True, allow_nan=False))
