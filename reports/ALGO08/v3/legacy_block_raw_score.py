"""Verify the original-identity legacy block pair and price paid preparation."""

from collections import Counter

from legacy_block_raw_0016 import ORDER, digest, runtime_pins, seal
from visit_frame_raw_0016 import read


def snapshot(target, log, request, producer, *, verify_renderer=None):
    from empty_bootstrap import bind_native
    from history_risk_residual_layout_0402 import media_identity, require_active
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_0016_best_score import position_sides

    from tools.pipeline_eval.qualification.paired_publication import evidence

    raw = read(target / "unified-short-bootstrap.json")
    witness = read(target / "exact-named-raw-witness.json")
    receipt = raw["receipt"]
    process = log["clock"]
    (native_file,) = target.glob("fast-scan-automatic-work/*/detections.json")
    native = read(native_file)
    bind_native(
        native,
        request["session"],
        request["inventory"],
        request["detector"][7:],
        expected=request["native"],
    )
    published = evidence(target, receipt, process["started_unix_ns"], read_only=True)
    if (
        process["exit_code"]
        or receipt["decision"] != "complete"
        or receipt["session_id"] != request["session"]
        or native["source"]["raw_recording_authority_digest"] != request["authority"]
        or published["raw_authority"] != request["authority"]
        or digest(native_file) != raw["native_sha256"]
        or raw["requested_offer_sha256"] != request["offer_sha256"]
        or raw["archive_root"] != request["archive"]["root"]
        or raw["causal_cutoff_utc_ns"] != request["cutoff_utc_ns"]
        or receipt["window_count"] != 808
        or receipt["counts"] != dict(processed=713, invalid_capture=95, skipped_fast_score=0)
        or raw["raw_acquisitions"] != 1
        or raw["verified_handoffs"] != 1
        or raw["scientific_imports_before"]
    ):
        raise ValueError(
            f"Original signed acquisition or paid physical scope changed in {target.name}"
        )
    for label in ("cache_before", "cache_after"):
        cache = log[label]
        if (
            cache["members"],
            cache["observed_members"],
            cache["observed_file_pages"],
            cache["cached_pages"],
            cache["unavailable"],
        ) != (28, 28, 242_675, 242_675, {}):
            raise ValueError(
                f"The original physical waveform scope was not resident: {target.name}"
            )
    inner = witness["evidence"]
    owners = inner["owner_rows"]
    verified_media = artifacts(target, receipt)
    if (
        set(owners) != {"c0", "fitted_c"}
        or len(verified_media["images"]) != 8
        or media_identity(verified_media["images"]) != media_identity(inner["images"])
        or any(
            canonical_digest({oid: label for oid, label, _ in rows}) != published["owners"][arm]
            or len({row[0] for row in rows}) != len(rows)
            for arm, rows in owners.items()
        )
        or any(verified_media[name] != inner["sidecars"][name] for name in ("grid", "path"))
        or (target / "render-scene.pickle").exists()
    ):
        raise ValueError(
            "Ordered owners and all eight standard products must verify without a scene export"
        )
    orbit = witness["ports"]["portable"]
    (attempt,) = orbit["attempts"]
    (transfer,) = orbit["transfers"]
    if (
        not attempt["guard"]
        or attempt["fallback"]
        or transfer["compatibility"]["fallback"]
        or transfer["loading"]["fallback"]
        or transfer["sha256"] != producer["artifact_sha256"]
        or transfer["producer_sha256"] != producer["producer_sha256"]
        or transfer["counts"]["sidecar_hit_bodies"] != producer["overlapping_bodies"]
    ):
        raise ValueError("Portable history-risk did not use the earlier trusted index")
    if verify_renderer is None:
        require_active(witness["ports"]["cairo_layout"])
    else:
        verify_renderer(witness["ports"])
    if (
        witness["ports"]["cairo_layout"]["original_recording_title"]
        != request["recording"].split("/")[-1]
    ):
        raise ValueError("The renderer used a different recording title")
    store = FastStandardAnalysisStore(target)
    positions = position_sides(store, receipt, verified_media)
    return dict(
        process=process,
        phases=raw["phases"],
        receipt=receipt,
        native_sha256=raw["native_sha256"],
        native_source={
            key: value
            for key, value in raw["receiver_audit"]["native"].items()
            if key not in ("native_cpu_ns", "native_wall_ns")
        },
        prefetch=raw["prefetch"],
        portable=orbit,
        history_risk=witness["solver_recipe"],
        timing=witness["timing"],
        ordered_owners=owners,
        published=published,
        positions=positions,
        images=verified_media["images"],
        renderer=witness["ports"]["cairo_layout"],
        detector_file_s=(native_file.stat().st_mtime_ns - process["started_unix_ns"]) / 1e9,
    )


def check_members(path, book):
    audit = read(path)
    plan, prep = book["plan"], book["preparation"]
    if (
        audit["custody_sha256"] != book["map_custody_sha256"]
        or audit["binary_sha256"] != prep["build"]["binary_sha256"]
    ):
        raise ValueError("Mixed reading did not use the frozen map and decoder pins")
    totals, apertures, native_blocks = Counter(), Counter(), Counter()
    for actual, sealed in zip(audit["members"], plan["members"], strict=True):
        if any(actual[key] != val for key, val in sealed.items()):
            raise ValueError("Mixed acquisition moved a member or changed signed custody")
        kind = "map" if sealed["map"] else "ordinary"
        if actual["kind"] != kind or actual["authenticated_encoded_bytes"] != sealed["encoded"]:
            raise ValueError("Every member must retain its original encoded authentication")
        totals.update(
            {
                f"{kind}_members": 1,
                f"{kind}_windows": sealed["windows"],
                f"{kind}_encoded_bytes": sealed["encoded"],
                f"{kind}_committed_bytes": actual["committed_bytes"],
            }
        )
        if kind == "map":
            apertures.update(actual["counts"])
            native_blocks.update(actual["spans"])
        elif actual["committed_bytes"] != sealed["decoded"]:
            raise ValueError(
                "Ordinary fallback must exhaust the whole decoded member and all signed rows"
            )
    if (
        totals["map_members"],
        totals["ordinary_members"],
        totals["map_windows"],
        totals["ordinary_windows"],
        totals["map_encoded_bytes"] + totals["ordinary_encoded_bytes"],
    ) != (5, 8, 320, 488, 991_734_597):
        raise ValueError("Measured mixed coverage differs from the frozen five-member plan")
    return dict(
        audit, totals=dict(totals), apertures=dict(apertures), native_blocks=dict(native_blocks)
    )


def score(root):
    from aperture_trial import write
    from history_risk_residual_layout_0402 import media_identity
    from publication_media_checks import verify_position_sidecars

    book = read(root / "admission.json")
    sealed = read(root / "prediction-seal.json")
    recovery_path = root / "recovery.json"
    recovery = read(recovery_path) if recovery_path.exists() else None
    measured_pins, observed_pins = (recovery or book)["sources"], runtime_pins()
    reviewer = "reports/ALGO08/v3/legacy_block_raw_score.py"
    if sealed != seal(root) or any(
        measured_pins[key] != pin for key, pin in observed_pins.items() if key != reviewer
    ):
        raise ValueError("One or more paid outputs or frozen sources changed")
    if recovery is not None:
        moved = {"indexed-clock.json", "indexed.stdout", "indexed.stderr"}
        if any(
            sealed["indexed-bootstrap/" + name if name in moved else name] != pin
            for name, pin in recovery["previous_seal"].items()
        ):
            raise ValueError("One or more artifacts from the previous launch changed")
    logs = {mode: read(root / f"{mode}-clock.json") for mode in ORDER}
    if any(logs[mode]["command"] != book["commands"][mode] for mode in ORDER):
        raise ValueError("Measured argv differs from the frozen matched pair")
    products = {
        mode: snapshot(root / mode, logs[mode], book["request"], book["producer"]) for mode in ORDER
    }
    original, indexed = (products[mode] for mode in ORDER)
    aperture = check_members(root / "indexed/legacy-map-acquisition.json", book)
    if (root / "ordinary/legacy-map-acquisition.json").exists():
        raise ValueError("The ordinary comparator unexpectedly used a detached map")
    fields = (
        "decision",
        "session_id",
        "run_id",
        "terminal_sha256",
        "region",
        "window_count",
        "counts",
    )
    if (
        any(original["receipt"][key] != indexed["receipt"][key] for key in fields)
        or any(
            original[key] != indexed[key]
            for key in (
                "native_sha256",
                "native_source",
                "ordered_owners",
                "positions",
                "history_risk",
            )
        )
        or any(
            original["published"][key] != indexed["published"][key]
            for key in ("raw_authority", "arms", "owners", "scientific_digests")
        )
        or media_identity(original["images"]) != media_identity(indexed["images"])
    ):
        raise ValueError("The paired scientific products or their recording identity changed")
    sidecars = verify_position_sidecars(
        root / "ordinary",
        root / "indexed",
        original["receipt"]["run_id"],
        original["images"],
        indexed["images"],
    )
    prep = book["preparation"]
    isolated = Counter()
    for piece in prep["members"]:
        isolated.update(piece["incremental"])
    price = {}
    for metric, ns in (("elapsed_s", "wall_ns"), ("cpu_s", "cpu_ns")):
        prepared = indexed["process"][metric]
        ordinary = original["process"][metric]
        full_preparation = prep["total"][metric] + (
            prep["build"]["compiler_cpu_s"] if metric == "cpu_s" else 0
        )
        added = isolated[ns] / 1e9 + prep["write_costs"][metric] + prep["build"]["clock"][metric]
        if metric == "cpu_s":
            added += prep["build"]["compiler_cpu_s"]
        price[metric] = dict(
            ordinary=ordinary,
            prepared=prepared,
            installed_prior=book["prior_installed"][metric],
            measured_full_preparation=full_preparation,
            isolated_map_work=added,
            first_use=prepared + full_preparation,
            first_use_only_incremental_if_common_validation=prepared + added,
            earlier_portable_preparation=book["prior_index_build"][metric],
            first_use_with_portable_build=prepared
            + full_preparation
            + book["prior_index_build"][metric],
            steady_saving=ordinary - prepared,
        )
    write(
        root / "result.json",
        dict(
            qualified=True,
            recovery=recovery,
            verifier=dict(measured=measured_pins[reviewer], scored=observed_pins[reviewer]),
            case=book["case"],
            admission=book,
            products=products,
            measured_input=aperture,
            sidecars=sidecars,
            prices=price,
            title=book["request"]["recording"].split("/")[-1],
            prediction_seal_sha256=digest(root / "prediction-seal.json"),
        ),
    )
