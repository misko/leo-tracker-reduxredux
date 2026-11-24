"""Verify the two independently identified North publications after the clocks stop."""

from hashlib import sha256
import gzip
from io import BytesIO
import json
import math
from pathlib import Path
import sys

from .north_direct_multichunk import HERE, NAMED, OFFER_PIN, SOURCE, check_native_authority, normalized_native


SCORE_KEY = HERE.parent/"regional-release/scoring-key.json"
SCORE_KEY_SHA = "0bda865a20e62852220a9ab8df63895a449bf203a2deb5370920dc3ce215d37d"
TITLE_ROWS = {
    "ordinary": {"ch1-4-all": (33, 63), "ch5-8-all": (33, 63), "ch1-4-unassociated": (33, 63),
                 "ch5-8-unassociated": (33, 63), "ch1-4-residuals": (7, 25), "ch5-8-residuals": (7, 25),
                 "track-rms": (5, 25), "position": (7, 26)},
    "packed": {"ch1-4-all": (36, 67), "ch5-8-all": (36, 67), "ch1-4-unassociated": (36, 67),
               "ch5-8-unassociated": (36, 67), "ch1-4-residuals": (28, 46), "ch5-8-residuals": (28, 46),
               "track-rms": (71, 91), "position": (21, 40)},
}


def document(path):
    return json.loads(path.read_bytes())


def omit(data, *names):
    return {key: value for key, value in data.items() if key not in names}


def matched_images(current, reference, actual, historical, kind):
    import numpy as np
    from PIL import Image
    from leo.contracts.digests import sha256_digest
    from leo.contracts.fast_standard_analysis import PLOTS

    if [row["name"] for row in current] != list(PLOTS) or [row["name"] for row in reference] != list(PLOTS):
        raise ValueError("A complete route must provide its eight figure names in order")

    def inspect(read, item):
        png = read(item)
        if sha256_digest(png) != item["sha256"] or len(png) != item["byte_count"]:
            raise ValueError("The figure content differs from its independently sealed digest")
        with Image.open(BytesIO(png)) as image:
            if image.format != "PNG":
                raise ValueError("Expected a decoded PNG")
            rgba = np.asarray(image.convert("RGBA"))
            return rgba, dict(file_sha256=item["sha256"], decoded_rgba_sha256=sha256_digest(rgba.tobytes()),
                              size=list(image.size), byte_count=len(png))

    result = {}
    for item, control in zip(current, reference, strict=True):
        name = item["name"]
        (a, this), (b, before) = inspect(actual, item), inspect(historical, control)
        if a.shape != b.shape:
            raise ValueError("The figure dimensions changed")
        y, x = np.where(np.any(a != b, axis=2))
        bbox = None if len(y) == 0 else [int(x.min()), int(y.min()), int(x.max()), int(y.max())]
        lo, hi = TITLE_ROWS[kind][name]
        if bbox and not lo <= bbox[1] <= bbox[3] <= hi:
            raise ValueError(f"Pixels outside the capture title differed for {kind}/{name}: {bbox}")
        result[name] = dict(current=this, reference=before, differing_pixels=len(y), bounding_box=bbox,
                            identical_outside_title=True)
    return result


def physical_owners(native, selected, arms):
    from leo.contracts.digests import canonical_digest

    source = native["source"]
    physical = {}
    for probe in source["probes"]:
        if not any(c["passed_fractional_margin_gate"] for c in probe["candidates"]):
            continue
        rx, sample = probe["receiver_id"], probe["valid_start_counter"]
        text = f"{source['session_id']}:{rx}:{sample}"
        oid = "sha256:" + sha256(text.encode()).hexdigest()
        if oid in physical:
            raise ValueError("A signed observation identity maps to more than one receiver window")
        physical[oid] = [probe["visit_index"], rx, probe["channel"], sample]
    rows = {}
    for arm, items in selected.items():
        owners = {oid: norad for oid, norad, role in items}
        if (len(owners) != arms[arm]["associated_points"] or len(items) != len(owners)
                or canonical_digest(owners) != arms[arm]["owner_sha256"]):
            raise ValueError("Published owner digests and ordered rows differ")
        rows[arm] = [[*physical[oid], norad, role] for oid, norad, role in items]
    return rows


def artifacts(root, run, kind):
    from leo.contracts.fast_standard_analysis import standard_model, validate
    from leo.contracts.position_grid import binding
    from leo.contracts.position_path import validate as validate_path
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    from .live_adaptive_grid_entry import check_sample, read_manifest, read_sidecar, research_folder

    if kind == "ordinary":
        store = FastStandardAnalysisStore(root)

        def png(item):
            return store.artifact(run, item["name"], item["sha256"])

        return store.detail(run), store.position_grid(run), store.position_path(run), png
    manifest = read_manifest(root, run)
    publication = validate({"schema_version": 3, **manifest["publication"]}, model=standard_model(run))
    grid = read_sidecar(root, run, "sample")
    path = validate_path(read_sidecar(root, run, "path"), publication)
    check_sample(grid, publication)
    if grid["binding"] != binding(publication):
        raise ValueError("The adaptive points do not bind the published capture and both owner sets")
    folder = research_folder(root, run)

    def png(item):
        return (folder/(item["sha256"][7:]+".png")).read_bytes()

    return publication, grid, path, png


def solution(root, run, terminal_pin, kind, truth):
    from leo.contracts.digests import canonical_digest

    native_path, = root.glob("fast-scan-automatic-work/*/detections.json")
    terminal_path = root/"fast-scan-automatic-work"/run/"terminal.json"
    native, terminal = document(native_path), document(terminal_path)
    pub, grid, path, png = artifacts(root, run, kind)
    if (pub["state"] != "complete" or set(terminal["arms"]) != {"c0", "fitted_c"}
            or canonical_digest(terminal) != terminal_pin or pub["terminal_sha256"] != terminal_pin
            or terminal["native_sha256"] != canonical_digest(native) or pub["session_id"] != native["source"]["session_id"]):
        raise ValueError("Complete location evidence is not bound to its signed capture")

    def error_m(latlon):
        lat, lon = map(math.radians, latlon)
        a, b = map(math.radians, truth)
        h = math.sin((lat-a)/2)**2+math.cos(a)*math.cos(lat)*math.sin((lon-b)/2)**2
        return 12_742_017.6*math.asin(math.sqrt(h))

    arms = {arm: dict(endpoint=value["latlon"], position_error_m=error_m(value["latlon"]),
                      conditional_rf_rms_hz=value["rf_rms_hz"], figure_rf_rms_hz=pub["arms"][arm]["residual_rms_hz"],
                      observation_count=pub["arms"][arm]["associated_points"], owner_sha256=pub["arms"][arm]["owner_sha256"])
            for arm, value in terminal["arms"].items()}
    return native, terminal, pub, grid, path, png, arms


def packed_readback(root, authority):
    actual = document(root/"packed/verified-readback.json")
    wanted = authority["members"]
    records = actual["members"]
    if (actual["root_sha256"] != authority["archive_sha256"] or len(records) != len(wanted) or any(
            (row["seek_sha256"], row["original_decoded_sha256"], row["checks"]["full_checks"], row["encoded_blocks"])
            != (member["seek_sha256"], member["uncompressed_sha256"], member["window_count"], 2*member["window_count"])
            for row, member in zip(records, wanted, strict=True))):
        raise ValueError("The paid candidate did not independently validate the entire encoded and logical capture")
    return dict(verified_members=len(records), verified_encoded_blocks=sum(row["encoded_blocks"] for row in records),
                **{key: sum(row["checks"][key] for row in records) for key in records[0]["checks"]},
                decode_and_hash_cpu_ns=sum(row["decode"]["cpu_ns"] for row in records),
                decode_and_hash_wall_ns=sum(row["decode"]["wall_ns"] for row in records))


def score(root):
    from empty_bootstrap import checked
    from leo.contracts.digests import canonical_digest
    from north_strict_read import LEAN, LEAN_RAW, LEAN_RESULT, NAMED_REFERENCE
    from raw_cfo_north_trial import CUTOFF

    timing = document(root/"timing.json")
    if set(timing["arms"]) != {"ordinary", "packed"}:
        raise ValueError("Expected both paid capture and first-publication clocks")
    if timing["offer_sha256"] != OFFER_PIN:
        raise ValueError("Expected the original North containing offer")
    (truth,) = {tuple(item["truth"]) for item in json.loads(checked(SCORE_KEY, SCORE_KEY_SHA))["answers"].values()
                if item["recording"] == SOURCE.name}
    installed = json.loads(gzip.decompress(checked(HERE/"measurements/current-north-control.json.gz", NAMED_REFERENCE)))
    leap = json.loads(checked(LEAN/"verified-result.json", LEAN_RESULT))
    baseline = dict(ordinary=installed["new"]["verified"]["receipt"], packed=leap["receipt"])
    known_native = dict(ordinary=installed["new"]["native_sha256"], packed=leap["native_sha256"])
    if not all(installed["checked_fields"].values()) or not all(leap["checks"].values()):
        raise ValueError("Both previous publications must be independently authenticated")
    results = {}
    for kind, old in (("ordinary", NAMED), ("packed", LEAN/"containing")):
        worker = root/kind
        current = worker/"publication"
        receipt = json.loads((worker/"stdout").read_text().splitlines()[-1])
        if kind == "packed":
            receipt = document(current/"joint-research-receipt.json")["receipt"]
        previous = baseline[kind]
        run, last = receipt["run_id"], previous["run_id"]
        now, end, details, grid, path, png, arms = solution(current, run, receipt["terminal_sha256"], kind, truth)
        native, terminal, reference_details, reference_grid, reference_path, old_png, _ = solution(
            old, last, previous["terminal_sha256"], kind, truth)
        cost = timing["arms"][kind]
        binding = cost["authority"]
        index = current/"fast-scan-inputs"/(receipt["session_id"]+".json")
        check_native_authority(now, index, binding["archive_sha256"], timing["owned_window_sha256"])
        if (canonical_digest(native) != known_native[kind] or normalized_native(now) != normalized_native(native)
                or now["clock_anchor"]["before"]["realtime_ns"] != CUTOFF):
            raise ValueError("The current and earlier normalized signed packets differ")
        if (cost["publication"]["exit_code"] or receipt["decision"] != "complete" or receipt["window_count"] != 1200
                or receipt["region"] != previous["region"] or receipt["counts"] != previous["counts"]
                or omit(end, "native_sha256", "session_id") != omit(terminal, "native_sha256", "session_id")
                or omit(grid, "binding", "elapsed_seconds", "refinement_cpu_s", "sample_cpu_s")
                != omit(reference_grid, "binding", "elapsed_seconds", "refinement_cpu_s", "sample_cpu_s")
                or omit(path, "binding") != omit(reference_path, "binding")
                or any(omit(value, "owner_sha256") != omit(reference_details["arms"][arm], "owner_sha256")
                       for arm, value in details["arms"].items())):
            raise ValueError("The retained scientific evidence differs from its independent North control")
        images = matched_images(details["artifacts"], reference_details["artifacts"], png, old_png, kind)
        measured = dict(arms=arms, figures=images, grid_points=grid["evaluated_points"],
                        normalized_native_sha256=canonical_digest(normalized_native(now)), current_native_sha256=canonical_digest(now),
                        reference_native_sha256=known_native[kind], terminal_sha256=receipt["terminal_sha256"],
                        normalized_terminal_sha256=canonical_digest(omit(end, "native_sha256", "session_id")),
                        grid_sha256=canonical_digest(omit(grid, "binding", "elapsed_seconds", "refinement_cpu_s", "sample_cpu_s")),
                        path_sha256=canonical_digest(omit(path, "binding")), cutoff_utc_ns=CUTOFF)
        if kind == "packed":
            a, b = (document(pub/"joint-research-receipt.json") for pub in (current, old))
            rows = physical_owners(now, a["selected_rows"], details["arms"])
            previous_rows = physical_owners(native, b["selected_rows"], reference_details["arms"])
            if rows != previous_rows or a["route"] != b["route"] or a["selected_roles"] != b["selected_roles"]:
                raise ValueError("Ordered physical owners, roles or exact publication route changed")
            phases = document(current/"unified-short-bootstrap.json")
            old_raw = json.loads(checked(old/"unified-short-bootstrap.json", LEAN_RAW))
            if (phases["receiver_recipe"] != old_raw["receiver_recipe"] or phases["raw_acquisitions"] != 1
                    or phases["verified_handoffs"] != 1 or phases["causal_cutoff_utc_ns"] != CUTOFF):
                raise ValueError("The mixed schedule, authentic raw handoff or time cutoff changed")
            measured.update(phases=phases["phases"], readback=packed_readback(root, binding),
                            ordered_physical_owners_sha256=canonical_digest(rows), packed_owner_rows=len(rows["c0"]),
                            phase_state_sha256=grid["phase_state_sha256"], raw_route=a["route"],
                            detector_calls=phases["receiver_audit"]["native"]["native_calls"])
        results[kind] = measured
    a, b = (timing["arms"][arm]["total"]["wall_ns"]/1e9 for arm in ("ordinary", "packed"))
    return dict(source=str(SOURCE), timing=timing, results=results, speedup=a/b, needed_savings_s={"1.6x": b-a/1.6, "2x": b-a/2})


if __name__ == "__main__":
    result = score(Path(sys.argv[1]))
    with Path(sys.argv[2]).open("x") as stream:
        json.dump(result, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
