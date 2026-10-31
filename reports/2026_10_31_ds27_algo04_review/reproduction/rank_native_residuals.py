"""Rank contiguous native source fragments after exact published ALGO04 owners.

Read-only analysis of explicitly supplied exports. No inference, GPS, TLE or IQ
read occurs. A graph polynomial is an existing descriptive source fit, never an
emitter identification. The approved primary gap bound is five seconds.
"""

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path

PERIOD_HZ = 1 / 4.4e-6
GAP_S = 5.0


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_bound(path, expected=None, hashes=None):
    actual = digest(path)
    if expected is not None and actual.removeprefix("sha256:") != expected.removeprefix("sha256:"):
        raise ValueError("Changed frozen input: " + str(path))
    if hashes is not None:
        hashes[str(path)] = actual
    return json.loads(Path(path).read_text())


def published_owners(terminal, arm="fitted_c"):
    """Follow the chosen public proof, never an unchosen numerical proposal."""
    if terminal["state"] != "complete":
        raise ValueError("No qualified published support")
    model = terminal["model_version"]
    if model == "algo04-causal-numerical-v1":
        if terminal["decision"] == "ALGO04_additive":
            return published_owners(terminal["candidate"], arm)
        if terminal["decision"] == "ALGO03_fallback":
            return published_owners(terminal["incumbent"], arm)
        raise ValueError("Unknown ALGO04 decision")
    if model == "algo03-causal-predictive-v1":
        if terminal.get("selected"):
            saved = terminal["selected"]["arms"][arm]
            if set(saved["associated_ids"]) != set(saved["owners"]):
                raise ValueError("Published IDs and owners disagree")
            return dict(saved["owners"])
        if terminal["decision"] != "ALGO02_fallback":
            raise ValueError("Missing chosen ALGO03 support")
        baseline = published_owners(terminal["baseline"], arm)
        proof = terminal.get("source_support", {}).get(arm, {}).get("owners")
        if proof is None:
            return baseline
        if set(proof) != set(baseline):
            raise ValueError("Fallback source-support IDs differ from published baseline IDs")
        if any(not isinstance(norad, int) or isinstance(norad, bool) or norad <= 0
               for norad in proof.values()):
            raise ValueError("Fallback source-support owner labels are not known NORADs")
        if any(norad is not None and proof[oid] != norad for oid, norad in baseline.items()):
            raise ValueError("Fallback source-support owners disagree with known baseline labels")
        return dict(proof)
    if model != "algo02-causal-family-v1":
        raise ValueError("Unknown published model")
    saved = terminal["arms"][arm]
    owners = {}
    for row in saved["gates"]["tracks"] + saved.get("linear_gates", []):
        for oid in row["observation_ids"]:
            norad = row.get("norad")
            if oid in owners and owners[oid] != norad:
                raise ValueError("Conflicting published baseline owner")
            owners[oid] = norad
    return owners


def canonical_tracks(tracks):
    """Collapse identical physical-ID aliases; never union partially overlapping curves."""
    groups = {}
    for index, track in enumerate(tracks):
        ids = track["observation_ids"]
        if len(ids) != len(set(ids)) or len(ids) != len(track["times"]) or len(ids) != len(track["values"]):
            raise ValueError("Duplicate IDs or unequal source arrays")
        key = (track["receiver"], track["channel"], track["rf_hz"], frozenset(ids))
        groups.setdefault(key, []).append((index, track))
    result, owner = [], {}
    for variants in sorted(groups.values(), key=lambda group: group[0][0]):
        index, track = variants[0]
        for oid in track["observation_ids"]:
            if oid in owner:
                raise ValueError(f"Partial graph-source overlap: {oid}, tracks {owner[oid]}/{index}")
            owner[oid] = index
        result.append((index, track, [dict(track_index=i, key=t["key"]) for i, t in variants]))
    return result


def piece_membership(track):
    indices = track.get("indices", list(range(len(track["times"]))))
    if len(indices) != len(track["times"]):
        raise ValueError("Native index array differs from observation array")
    memberships = []
    for index, time in zip(indices, track["times"], strict=True):
        matches = [i for i, piece in enumerate(track.get("pieces", []))
                   if index in piece.get("indices", [])]
        if not matches:
            matches = [i for i, piece in enumerate(track.get("pieces", []))
                       if piece["start_s"] <= time <= piece["end_s"]]
        memberships.append(matches)
    return memberships


def runs(track, associated, gap_s=GAP_S):
    """Source adjacency includes claimed points, so subtraction cannot bridge them."""
    membership = piece_membership(track)
    result, current = [], []
    for i in sorted(range(len(track["times"])), key=lambda k: (track["times"][k], k)):
        if track["observation_ids"][i] in associated:
            if current:
                result.append(current)
                current = []
            continue
        piece = membership[i][0] if membership[i] else None
        if current:
            previous = current[-1]
            old_piece = membership[previous][0] if membership[previous] else None
            if track["times"][i] - track["times"][previous] > gap_s or piece != old_piece:
                result.append(current)
                current = []
        current.append(i)
    if current:
        result.append(current)
    return result


def span(track, indices):
    return float(track["times"][indices[-1]] - track["times"][indices[0]])


def polynomial(piece, time):
    x = (time - piece["reference_time_s"]) / piece["time_scale_s"]
    coefficients = piece["coefficients_hz"]
    total, p0, p1 = coefficients[0], 1.0, x
    if len(coefficients) > 1:
        total += coefficients[1] * p1
    for degree in range(2, len(coefficients)):
        p0, p1 = p1, ((2 * degree - 1) * x * p1 - (degree - 1) * p0) / degree
        total += coefficients[degree] * p1
    return total


def fragment_rows(case, tracks, observations, associated, identities=None):
    lookup = {o["observation_id"]: o for o in observations}
    if len(lookup) != len(observations) or not set(associated) <= set(lookup):
        raise ValueError("Duplicate native GLRT IDs or unknown published support")
    canonical = canonical_tracks(tracks)
    graph = {oid for _, t, _ in canonical for oid in t["observation_ids"]}
    if not graph <= set(lookup):
        raise ValueError("Graph contains non-native observation IDs")
    rows = []
    for index, track, variants in canonical:
        for oid, time in zip(track["observation_ids"], track["times"], strict=True):
            obs = lookup[oid]
            if (obs["receiver"], obs["channel"]) != (track["receiver"], track["channel"]) or abs(obs["time_s"] - time) > 1e-6:
                raise ValueError("Graph-to-native lane/time mismatch")
        remaining = [i for i, oid in enumerate(track["observation_ids"]) if oid not in associated]
        if not remaining:
            continue
        remaining.sort(key=lambda i: (track["times"][i], i))
        track_id = hashlib.sha256(("\n".join(sorted(identities or [case])) + "\n" +
                                   "\n".join(sorted(track["observation_ids"]))).encode()).hexdigest()[:20]
        source_membership = piece_membership(track)
        sensitivity = {}
        for bound in (2.0, 5.0, 10.0):
            rr = runs(track, associated, bound)
            longest = max(rr, key=lambda z: (span(track, z), len(z)))
            sensitivity[f"parent_longest_{int(bound)}s_gap_fragment_span_s"] = span(track, longest)
            sensitivity[f"parent_{int(bound)}s_gap_fragments"] = len(rr)
        parent_gaps = [track["times"][b] - track["times"][a] for a, b in zip(remaining, remaining[1:])]
        for number, fragment in enumerate(runs(track, associated), 1):
            times = [track["times"][i] for i in fragment]
            ids = [track["observation_ids"][i] for i in fragment]
            native = [lookup[oid]["measured_cfo_hz"] for oid in ids]
            lifts = [track["values"][i] - y for i, y in zip(fragment, native, strict=True)]
            piece_index = source_membership[fragment[0]][0] if source_membership[fragment[0]] else None
            piece = track.get("pieces", [])[piece_index] if piece_index is not None else None
            errors = [track["values"][i] - polynomial(piece, track["times"][i]) for i in fragment] if piece else []
            rows.append(dict(case=case, track_index=index, key=track["key"], track_id=track_id,
                native_graph_source_id=track.get("source_id"),
                track_id_identity_basis=sorted(identities or [case]),
                fragment_id=hashlib.sha256((track_id + "\n" + "\n".join(ids)).encode()).hexdigest()[:20],
                fragment_number=number, source_variants=variants, source_piece_index=piece_index,
                receiver=track["receiver"], channel=track["channel"], rf_hz=track["rf_hz"],
                points=len(ids), start_s=float(times[0]), end_s=float(times[-1]), duration_s=float(times[-1] - times[0]),
                max_gap_s=float(max((b - a for a, b in zip(times, times[1:])), default=0)),
                parent_points=len(track["observation_ids"]), parent_residual_points=len(remaining),
                parent_associated_points=len(track["observation_ids"]) - len(remaining),
                parent_wholly_unassociated=len(remaining) == len(track["observation_ids"]),
                parent_residual_span_s=span(track, remaining), parent_residual_max_gap_s=float(max(parent_gaps, default=0)),
                parent_graph_pieces=len(track.get("pieces", [])), graph_quality_status=track.get("quality_status"),
                graph_polynomial_rms_hz=track.get("residual_rms_hz"),
                fragment_point_minus_polynomial_rms_hz=math.sqrt(sum(e * e for e in errors) / len(errors)) if errors else None,
                alias_lift_changes=sum(abs(b - a) > 1 for a, b in zip(lifts, lifts[1:])),
                maximum_noninteger_alias_lift_error_hz=max((abs(v - round(v / PERIOD_HZ) * PERIOD_HZ) for v in lifts), default=0),
                ambiguous_piece_memberships=sum(len(source_membership[i]) > 1 for i in fragment),
                observation_ids=ids, source_local_indices=fragment,
                all_track_observation_ids=track["observation_ids"], native_source_indices=[track.get("indices", list(range(len(track["times"]))))[i] for i in fragment],
                **sensitivity))
    summary = dict(case=case, total_GLRT=len(lookup), associated=len(associated),
        residual_GLRT=len(set(lookup) - set(associated)), graph_source_tracks=len(tracks),
        canonical_graph_tracks=len(canonical), duplicate_alias_tracks_collapsed=len(tracks) - len(canonical),
        residual_graph_unique_points=len(graph - set(associated)),
        unassociated_untracked_points=len(set(lookup) - graph - set(associated)),
        residual_fragments=len(rows), singleton_fragments=sum(r["points"] == 1 for r in rows))
    assert sum(r["points"] for r in rows) == summary["residual_graph_unique_points"]
    return rows, summary


def write_csv(path, rows):
    if not rows:
        return
    fields = [k for k, v in rows[0].items() if not isinstance(v, (list, dict))]
    with Path(path).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parent_ranking(rows):
    grouped = {}
    for row in rows:
        key = (row["case"], row["track_index"])
        grouped.setdefault(key, []).append(row)
    parents = []
    for fragments in grouped.values():
        first = fragments[0]
        remaining = {oid for row in fragments for oid in row["observation_ids"]}
        keep = ("case", "track_index", "key", "track_id", "receiver", "channel", "rf_hz",
                "source_variants", "parent_points", "parent_associated_points", "parent_wholly_unassociated",
                "parent_graph_pieces", "graph_quality_status", "recording_id", "run_id")
        parent = {key: first[key] for key in keep if key in first}
        parent.update(points=first["parent_residual_points"], duration_s=first["parent_residual_span_s"],
            max_gap_s=first["parent_residual_max_gap_s"], contiguous_fragments=len(fragments),
            longest_native_fragment_duration_s=max(row["duration_s"] for row in fragments),
            primary_fragment_ranks=[row.get("rank") for row in fragments],
            remaining_observation_ids=[oid for oid in first["all_track_observation_ids"] if oid in remaining],
            all_track_observation_ids=first["all_track_observation_ids"])
        parent.update({key: value for key, value in first.items() if key.startswith("parent_longest_")})
        parents.append(parent)
    parents.sort(key=lambda row: (-row["duration_s"], -row["points"], row["case"], row["track_index"]))
    for number, row in enumerate(parents, 1):
        row["parent_rank"] = number
    return parents


def export_plot_packet(path, top, contexts, failed=None):
    """Standalone, deterministic and path-free native plot inputs; no orbit arrays."""
    needed = sorted({row["case"] for row in top})
    observation_keys = ("observation_id", "time_s", "measured_cfo_hz", "receiver", "channel")
    track_keys = ("key", "receiver", "channel", "rf_hz", "observation_ids", "times", "values",
                  "indices", "pieces", "quality_status", "residual_rms_hz")
    packet = dict(schema="native-residual-plot-packet/v1", no_orbit_or_truth_arrays=True,
        top10=[{key: value for key, value in row.items() if not key.endswith("_path")} for row in top],
        cases={case: dict(
            observations=[{k: o[k] for k in observation_keys} for o in contexts[case]["observations"]],
            tracks=[{k: t[k] for k in track_keys if k in t} for t in contexts[case]["tracks"]],
            associated_ids=sorted(contexts[case]["associated"])) for case in needed},
        failed_cases={case: dict(ownership_status="unknown_no_qualified_association_result",
            observations=[{k: o[k] for k in observation_keys} for o in value["observations"]],
            tracks=[{k: t[k] for k in track_keys if k in t} for t in value["tracks"]],
            top3=value["top3"]) for case, value in (failed or {}).items()})
    payload = json.dumps(packet, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as archive:
        archive.write(payload)
    Path(path).write_bytes(stream.getvalue())
    return dict(path=Path(path).name, sha256=digest(path), compressed_bytes=Path(path).stat().st_size,
                case_labels=needed, original_GLRT_points=sum(len(packet["cases"][c]["observations"]) for c in needed))


def render_packet(packet_path, output):
    packet = json.loads(gzip.decompress(Path(packet_path).read_bytes()))
    if packet["schema"] != "native-residual-plot-packet/v1":
        raise ValueError("Unknown plot packet")
    output.mkdir(parents=True, exist_ok=False)
    contexts = {case: dict(tracks=value["tracks"], observations=value["observations"],
                           associated=set(value["associated_ids"])) for case, value in packet["cases"].items()}
    render(output, packet["top10"], contexts)
    render_failed(output, packet.get("failed_cases", {}))


def rank(index_path, output, *, allow_prior_fixture=False, plots=False):
    hashes = {str(Path(__file__).resolve()): digest(__file__)}
    index = read_bound(index_path, hashes=hashes)
    output.mkdir(parents=True, exist_ok=False)
    rows, summaries, unavailable, contexts, failed_contexts = [], [], [], {}, {}
    physical_sources, physical_observations = {}, {}
    for entry in index["cases"]:
        case = entry["case"]
        if entry["state"] != "complete":
            item = dict(entry, excluded_from_post_ALGO04_ranking=True, association_ownership="unknown")
            if entry.get("tracks_path") and entry.get("observations_path"):
                tracks = read_bound(entry["tracks_path"], entry.get("tracks_sha256"), hashes)
                observations = read_bound(entry["observations_path"], entry.get("observations_sha256"), hashes)
                native, _ = fragment_rows(case, tracks, observations, {}, entry.get("identities", [case]))
                keep = ("case", "track_index", "key", "track_id", "fragment_id", "fragment_number",
                        "source_variants", "source_piece_index", "receiver", "channel", "rf_hz",
                        "points", "start_s", "end_s", "duration_s", "max_gap_s", "parent_points",
                        "parent_graph_pieces", "graph_quality_status", "graph_polynomial_rms_hz",
                        "observation_ids", "source_local_indices", "all_track_observation_ids", "native_source_indices")
                unknown = [dict({k: r[k] for k in keep}, parent_native_span_s=r["parent_residual_span_s"],
                                ownership_status="unknown_no_qualified_association_result") for r in native]
                unknown.sort(key=lambda r: (-r["duration_s"], -r["points"], r["track_index"], r["fragment_number"]))
                item.update(native_GLRT_points=len(observations), native_graph_fragments=unknown,
                            note="Native geometry only; these are not post-ALGO04 unassociated tracks")
                failed_contexts[case] = dict(tracks=tracks, observations=observations, top3=unknown[:3])
            unavailable.append(item)
            continue
        terminal = read_bound(entry["terminal_path"], entry["terminal_sha256"], hashes)
        if not allow_prior_fixture and terminal["model_version"] != "algo04-causal-numerical-v1":
            raise ValueError("Post-ALGO04 ranking requires an ALGO04 terminal")
        owners = published_owners(terminal)
        tracks = read_bound(entry["tracks_path"], entry["tracks_sha256"], hashes)
        observations = read_bound(entry["observations_path"], entry["observations_sha256"], hashes)
        source_identity = entry.get("recording_id") or terminal.get("session_id") or case
        if source_identity in physical_sources:
            raise ValueError("Repeated physical recording under cohort aliases: " + source_identity)
        physical_sources[source_identity] = case
        for observation in observations:
            oid = observation["observation_id"]
            if oid in physical_observations:
                raise ValueError(f"Physical GLRT ID repeats across cohort scans {physical_observations[oid]}/{case}: {oid}")
            physical_observations[oid] = case
        local, summary = fragment_rows(case, tracks, observations, owners,
                                      entry.get("identities", [terminal.get("session_id", case)]))
        for row in local:
            row.update(recording_id=entry.get("recording_id"), run_id=entry.get("run_id"),
                       terminal_path=entry["terminal_path"], tracks_path=entry["tracks_path"],
                       observations_path=entry["observations_path"], decision=terminal["decision"],
                       chosen_model=terminal["model_version"])
        rows += local
        summary["c_arm_published_owners_identical"] = published_owners(terminal, "c0") == owners
        summaries.append(summary)
        contexts[case] = dict(tracks=tracks, observations=observations, associated=set(owners))
    rows.sort(key=lambda r: (-r["duration_s"], -r["points"], r["case"], r["track_index"], r["fragment_number"]))
    for number, row in enumerate(rows, 1):
        row["rank"] = number
    parents = parent_ranking(rows)
    plot_packet = export_plot_packet(output / "plot-inputs.json.gz", rows[:10], contexts, failed_contexts)
    report = dict(schema="ds27-contiguous-native-residual-fragments/v1", cases=len(index["cases"]),
        complete_cases=len(summaries), unavailable=unavailable, selected_arm="fitted_c",
        fixture_only=allow_prior_fixture, no_GPS_TLE_IQ_or_fit=True,
        ranking="Observed fragment duration descending, unique point count descending, stable source order",
        continuity="Split at claimed source points, existing native polynomial-piece boundaries and adjacent gaps >5s; no interpolated coverage",
        alias_policy="Collapse identical lane/RF/physical-ID source aliases; reject partial graph overlaps; native alias wraps are rendered as gaps, not new points",
        untracked_policy="Count native unassociated IDs outside existing graph separately; no claim of finding every possible curve",
        unique_physical_recordings=len(physical_sources), unique_original_GLRT=len(physical_observations),
        tracks=rows, parent_tracks=parents, per_scan=summaries, source_sha256=hashes, reproducible_plot_inputs=plot_packet)
    for name, value in (("inventory.json", report), ("top10.json", rows[:10])):
        (output / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    write_csv(output / "residual_fragments.csv", rows)
    write_csv(output / "top10.csv", rows[:10])
    write_csv(output / "parent-top10.csv", parents[:10])
    write_csv(output / "parent_tracks.csv", parents)
    write_csv(output / "per_scan.csv", summaries)
    (output / "failed-scan-native-inventory.json").write_text(json.dumps(dict(
        association_ownership="unknown; never assumed zero", excluded_from_main_top10=True,
        cases=unavailable), indent=2, allow_nan=False) + "\n")
    if plots:
        render(output, rows[:10], contexts)
        render_failed(output, failed_contexts)
    print(json.dumps(dict(cases=len(index["cases"]), complete=len(summaries), fragments=len(rows),
                          untracked=sum(s["unassociated_untracked_points"] for s in summaries))))
    return report


def render(output, top, contexts):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    figures = output / "figures"
    figures.mkdir()
    fig, axes = plt.subplots(5, 2, figsize=(17, 19), layout="constrained")
    for ax, row in zip(axes.flat, top):
        context = contexts[row["case"]]
        track = context["tracks"][row["track_index"]]
        lookup = {o["observation_id"]: o for o in context["observations"]}
        focus = set(row["observation_ids"])
        lane = [o for o in context["observations"] if (o["receiver"], o["channel"]) == (row["receiver"], row["channel"]) and row["start_s"] - 5 <= o["time_s"] <= row["end_s"] + 5]
        for label, color, marker, chosen in (
            ("Associated GLRT", ".72", ".", [o for o in lane if o["observation_id"] in context["associated"]]),
            ("Other unassociated GLRT", "darkorange", "x", [o for o in lane if o["observation_id"] not in context["associated"] | focus]),
            ("Ranked native fragment", "crimson", ".", [lookup[oid] for oid in row["observation_ids"]])):
            ax.scatter([o["time_s"] for o in chosen], [o["measured_cfo_hz"] / 1000 for o in chosen], c=color, marker=marker, s=12, label=label)
        ix = row["source_local_indices"]
        times = np.array([track["times"][i] for i in ix])
        native = np.array([lookup[track["observation_ids"][i]]["measured_cfo_hz"] for i in ix])
        if row["source_piece_index"] is not None:
            piece = track["pieces"][row["source_piece_index"]]
            y = np.array([polynomial(piece, t) for t in times]) - (np.array([track["values"][i] for i in ix]) - native)
            y[np.r_[False, abs(np.diff(y)) > PERIOD_HZ / 2]] = np.nan
            ax.plot(times, y / 1000, c="tab:blue", lw=1, label="Existing native graph polynomial")
        pad = max(3000, float(np.ptp(native)) * .08)
        ax.set_ylim((float(native.min()) - pad) / 1000, (float(native.max()) + pad) / 1000)
        ax.set(title=f"#{row['rank']} {row['case']} RX{row['receiver']} CH{row['channel']} · {row['duration_s']:.3f}s · {row['points']} points",
               xlabel="Native scan time (s)", ylabel="Native CFO (kHz)")
        ax.grid(alpha=.2)
    for ax in list(axes.flat)[len(top):]:
        ax.set_visible(False)
    if top:
        fig.legend(*axes.flat[0].get_legend_handles_labels(), loc="outside lower center", ncol=4)
    models = {row.get("chosen_model") for row in top}
    owner_label = ("published ALGO03 fitted-c owners (prior-data tooling fixture)"
                   if models == {"algo03-causal-predictive-v1"} else "chosen ALGO04 fitted-c owners")
    fig.suptitle(f"Ten longest contiguous native fragments after {owner_label}\nGray = associated; orange/red = unassociated; blue = existing source polynomial")
    fig.savefig(output / "top10-overview.png", dpi=140)
    plt.close(fig)
    for case in sorted({r["case"] for r in top}):
        context = contexts[case]
        graph = {oid for t in context["tracks"] for oid in t["observation_ids"]}
        for rx in (1, 2):
            fig, axes = plt.subplots(4, 2, figsize=(15, 12), layout="constrained")
            for ch, ax in enumerate(axes.flat, 1):
                lane = [o for o in context["observations"] if (o["receiver"], o["channel"]) == (rx, ch)]
                for label, color, marker, chosen in (
                    ("Associated GLRT", ".72", ".", [o for o in lane if o["observation_id"] in context["associated"]]),
                    ("Unassociated in graph", "crimson", ".", [o for o in lane if o["observation_id"] in graph - context["associated"]]),
                    ("Unassociated untracked", "darkorange", "x", [o for o in lane if o["observation_id"] not in graph | context["associated"]])):
                    ax.scatter([o["time_s"] for o in chosen], [o["measured_cfo_hz"] / 1000 for o in chosen], s=9, c=color, marker=marker, label=label, alpha=.8)
                untracked = sum(o["observation_id"] not in graph | context["associated"] for o in lane)
                ax.set(title=f"{case} RX{rx} CH{ch} · {untracked} untracked winners", xlabel="Native scan time (s)", ylabel="Native CFO (kHz)")
                ax.grid(alpha=.2)
            fig.legend(*axes.flat[0].get_legend_handles_labels(), loc="outside lower center", ncol=3)
            fig.suptitle("All original GLRT context; gray = associated; colors = unassociated")
            fig.savefig(figures / f"{case}-RX{rx}-context.png", dpi=140)
            plt.close(fig)
    for row in top:
        context = contexts[row["case"]]
        track = context["tracks"][row["track_index"]]
        lookup = {o["observation_id"]: o for o in context["observations"]}
        focus = set(row["observation_ids"])
        lane = [o for o in context["observations"] if (o["receiver"], o["channel"]) == (row["receiver"], row["channel"]) and row["start_s"] - 5 <= o["time_s"] <= row["end_s"] + 5]
        fig, (ax, residual) = plt.subplots(2, 1, figsize=(12, 7), sharex=True, layout="constrained")
        for label, color, marker, chosen in (
            ("Associated GLRT", ".72", ".", [o for o in lane if o["observation_id"] in context["associated"]]),
            ("Other unassociated graph GLRT", "tab:purple", ".", [o for o in lane if o["observation_id"] not in context["associated"] | focus and any(o["observation_id"] in t["observation_ids"] for t in context["tracks"])]),
            ("Unassociated untracked GLRT", "darkorange", "x", [o for o in lane if o["observation_id"] not in context["associated"] | focus and not any(o["observation_id"] in t["observation_ids"] for t in context["tracks"])]),
            ("Ranked residual fragment", "crimson", "o", [lookup[oid] for oid in row["observation_ids"]])):
            ax.scatter([o["time_s"] for o in chosen], [o["measured_cfo_hz"] / 1000 for o in chosen], c=color, marker=marker, s=18, label=label)
        ix = row["source_local_indices"]
        times = np.array([track["times"][i] for i in ix])
        native = np.array([lookup[track["observation_ids"][i]]["measured_cfo_hz"] for i in ix])
        if row["source_piece_index"] is not None:
            piece = track["pieces"][row["source_piece_index"]]
            unwrapped = np.array([polynomial(piece, t) for t in times])
            prediction = unwrapped - (np.array([track["values"][i] for i in ix]) - native)
            prediction[np.r_[False, abs(np.diff(prediction)) > PERIOD_HZ / 2]] = np.nan
            ax.plot(times, prediction / 1000, c="tab:blue", lw=1, label="Existing native graph polynomial")
            residual.plot(times, np.array([track["values"][i] for i in ix]) - unwrapped, ".-", c="crimson", label="Source points minus existing graph polynomial")
        else:
            residual.text(.02, .7, "No existing polynomial for this fragment", transform=residual.transAxes)
        residual.axhline(0, c=".5", lw=.7)
        for a in (ax, residual):
            a.grid(alpha=.2)
            a.legend(fontsize=8)
        ax.set(ylabel="Native CFO (kHz)", title=f"#{row['rank']} {row['case']} RX{row['receiver']} CH{row['channel']} {row['key']}\n{row['points']} points · {row['duration_s']:.3f}s · max gap {row['max_gap_s']:.3f}s · parent {row['parent_associated_points']}/{row['parent_points']} associated")
        residual.set(xlabel="Native scan time (s)", ylabel="Polynomial residual (Hz)")
        for suffix in ("png", "pdf"):
            fig.savefig(figures / f"{row['rank']:02}-{row['case']}-{row['fragment_id']}.{suffix}", dpi=150)
        plt.close(fig)


def render_failed(output, cases):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for case, context in cases.items():
        rows = context["top3"]
        if not rows:
            continue
        fig, axes = plt.subplots(len(rows), 1, figsize=(13, 3.6 * len(rows)), squeeze=False, layout="constrained")
        lookup = {o["observation_id"]: o for o in context["observations"]}
        for ax, row in zip(axes.flat, rows, strict=True):
            lane = [o for o in context["observations"] if (o["receiver"], o["channel"]) == (row["receiver"], row["channel"]) and row["start_s"] - 5 <= o["time_s"] <= row["end_s"] + 5]
            ax.scatter([o["time_s"] for o in lane], [o["measured_cfo_hz"] / 1000 for o in lane], c=".7", s=14, label="Native GLRT · ownership unknown")
            points = [lookup[oid] for oid in row["observation_ids"]]
            ax.scatter([o["time_s"] for o in points], [o["measured_cfo_hz"] / 1000 for o in points], c="tab:blue", s=20, label="Highlighted native fragment · ownership unknown")
            ax.set(title=f"{case} RX{row['receiver']} CH{row['channel']} {row['key']}\n{row['duration_s']:.3f}s · {row['points']} points · max gap {row['max_gap_s']:.3f}s · native parent span {row['parent_native_span_s']:.3f}s",
                   xlabel="Native scan time (s)", ylabel="Native CFO (kHz)")
            ax.grid(alpha=.2)
            ax.legend(fontsize=8)
        fig.suptitle("NO qualified position / association result: ownership is UNKNOWN\nSeparate failed-scan native geometry; excluded from the post-ALGO04 top ten")
        fig.savefig(output / f"failed-scan-{case}-longest3.png", dpi=145)
        plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--packet", type=Path, help="Render a standalone published plot packet")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-prior-fixture", action="store_true")
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args()
    if args.packet:
        render_packet(args.packet, args.output)
    elif args.index:
        rank(args.index, args.output, allow_prior_fixture=args.allow_prior_fixture, plots=args.plots)
    else:
        parser.error("choose --index or --packet")
