"""Independently verify and compare full publications from the sealed panel."""

import json
import sys
from io import BytesIO
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from time import monotonic, process_time

from combined_small_panel import (
    CASES,
    CONTROL,
    REPO,
    TRIAL,
    check,
    digest,
    paired,
    reference,
    verify_ready,
    write,
)

REFERENCES = {
    "DS30-0016": ("score01", "68803c12437fe159278ca31183e9e1a6632e601310eead70f0be71a10e358648"),
    "DS30-0107": ("score02", "173acbdfbbe538955a0dee46a0fe486273444f0a17717716a89a9ac01e2d1793"),
}
SITE_BOOK = REPO / "reports/2026_11_21_ds30_full/reference-audit.json"
SITE_PIN = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
ARMS = ("c0", "fitted_c")


def read(path):
    return json.loads(path.read_bytes())


def verifier_paths():
    # Verifier imports do not share the timed workers' interpreter or facade.
    sys.path[:0] = [str(REPO / "src"), str(REPO)]


def operands(inputs, case):
    from leo.contracts.algo08_region import Algo08Region

    return inputs | dict(
        expected_admitted=CASES[case]["admitted"],
        offered_region=Algo08Region.parse(read(Path(inputs["offer"]))).document(),
    )


def products(output, verified, owners):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    evidence = verified["evidence"]
    run = evidence["receipt"]["run_id"]
    store = FastStandardAnalysisStore(output)
    if verified["outcome"] == "withheld":
        if (
            verified["figures"]
            or owners
            or store.position_grid(run) is not None
            or store.position_path(run) is not None
            or any(
                any(value.get(key) is not None for key in ("latlon", "rf_rms_hz"))
                for value in evidence["arms"].values()
            )
        ):
            raise ValueError("A withheld result contains positive inference products")
        return dict(grid=None, path=None, ordered_owners={}, publication_arms={})
    grid, path = store.position_grid(run), store.position_path(run)
    arms = store.detail(run)["arms"]
    if (
        set(arms) != set(ARMS)
        or (len(verified["figures"]), len(grid["points"])) != (8, 179)
        or not path["stages"]
        or not grid["matched_c_grid"]
        or set(owners) != set(ARMS)
    ):
        raise ValueError(
            "Expected both calibrated fits, the full grid/path and eight decoded figures"
        )
    for arm, rows in owners.items():
        if (
            not rows
            or len({row[0] for row in rows}) != len(rows)
            or canonical_digest({row[0]: row[1] for row in rows}) != evidence["owners"][arm]
        ):
            raise ValueError("Ordered owners failed independent publication digest verification")
    return dict(grid=grid, path=path, ordered_owners=owners, publication_arms=arms)


def checked_publication(work, role, case, inputs, clock):
    t = monotonic(), process_time()
    verifier_paths()
    output = work / "publication"
    pin = CONTROL if role == "charted" else TRIAL
    verified = paired.publication(
        output, work, "successor", operands(inputs, case), clock, {"sha256": pin}
    )
    native = read(output / "unified-short-bootstrap.json")
    terminal = read(output / "exact-named-raw-witness.json")
    if (
        verified["outcome"] != CASES[case]["decision"]
        or native["native_sha256"] != verified["native_sha256"]
        or native["raw_acquisitions"] != 1
        or native["verified_handoffs"] != 1
        or native["scientific_imports_before"]
    ):
        raise ValueError(
            "The matched raw process did not preserve the registered acquisition and decision"
        )
    acquisition = read(output / "legacy-original-acquisition.json")
    if (
        acquisition["verified_source"]
        != dict(
            windows=inputs["authority"]["window_count"],
            session=inputs["authority"]["session_id"],
            inventory=inputs["authority"]["inventory_sha256"],
            raw_authority=inputs["authority"]["raw_authority_sha256"],
        )
        or acquisition["authority_mode"] != "verified-once"
    ):
        raise ValueError("Published receiver evidence fails original authenticated scope")
    details = products(output, verified, terminal["evidence"]["owner_rows"])
    scope = dict(
        phases=native["phases"],
        prefetch=native["prefetch"],
        build=pin,
        process=clock,
        solver_render=terminal.get("timing"),
        worker_evidence=terminal.get("verification"),
        verified_member_scopes=acquisition["members"],
        acquisition_setup=acquisition["setup"],
        detector_route=native["route"],
        graph_proof=native["graph_proof"],
        receiver_audit=native["receiver_audit"],
        recipe=native["held_anchor_route"]["receiver_recipe"],
    )
    if role == "trial":
        scope["features"] = read(output / "combined-small-panel-witness.json")
        scope["slots"] = read(output / "prefetch-snapshots.json")
        if (
            scope["features"]["native_sha256"] != native["native_sha256"]
            or scope["slots"]["statistics"] != native["prefetch"]
        ):
            raise ValueError("The paid features or slots did not bind this publication")
    elif any(
        (output / name).exists()
        for name in ("combined-small-panel-witness.json", "prefetch-snapshots.json")
    ):
        raise ValueError("An opt-in artifact appeared in the ordinary control")
    numeric_cpu = native["total_before_receipt"]["cpu_s"]
    bound = "authenticated_bootstrap_only"
    if case == "DS30-0016":
        inner = read(work / "numeric-process.json")
        if inner["exit_code"] or not numeric_cpu <= inner["cpu_s"] <= clock["elapsed_s"]:
            raise ValueError("The inside-namespace meter did not observe the complete worker")
        scope["numeric_process"] = inner
        numeric_cpu = inner["cpu_s"]
        bound = "numeric_worker_through_exit"
    wall, cpu = monotonic() - t[0], process_time() - t[1]
    return (
        verified
        | details
        | scope
        | dict(
            verification=dict(wall_s=wall, cpu_s=cpu),
            verified_boundary=dict(
                wall_s=clock["elapsed_s"] + wall,
                cpu_s=numeric_cpu + cpu,
                cpu_scope=bound + "_plus_independent_verifier",
            ),
        )
    )


def installed_reference(case, inputs):
    from PIL import Image

    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.qualification import paired_publication as qualification

    stock, seal = reference(case)
    for path, pin in seal.items():
        check(stock / path, pin)
    receipt = json.loads((stock / "stock.stdout").read_text().splitlines()[-1])
    output = stock / "stock"
    qualification.verify_v3_publication(output, receipt)
    clock = read(stock / "stock-clock.json")["clock"]
    evidence = qualification.evidence(output, receipt, clock["started_unix_ns"], read_only=True)
    (native,) = (output / "fast-scan-automatic-work").glob("*/detections.json")
    paired.native_identity(
        read(native),
        inputs["authority"],
        CASES[case]["admitted"],
        qualification.V3_IDENTITY["detector_sha256"],
    )
    if (
        evidence["raw_authority"] != inputs["authority"]["raw_authority_sha256"]
        or receipt["region"] != operands(inputs, case)["offered_region"]
        or receipt["decision"] != CASES[case]["decision"]
    ):
        raise ValueError("Historical installed reference is a different scientific request")
    name, score_pin = REFERENCES[case]
    summary = json.loads(
        check(stock.with_name(stock.name.removesuffix("-01") + f"-{name}.json"), score_pin)
    )
    if summary["seal_sha256"] != CASES[case]["reference"] or not summary["qualified"]:
        raise ValueError("Historical installed reference score does not bind the verified repeat")
    result = summary["stock"]
    store = FastStandardAnalysisStore(output)
    if store.detail(receipt["run_id"])["input_sha256"] != canonical_digest(read(native)):
        raise ValueError("Historical installed reference has a different native handoff")
    figures = []
    for artifact in evidence["artifacts"]:
        name, pin = artifact["name"], artifact["sha256"]
        body = store.artifact(receipt["run_id"], name, pin)
        with Image.open(BytesIO(body)) as image:
            if image.format != "PNG":
                raise ValueError("Expected a reference PNG")
            sizes = list(image.size)
            pixels = digest(image.convert("RGBA").tobytes())
        figures.append(dict(name=name, sha256=pin, size=sizes, rgba_sha256="sha256:" + pixels))
    verified = dict(
        outcome=receipt["decision"],
        evidence=evidence,
        figures=figures,
        process=clock,
        native_sha256="sha256:" + digest(native.read_bytes()),
    )
    return verified | products(output, verified, result.get("owners", {}))


def normalized(document):
    return {
        key: value for key, value in document.items() if key not in ("binding", "elapsed_seconds")
    }


def grid_delta(old, new):
    from reports.ALGO08.v3.profiled_grid_0138_score import compare_maps, qualified_map

    try:
        changes = compare_maps(dict(old, binding={}), dict(new, binding={}))
    except ValueError as error:
        return dict(qualified=False, error=str(error))
    return dict(qualified=qualified_map(changes), calibrated=changes)


def km(left, right):
    a, b = map(radians, left)
    c, d = map(radians, right)
    hav = sin((a - c) / 2) ** 2 + cos(a) * cos(c) * sin((b - d) / 2) ** 2
    return 12742.0176 * asin(sqrt(min(1.0, max(0.0, hav))))


def compare(old, new, site):
    base, trial = old["evidence"], new["evidence"]
    if old["outcome"] != new["outcome"]:
        raise ValueError("A new mode changed the registered original decision")
    result = dict(
        same_native=old["native_sha256"] == new["native_sha256"],
        same_reason=base["reason"] == trial["reason"],
    )
    if new["outcome"] == "withheld":
        return result
    arms = {}
    for label in ARMS:
        a, b = (packet["arms"][label] for packet in (base, trial))
        lrows, rrows = (packet["ordered_owners"][label] for packet in (old, new))
        lmap, rmap = ({row[0]: row[1:] for row in rows} for rows in (lrows, rrows))
        common = lmap.keys() & rmap.keys()
        arms[label] = dict(
            endpoint_shift_km=km(a["latlon"], b["latlon"]),
            position_error_km=[km(site, x["latlon"]) for x in (a, b)],
            rf_rms_hz=[a["rf_rms_hz"], b["rf_rms_hz"]],
            identical_ordered_owners=lrows == rrows,
            old_owners=len(lrows),
            new_owners=len(rrows),
            retained_owners=len(common),
            changed_owner_or_role=sum(lmap[i] != rmap[i] for i in common),
        )
    figures = []
    if isinstance(old["figures"], list) and isinstance(new["figures"], list):
        for x, y in zip(old["figures"], new["figures"], strict=True):
            if x["name"] != y["name"]:
                raise ValueError("Changed standard figure order")
            figures.append(
                dict(
                    name=x["name"],
                    encoded_equal=x["sha256"] == y["sha256"],
                    decoded_equal=x["rgba_sha256"] == y["rgba_sha256"],
                    same_dimensions=x["size"] == y["size"],
                )
            )
    return result | dict(
        calibrations=arms,
        grid=grid_delta(old["grid"], new["grid"]),
        figures=figures,
        path_equal=normalized(old["path"]) == normalized(new["path"]),
    )


def score(root, ready_pin, *, selection=None):
    verifier_paths()
    ready = verify_ready(root, ready_pin)
    results = {}
    deferred = {}
    conditioning = {}
    for case, inputs in ready["cases"].items():
        if selection is not None and case != selection:
            continue
        area = root / case
        if (
            not (area / "case.json").is_file()
            and case == "DS30-0016"
            and inputs["residency"]["nonresident"]
        ):
            deferred[case] = dict(
                reason="incomplete passive residency", admission=inputs["residency"]
            )
            continue
        seal = read(area / "case.json")
        if seal["ready_sha256"] != ready_pin or seal["order"] != CASES[case]["order"]:
            raise ValueError("Matched run differs from the prospective order")
        results[case] = {
            role: json.loads(check(area / role / "verified.json", row["result_sha256"]))
            for role, row in seal["results"].items()
        }
        control, trial = (results[case][role] for role in ("charted", "trial"))
        if any(control[key] != trial[key] for key in ("raw_identity", "native_sha256", "recipe")):
            raise ValueError("The combined worker changed the signed native receiver")
        results[case]["installed"] = installed_reference(case, inputs)
        pin = seal["conditioning_sha256"]
        if pin:
            warm = json.loads(check(root / "condition/outcome.json", pin))
            conditioning[case] = dict(
                receipt=warm,
                verified_trial_wall_plus_preparation_s=trial["verified_boundary"]["wall_s"]
                + warm["elapsed_with_isolation_s"],
            )
    references = json.loads(check(SITE_BOOK, SITE_PIN))["cases"]
    comparisons = {}
    for case, arms in results.items():
        (site,) = (
            row["reference"]
            for row in references
            if row["dataset_label"] == case and row["authority_eligible"]
        )
        coordinates = site["latitude_deg"], site["longitude_deg"]
        comparisons[case] = dict(
            charted_trial=compare(arms["charted"], arms["trial"], coordinates),
            installed_trial=compare(arms["installed"], arms["trial"], coordinates),
        )
    print(
        write(
            root / "panel-score.json",
            dict(
                residency={key: x["residency"] for key, x in ready["cases"].items()},
                comparisons=comparisons,
                ready_sha256=ready_pin,
                results=results,
                deferred=deferred,
                conditioning=conditioning,
            ),
        )
    )
