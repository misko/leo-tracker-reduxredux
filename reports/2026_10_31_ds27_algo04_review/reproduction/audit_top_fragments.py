"""Link ranked native IDs to retained ALGO03/04 annotation evidence; never fit."""

import argparse
from collections import Counter
import gzip
import io
import json
import math
from pathlib import Path

from rank_native_residuals import PERIOD_HZ, digest, published_owners, read_bound


def source_match(parent, fragment, target):
    parent, fragment, target = map(set, (parent, fragment, target))
    if not parent & target:
        return None
    relation = ("exact_parent" if parent == target else
                "target_subset_of_parent" if target <= parent else
                "bundle_contains_parent" if parent <= target else "partial_source_overlap")
    return dict(relation=relation, parent_overlap_points=len(parent & target),
                target_points=len(target), fragment_overlap_points=len(fragment & target),
                entire_fragment_covered=fragment <= target,
                disjoint_from_ranked_fragment=not bool(fragment & target))


def held_ids(target, native_tracks, lookup, split):
    """Return exact recorded target order only when native provenance proves it."""
    ids = target["observation_ids"]
    if len(ids) != len(set(ids)) or not set(ids) <= set(lookup):
        raise ValueError("Target IDs duplicate or are absent from native observations")
    if target.get("graph_bundle"):
        ordered = list(ids)
        times = [lookup[oid]["time_s"] for oid in ordered]
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("Bundle target order is not distinct increasing native time")
    else:
        matches = [t for t in native_tracks if set(ids) <= set(t["observation_ids"])]
        if not matches:
            raise ValueError("Cannot prove target order from a native parent")
        ordered = [oid for oid in matches[0]["observation_ids"] if oid in set(ids)]
        times = [lookup[oid]["time_s"] for oid in ordered]
        if any(b < a for a, b in zip(times, times[1:])):
            raise ValueError("Native parent target order is not increasing time")
    block, origin = split["block_s"], split.get("block_origin_s", 0)
    selected = set(split["held_blocks"])
    indices = [i for i, time in enumerate(times) if math.floor((time - origin) / block) in selected]
    if "target_held_indices" in split and indices != split["target_held_indices"]:
        raise ValueError("Stored held indices differ from recorded block assignment")
    return [ordered[i] for i in indices]


def compact_noise(value):
    keys = ("noise_screen_pass", "mean_z", "slope_z", "quadratic_bic_gain",
            "maximum_step_z", "lag1_acf")
    result = {k: value[k] for k in keys if k in value}
    for key in ("noise", "held_noise", "noise_screen"):
        if isinstance(value.get(key), dict):
            result[key] = {k: value[key][k] for k in keys if k in value[key]}
    return result


def annotation_evidence(document, protocol, tracks, observations, focus):
    lookup = {o["observation_id"]: o for o in observations}
    annotation = document["annotation"]
    result = dict(status=annotation["status"], annotated_norad_hypothesis=annotation.get("norad"),
                  minimum_margin=annotation.get("minimum_margin"), votes=annotation.get("votes", []),
                  hypothesis_only=True, graph_bundle=document.get("graph_bundle", False),
                  bundle_member_checks=document.get("bundle_member_checks"), folds=[])
    votes = {(v["seed"], v["arm"]): v for v in annotation.get("votes", [])}
    winners = []
    for fold in document.get("folds", []):
        seed, proposals = fold["seed"], fold.get("proposals", [])
        if not proposals:
            result["folds"].append(dict(seed=seed, status=fold.get("status", "no_retained_proposals")))
            continue
        for arm in ("c0", "fitted_c"):
            score_name = document.get("identity_score_name", "conditional_target")
            best = min(proposals, key=lambda p: p["arms"][arm]["scores"][score_name]["negative_twice_log_density"])
            winner = votes.get((seed, arm), {}).get("norad")
            if winner is not None and best["norad"] != winner:
                raise ValueError("Saved annotation winner differs from retained proposal scores")
            winners.append(best["norad"])
            value = best["arms"][arm]
            score = value["scores"][score_name]
            phase = value.get("phase_reference_check", {})
            row = dict(seed=seed, arm=arm, norad_hypothesis=best["norad"],
                candidate_index=best["candidate_index"], alias=best["alias"],
                conditional_target_rms_hz=score.get("rms_hz"),
                conditional_target_negative_twice_log_density=score.get("negative_twice_log_density"),
                final_phase_change_s=value.get("final_phase_change_s"),
                minimum_target_elevation_deg=value.get("minimum_target_elevation_deg"),
                target_phase_boundary_mass=value.get("target_phase_boundary_mass"),
                phase_outside_reference_window=phase.get("phase_outside_reference_window"),
                maximum_phase_overflow_s=phase.get("maximum_phase_overflow_s"),
                structured_screens=compact_noise(value) | compact_noise(score),
                vote=votes.get((seed, arm)), retained_held_residual_mapping="not_available")
            if "held_residual_hz" in score:
                try:
                    ids = held_ids(protocol["target"], tracks, lookup, fold["split"])
                    residual = score["held_residual_hz"]
                    if len(ids) != len(residual) or ("held_mean_hz" in score and len(score["held_mean_hz"]) != len(ids)):
                        raise ValueError("Held residual/mean vector length does not match exact held IDs")
                    row.update(retained_held_residual_mapping="exact_native_order_and_recorded_groups",
                        held_observation_ids=ids, held_times_s=[lookup[oid]["time_s"] for oid in ids],
                        held_residual_hz=residual, held_ranked_fragment_mask=[oid in focus for oid in ids])
                except (ValueError, KeyError, TypeError) as error:
                    row["retained_held_residual_mapping"] = "unproven: " + str(error)
            result["folds"].append(row)
    counts = Counter(winners)
    result["winning_norad_hypothesis_counts"] = dict(sorted(counts.items()))
    result["top_norad_hypothesis"] = (min(counts, key=lambda n: (-counts[n], n)) if counts else None)
    return result


def target_gate_details(family, focus):
    if family is None:
        return []
    if isinstance(family, list):
        return [row for f in family for row in target_gate_details(f, focus)]
    result = []
    for gate, diagnostic in zip(family.get("gates", []), family.get("diagnostics", []), strict=True):
        ids = gate.get("observation_ids")
        if ids is not None and not set(ids) & focus:
            continue
        result.append(dict(component=gate["component"], compatible=gate["compatible"],
            norad_hypothesis=gate.get("norad"), profile_RMS_hz=diagnostic.get("profile_RMS_hz"),
            profile_bias_hz=diagnostic.get("profile_bias_hz"), noise=diagnostic.get("noise"),
            minimum_elevation_deg=diagnostic.get("minimum_elevation_deg"),
            phase_map_s=family.get("phase_map_s"), continuous_phase_gate=family.get("continuous_phase_gate"),
            exact_fragment_membership_in_gate=ids is not None))
    return result


def shared_target_diagnostics(document, value, focus, observations):
    lookup = {o["observation_id"]: o for o in observations}
    result = []
    for diagnostic in value.get("target_diagnostics", []):
        entries = [e for e in document.get("target_entries", []) if e["component"] == diagnostic["component"]]
        if len(entries) != 1 or not set(entries[0]["observation_ids"]) & focus:
            continue
        ids = entries[0]["observation_ids"]
        item = dict(component=diagnostic["component"], norad_hypothesis=diagnostic.get("norad"),
                    profiled_RMS_hz=diagnostic["RMS_hz"], profile_bias_hz=diagnostic["bias_hz"],
                    mapping="unproven", RMS_definition="profiled/bias-removed, not raw")
        try:
            if not set(ids) <= set(lookup):
                raise ValueError("Shared target IDs absent from native source")
            ordered = sorted(ids, key=lambda oid: lookup[oid]["time_s"])
            times = diagnostic["times_s"]
            if len(set(lookup[oid]["time_s"] for oid in ordered)) != len(ordered):
                raise ValueError("Shared target timestamps are not unique")
            vectors = [diagnostic[k] for k in ("times_s", "CFO_hz", "predicted_CFO_hz", "residual_hz")]
            if any(len(v) != len(ordered) for v in vectors):
                raise ValueError("Shared diagnostic vector lengths differ from target IDs")
            if any(abs(t - lookup[oid]["time_s"]) > 1e-6 for t, oid in zip(times, ordered, strict=True)):
                raise ValueError("Shared diagnostic time does not match exact native ID")
            lifts = [v - lookup[oid]["measured_cfo_hz"] for v, oid in zip(diagnostic["CFO_hz"], ordered, strict=True)]
            if any(abs(v - round(v / PERIOD_HZ) * PERIOD_HZ) > 1e-4 for v in lifts):
                raise ValueError("Shared diagnostic CFO is not the same native alias")
            raw = [a - b for a, b in zip(diagnostic["CFO_hz"], diagnostic["predicted_CFO_hz"], strict=True)]
            bias_removed = diagnostic["residual_hz"]
            if any(abs(r - diagnostic["bias_hz"] - b) > 1e-6 for r, b in zip(raw, bias_removed, strict=True)):
                raise ValueError("Stored residual is not raw minus stored profile bias")
            item.update(mapping="exact_native_ids_times_and_alias", observation_ids=ordered, times_s=times,
                source_CFO_hz=diagnostic["CFO_hz"], prediction_CFO_hz=diagnostic["predicted_CFO_hz"],
                raw_residual_hz=raw, bias_removed_residual_hz=bias_removed,
                raw_RMS_hz=math.sqrt(sum(r * r for r in raw) / len(raw)),
                ranked_fragment_mask=[oid in focus for oid in ordered])
        except (KeyError, ValueError, TypeError) as error:
            item["mapping"] = "unproven: " + str(error)
        result.append(item)
    return result


def trial_evidence(folder, focus, hashes, observations):
    out = {}
    for filename in ("control.json", "new_family.json", "target_0.json"):
        path = folder / "trial" / filename
        if not path.exists():
            continue
        document = read_bound(path, hashes=hashes)
        fits = {}
        for arm, value in document.get("arms", {}).items():
            last = value.get("history", [{}])[-1]
            last = last.get("fit", last)
            fits[arm] = dict(final_phase_change_s=value.get("final_phase_change_s"),
                optimizer_success=last.get("success"), optimizer_message=last.get("message"),
                stopped=last.get("stopped"), target_gates=target_gate_details(value.get("family"), focus),
                shared_target_diagnostics=shared_target_diagnostics(document, value, focus, observations))
        out[filename] = dict(paired_valid=document.get("paired_valid"), arms=fits)
    path = folder / "trial/exact_owner_replay.json"
    if path.exists():
        document = read_bound(path, hashes=hashes)
        replay_rows = []
        for row in document.get("rows", []):
            negatives = {}
            for family in row.get("exact_family_replays", row.get("exact_incumbent_family_replays", [])):
                for key, slack in family.get("all_gate_slacks", {}).items():
                    if slack < 0:
                        negatives.setdefault(key, []).append(dict(norad=family["norad"], slack=slack))
            replay_rows.append(dict(role=row.get("role"), arm=row["arm"], verified=row.get("verified"),
                target=target_gate_details(row.get("target"), focus),
                continuous_target=target_gate_details(row.get("continuous_target"), focus),
                negative_gate_slacks={key: dict(minimum=min(z["slack"] for z in values),
                    maximum=max(z["slack"] for z in values), replayed_family_norads=[z["norad"] for z in values])
                    for key, values in negatives.items()},
                incumbent_ownership_changes=row.get("incumbent_ownership_changes"),
                control_ownership_changes=row.get("control_ownership_changes"),
                phase_reference_check={k: row.get("phase_reference_check", {}).get(k) for k in
                    ("phase_change_s", "phase_outside_reference_window", "maximum_phase_overflow_s")}))
        out["exact_owner_replay"] = dict(all_verified=document.get("all_verified"), rows=replay_rows)
    return out


def related_stages(decision, tid):
    selected = decision.get("selected_track_ids", [])
    ordinal = selected.index(tid) if tid in selected else None
    result = []
    for stage in decision.get("stages", []):
        name = stage.get("name", "")
        command_match = any(tid in str(token) for token in stage.get("command", []))
        if command_match or ordinal is not None and name.startswith(f"target-{ordinal}-"):
            result.append({k: v for k, v in stage.items() if k in
                           ("name", "status", "seconds", "budget_seconds", "returncode", "error")})
    return result


def omission_status(decision, tids):
    attempts = [a for a in decision.get("attempts", []) if a.get("track_id") in tids]
    stages = [s for tid in tids for s in related_stages(decision, tid)]
    if any("budget" in str(a.get("status", "")) for a in attempts) or any(s.get("status") == "budget_exhausted" for s in stages):
        return "explicit_budget_omission"
    if attempts or stages:
        return "attempted_or_selected_but_no_retained_annotation"
    if decision:
        return "not_selected_by_frozen_target_schedule"
    return "no_retained_recovery_decision"


def recovery_evidence(root, row, tracks, observations, hashes, published_by_arm):
    parent, focus = set(row["all_track_observation_ids"]), set(row["observation_ids"])
    decision_path = root / "decision.json"
    decision = read_bound(decision_path, hashes=hashes) if decision_path.exists() else {}
    inventories = []
    policy_comparisons, shadow_focus = [], set()
    inventory_tids = set()
    for path in sorted(root.rglob("inventory.json")) if root.exists() else []:
        if {"cache", "snapshot", "source-export"} & set(path.relative_to(root).parts):
            continue
        document = read_bound(path, hashes=hashes)
        support_path = path.with_name("publication_support.json")
        support = read_bound(support_path, hashes=hashes) if support_path.exists() else {}
        comparisons = {}
        for arm in ("c0", "fitted_c"):
            saved_policy = document.get("policy", {}).get(arm, {})
            policy = set(saved_policy.get("proposed_associated_ids", []))
            published = published_by_arm[arm]
            shadow = policy - set(published)
            unreported = set(support.get("arms", {}).get(arm, {}).get("unreported_postfit_ids", []))
            saved_owner_map = saved_policy.get("proposed_owners", saved_policy.get("owners", {}))
            saved_shadow_owners = {oid: saved_owner_map[oid] for oid in sorted(shadow & focus & set(saved_owner_map))}
            comparisons[arm] = dict(inventory_proposed_associated_points=len(policy),
                published_associated_points=len(published), shadow_only_points=len(shadow),
                shadow_only_parent_ids=sorted(shadow & parent),
                shadow_only_fragment_ids=sorted(shadow & focus),
                publication_support_unreported_points=len(unreported),
                publication_support_unreported_fragment_ids=sorted(unreported & focus),
                shadow_ids_equal_recorded_unreported_ids=shadow == unreported,
                published_parent_owners={oid: published[oid] for oid in sorted(parent & set(published))},
                saved_shadow_owner_hypotheses=saved_shadow_owners,
                shadow_owner_map_present=bool(saved_shadow_owners))
            if arm == "fitted_c":
                shadow_focus.update(shadow & focus)
        policy_comparisons.append(dict(inventory_path=str(path),
            publication_support_path=str(support_path) if support else None, arms=comparisons))
        for target in document.get("tracks", []):
            match = source_match(parent, focus, target.get("all_track_observation_ids", target.get("observation_ids", [])))
            if match is None:
                continue
            inventory_tids.add(target["track_id"])
            inventories.append(dict(path=str(path), track_id=target["track_id"],
                track_index=target.get("track_index"), component=target.get("component"),
                current_large=target.get("current_large"), source_match=match,
                target_fragment_overlap_points=len(focus & set(target.get("observation_ids", [])))))
    annotations = []
    for path in sorted(root.rglob("annotation/protocol.json")) if root.exists() else []:
        if {"cache", "snapshot", "source-export"} & set(path.relative_to(root).parts):
            continue
        protocol = read_bound(path, hashes=hashes)
        target = protocol.get("target", {})
        match = source_match(parent, focus, target.get("observation_ids", []))
        if match is None:
            continue
        tid = target.get("track_id", path.parent.parent.name)
        inventory_tids.add(tid)
        result_path = path.with_name("result.json")
        item = dict(track_id=tid, protocol_path=str(path), source_match=match,
            target_observation_ids=target.get("observation_ids", []),
            graph_bundle=target.get("graph_bundle", False), bundle_members=target.get("members"),
            attempts=[{k: v for k, v in a.items() if k in ("track_id", "points", "status", "shared_family")}
                      for a in decision.get("attempts", []) if a.get("track_id") == tid],
            stages=related_stages(decision, tid), annotation=None)
        if result_path.exists():
            document = read_bound(result_path, hashes=hashes)
            item["annotation"] = annotation_evidence(document, protocol, tracks, observations, focus)
            item["trial"] = trial_evidence(path.parent.parent, focus, hashes, observations)
        annotations.append(item)
    tested = [a for a in annotations if a["annotation"] and not a["source_match"]["disjoint_from_ranked_fragment"]]
    status = omission_status(decision, inventory_tids)
    if tested:
        statuses = [a.get("status", "") for item in tested for a in item["attempts"]]
        if any("reject" in value.lower() for value in statuses):
            status = "tested_inclusion_rejection"
        elif any(item["annotation"]["status"] != "conditionally_supported_identity" for item in tested):
            status = "tested_annotation_not_supported"
        else:
            status = "tested_supported_hypothesis_without_published_fragment"
    tested_ids = {oid for item in tested for oid in item["target_observation_ids"]}
    shadow_omitted = shadow_focus - tested_ids
    if shadow_omitted:
        status = "unpublished_postfit_ids_suppress_recovery_inventory"
    return dict(recovery_root=str(root), decision_present=bool(decision),
        decision=decision.get("decision"), inventory_matches=inventories, annotations=annotations,
        inventory_publication_comparisons=policy_comparisons,
        unpublished_shadow_ids_without_retained_annotation=sorted(shadow_omitted),
        shadow_owner_inference="Unknown unless an explicit saved observation-owner map proves it; published neighbors do not establish shadow owners",
        status=status,
        matched_attempts=[{k: v for k, v in a.items() if k in ("track_id", "points", "status", "shared_family")}
                          for a in decision.get("attempts", []) if a.get("track_id") in inventory_tids],
        top_hypotheses_are_not_confirmed_identities=True)


def plot_residuals(output, row, versions):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for version, evidence in versions.items():
        shared = [(annotation["track_id"], arm, diagnostic) for annotation in evidence["annotations"]
                  for file in annotation.get("trial", {}).values() if isinstance(file, dict)
                  for arm, value in file.get("arms", {}).items()
                  for diagnostic in value.get("shared_target_diagnostics", [])
                  if diagnostic["mapping"] == "exact_native_ids_times_and_alias"]
        if shared:
            fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, layout="constrained")
            for tid, arm, diagnostic in shared:
                mask = diagnostic["ranked_fragment_mask"]
                times = [t for t, use in zip(diagnostic["times_s"], mask, strict=True) if use]
                for ax, key, label in ((axes[0], "raw_residual_hz", "Raw CFO minus prediction"),
                                       (axes[1], "bias_removed_residual_hz", "Bias-removed residual")):
                    values = [v for v, use in zip(diagnostic[key], mask, strict=True) if use]
                    ax.plot(times, values, ".-", label=f"{arm} NORAD {diagnostic['norad_hypothesis']} hypothesis; profile bias {diagnostic['profile_bias_hz']:.1f}Hz, profiled RMS {diagnostic['profiled_RMS_hz']:.1f}Hz")
                    ax.set(ylabel=label + " (Hz)")
            for ax in axes:
                ax.axhline(0, c=".5", lw=.7)
                ax.grid(alpha=.2)
                ax.legend(fontsize=8)
            axes[1].set(xlabel="Native scan time (s)")
            fig.suptitle(f"#{row['rank']} {row['case']} {version}: saved shared-family target diagnostics\nRaw and profiled residuals are distinct; no new fit or identity confirmation")
            fig.savefig(output / f"{row['rank']:02}-{row['case']}-{version}-shared-target-residuals.png", dpi=145)
            plt.close(fig)
        series = [(annotation["track_id"], fold) for annotation in evidence["annotations"]
                  if annotation["annotation"] and not annotation["source_match"]["disjoint_from_ranked_fragment"]
                  for fold in annotation["annotation"]["folds"]
                  if fold.get("retained_held_residual_mapping") == "exact_native_order_and_recorded_groups"
                  and any(fold["held_ranked_fragment_mask"])]
        if not series:
            continue
        keys = sorted({(tid, fold["seed"]) for tid, fold in series})
        fig, axes = plt.subplots(len(keys), 1, figsize=(12, 2.7 * len(keys)), squeeze=False, layout="constrained")
        for ax, key in zip(axes.flat, keys, strict=True):
            for tid, fold in series:
                if (tid, fold["seed"]) != key:
                    continue
                selected = [(t, r) for t, r, use in zip(fold["held_times_s"], fold["held_residual_hz"], fold["held_ranked_fragment_mask"], strict=True) if use]
                ax.plot([p[0] for p in selected], [p[1] for p in selected], ".", label=f"{fold['arm']}: NORAD {fold['norad_hypothesis']} hypothesis, alias {fold['alias']}")
            ax.axhline(0, c=".5", lw=.7)
            ax.set(title=f"Target {key[0]} · saved random-group seed {key[1]}", xlabel="Native scan time (s)", ylabel="Held residual (Hz)")
            ax.grid(alpha=.2)
            ax.legend(fontsize=8)
        fig.suptitle(f"#{row['rank']} {row['case']} {version}: stored held residuals on exact ranked-fragment IDs\nConditional hypotheses only; no new fit or identity assignment")
        name = f"{row['rank']:02}-{row['case']}-{version}-held-residuals"
        fig.savefig(output / (name + ".png"), dpi=145)
        plt.close(fig)


def run(index_path, ranking_path, output, *, plots=False):
    output.mkdir(parents=True, exist_ok=False)
    hashes = {str(Path(__file__).resolve()): digest(__file__),
              str(Path(__file__).with_name("rank_native_residuals.py").resolve()): digest(Path(__file__).with_name("rank_native_residuals.py"))}
    index = read_bound(index_path, hashes=hashes)
    ranked = read_bound(ranking_path, hashes=hashes)
    rows = ranked if isinstance(ranked, list) else ranked["tracks"][:10]
    entries = {e["case"]: e for e in index["cases"]}
    records = []
    for row in rows:
        entry = entries[row["case"]]
        terminal = read_bound(entry["terminal_path"], entry["terminal_sha256"], hashes)
        incumbent = terminal["incumbent"] if terminal["model_version"] == "algo04-causal-numerical-v1" else terminal
        tracks = read_bound(entry["tracks_path"], entry["tracks_sha256"], hashes)
        observations = read_bound(entry["observations_path"], entry["observations_sha256"], hashes)
        case_root = index_path.parent / "cases" / row["case"]
        versions = {}
        for version, key, default in (("ALGO03", "algo03_recovery_path", case_root / "candidate-v2/recovery"),
                                      ("ALGO04", "algo04_recovery_path", case_root / "candidate-v3/recovery")):
            chosen = incumbent if version == "ALGO03" else terminal
            owners = {arm: published_owners(chosen, arm) for arm in ("c0", "fitted_c")}
            versions[version] = recovery_evidence(Path(entry.get(key) or default), row, tracks, observations, hashes, owners)
        record = dict(rank=row["rank"], case=row["case"], fragment_id=row["fragment_id"],
            track_id=row["track_id"], track_index=row["track_index"], key=row["key"],
            observation_ids=row["observation_ids"], all_track_observation_ids=row["all_track_observation_ids"],
            versions=versions, no_new_fits=True, no_GPS_TLE_IQ=True)
        (output / f"{row['rank']:02}-{row['case']}-{row['fragment_id']}.json").write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
        records.append(record)
        if plots:
            plot_residuals(output, row, versions)
    report = dict(schema="ds27-top-native-fragment-retained-annotation-audit/v1", tracks=records,
        fixture_only=index.get("fixture_only", False),
        rule="Exact native source-ID relationships; bundle and subset matches explicit; missing is not a tested rejection",
        no_new_fits=True, hypotheses_not_confirmed_identities=True, source_sha256=hashes)
    (output / "annotation-audit.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    portable = []
    for record in records:
        versions = {}
        for version, evidence in record["versions"].items():
            annotations = []
            for item in evidence["annotations"]:
                annotations.append(dict(track_id=item["track_id"], source_match=item["source_match"],
                    annotation=dict(folds=item["annotation"]["folds"]) if item["annotation"] else None,
                    trial={name: dict(arms={arm: dict(shared_target_diagnostics=value.get("shared_target_diagnostics", []))
                                          for arm, value in trial.get("arms", {}).items()})
                           for name, trial in item.get("trial", {}).items()}))
            versions[version] = dict(annotations=annotations)
        portable.append(dict(rank=record["rank"], case=record["case"], versions=versions))
    packet = dict(schema="retained-annotation-residual-plot-packet/v1", tracks=portable,
                  hypotheses_not_confirmed_identities=True, no_orbit_or_truth_arrays=True)
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as archive:
        archive.write(json.dumps(packet, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
    (output / "annotation-plot-inputs.json.gz").write_bytes(stream.getvalue())
    return report


def replot(packet_path, output):
    packet = json.loads(gzip.decompress(packet_path.read_bytes()))
    if packet["schema"] != "retained-annotation-residual-plot-packet/v1":
        raise ValueError("Unknown retained-residual plot packet")
    output.mkdir(parents=True, exist_ok=False)
    for record in packet["tracks"]:
        plot_residuals(output, record, record["versions"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--ranking", type=Path)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args()
    if args.packet:
        replot(args.packet, args.output)
    elif args.index and args.ranking:
        run(args.index, args.ranking, args.output, plots=args.plots)
    else:
        parser.error("choose --packet or both --index and --ranking")
