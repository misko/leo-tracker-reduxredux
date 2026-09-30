"""Frame-disjoint identity transfer with matched contrasts and label permutations."""

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parent / "2026_09_29_ds10_signal_extension/local"
OUT = BASE / "local"
FEATURES = ["absolute_phase", "within_symbol_difference", "between_symbol_difference", "real_sign"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unit(x):
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-10)


def features(z):
    u = z / np.maximum(abs(z), 1e-10)
    complex_features = [u, u[:, :, [0, 2]] * u[:, :, [1, 3]].conj(),
                        u[:, [1, 3], :] * u[:, [2, 4], :].conj()]
    result = [np.concatenate([v.real.reshape(2, -1), v.imag.reshape(2, -1)], axis=1)
              for v in complex_features]
    return result + [(z.real >= 0).reshape(2, -1).astype(float) * 2 - 1]


def load_features():
    rows = json.loads((SOURCE / "qualified-tracks.json").read_text())
    best = {}
    for r in rows:
        key = (r["session"], r["visit"], r["receiver"], r["edge"], r["channel"])
        if key not in best or r["pilot"] > best[key]["pilot"]:
            best[key] = r
    rows = sorted(best.values(), key=lambda r: r["id"])
    arrays = [[] for _ in FEATURES]
    for r in rows:
        path = Path(r["source_artifact"])
        assert sha(path) == r["source_artifact_sha256"]
        with np.load(path) as d:
            meta = json.loads(str(d["metadata"]))
            core = [486, 487, 496, 497] if r["edge"] == "upper" else [526, 527, 536, 537]
            assert not set(core) & set(meta["pilot_bins"])
            assert np.isin(core, d["bins"]).all()
            z = d["z"][meta["evaluation_frames"], :6][:, :, np.searchsorted(d["bins"], core)]
            assert z.shape == (2, 6, 4)
            for output, value in zip(arrays, features(z), strict=True):
                output.append(value)
    arrays = [np.array(a, dtype=float) for a in arrays]
    # Instrument-stratum center/scale uses observation half 0 only, no labels.
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        groups[r["edge"], r["channel"], r["rate"], r["receiver"]].append(i)
    for group in groups.values():
        for a in arrays:
            discovery = a[group, 0]
            center = discovery.mean(axis=0)
            scale = np.maximum(discovery.std(axis=0), .25)
            a[group] = (a[group] - center) / scale
    return rows, [unit(a) for a in arrays]


def separation_bin(t):
    return int(np.searchsorted([10, 120, 600, 7200], t, side="right"))


def contrast(labels, i, j, strata, scores):
    same = labels[i] == labels[j]
    differences, used = [], []
    for group in strata:
        positive, negative = group[same[group]], group[~same[group]]
        if len(positive) and len(negative):
            differences.extend(scores[positive] - scores[negative].mean(axis=0))
            used.extend(positive.tolist())
    if not used:
        return None, []
    return np.mean(differences, axis=0), used


def experiment(rows, arrays, scope, tier, permutations=499):
    relaxed = scope.endswith("_pairs")
    base_scope = scope.removesuffix("_pairs")
    chosen = [k for k, r in enumerate(rows) if r["norad_id"] is not None
              and (tier == "all" or r["tier"] == "control_supported_candidate")]
    rr = [rows[k] for k in chosen]
    labels = np.array([r["norad_id"] for r in rr])
    pairs, strata = [], defaultdict(list)
    for i, a in enumerate(rr):
        for j, b in enumerate(rr[:i]):
            if a["session"] == b["session"] and a["visit"] == b["visit"]:
                continue
            if a["edge"] != b["edge"]:
                continue
            if not relaxed and any(a[k] != b[k] for k in ("rate", "receiver")):
                continue
            if base_scope == "same_channel" and a["channel"] != b["channel"]:
                continue
            if base_scope == "cross_channel_session" and (
                    a["session"] == b["session"] or a["channel"] == b["channel"]):
                continue
            if abs(a["pilot"] - b["pilot"]) > (.1 if relaxed else .05):
                continue
            dt = abs(a["selected_utc_ns"] - b["selected_utc_ns"]) / 1e9
            states0, states1 = set(a["known_tail_states"]), set(b["known_tail_states"])
            state = int(bool(states0 & states1)) if states0 and states1 else -1
            key = (a["edge"], tuple(sorted([a["rate"], b["rate"]])),
                   tuple(sorted([a["receiver"], b["receiver"]])),
                   tuple(sorted([a["channel"], b["channel"]])),
                   a["session"] == b["session"], separation_bin(dt), state)
            strata[key].append(len(pairs))
            pairs.append((i, j, dt, state))
    result = dict(scope=scope, tier=tier, observations=len(rr), pairs=len(pairs))
    if not pairs:
        return dict(**result, abstention="No matched pairs")
    i, j = np.array([(p[0], p[1]) for p in pairs]).T
    groups = [np.array(g) for g in strata.values()]
    scores = np.column_stack([
        .5 * ((a[np.array(chosen)[i], 0] * a[np.array(chosen)[j], 1]).sum(axis=1)
              + (a[np.array(chosen)[j], 0] * a[np.array(chosen)[i], 1]).sum(axis=1))
        for a in arrays])
    observed, used = contrast(labels, i, j, groups, scores)
    result.update(same_candidate_pairs=int((labels[i] == labels[j]).sum()),
                  different_candidate_pairs=int((labels[i] != labels[j]).sum()))
    if observed is None:
        return dict(**result,
                    abstention="No same-candidate pairs with matched different-ID controls")
    # One row per visit/RX, permuted within instrument strata. No receiver pairs
    # counted as revisits. Conditional labels and all feature dimensions stay intact.
    blocks = defaultdict(list)
    for k, r in enumerate(rr):
        blocks[r["edge"], r["rate"], r["receiver"], r["channel"]].append(k)
    rng, null = np.random.default_rng(917301), []
    for _ in range(permutations):
        permuted = labels.copy()
        for group in blocks.values():
            permuted[group] = rng.permutation(labels[group])
        value, _ = contrast(permuted, i, j, groups, scores)
        if value is not None:
            null.append(value)
    null = np.array(null)
    p = [(1 + int((null.max(axis=1) >= v).sum())) / (len(null) + 1) for v in observed]
    result.update(features=FEATURES, matched_same_pairs=len(used),
                  effect=observed.tolist(), valid_permutations=len(null),
                  familywise_permutation_p=p, all_scope_bonferroni_p=[min(1., v * 8) for v in p],
                  matched_pairs=[dict(left=rr[i[k]]["id"], right=rr[j[k]]["id"],
                                      candidate=int(labels[i[k]]), separation_s=pairs[k][2],
                                      cross_session=rr[i[k]]["session"] != rr[j[k]]["session"],
                                      shared_state=pairs[k][3], scores=scores[k].tolist())
                                 for k in used])
    # A global shuffle can destroy session-specific candidate prevalence and
    # manufacture significance. Preserve session too as a mandatory sensitivity.
    session_blocks = defaultdict(list)
    for k, r in enumerate(rr):
        session_blocks[r["session"], r["edge"], r["rate"], r["receiver"], r["channel"]].append(k)
    session_null = []
    for _ in range(permutations):
        permuted = labels.copy()
        for group in session_blocks.values():
            permuted[group] = rng.permutation(labels[group])
        value, _ = contrast(permuted, i, j, groups, scores)
        if value is not None:
            session_null.append(value)
    session_null = np.array(session_null)
    result["session_preserving_permutation_p"] = [
        (1 + int((session_null.max(axis=1) >= v).sum())) / (len(session_null) + 1)
        for v in observed]
    result["session_exchangeable_observations"] = sum(
        len(g) for g in session_blocks.values() if len(set(labels[g])) > 1)
    result["session_preserving_corrected_p"] = [
        min(1., p * 8) for p in result["session_preserving_permutation_p"]]
    sensitivity = []
    for gap in (15, 120, 7200):
        selected_groups = [g[np.array([pairs[k][2] >= gap for k in g])] for g in groups]
        effect, eligible = contrast(labels, i, j, selected_groups, scores)
        sensitivity.append(dict(minimum_separation_s=gap, matched_same_pairs=len(eligible),
                                effect=effect.tolist() if effect is not None else None))
    doppler_groups = defaultdict(list)
    for n, g in enumerate(groups):
        for k in g:
            difference = abs(rr[i[k]]["cfo_hz"] - rr[j[k]]["cfo_hz"])
            doppler_groups[n, int(np.searchsorted([10000, 30000, 100000], difference))].append(k)
    doppler_strata = [np.array(g) for g in doppler_groups.values()]
    effect, eligible = contrast(labels, i, j, doppler_strata, scores)
    result["doppler_sensitivity"] = dict(matched_same_pairs=len(eligible),
                                         effect=effect.tolist() if effect is not None else None)
    result["time_sensitivity"] = sensitivity
    # Predefined coordinate exclusion: symbol 2 has many nearly universal signs.
    sign = unit(arrays[-1][..., 4:])
    ablated = .5 * ((sign[np.array(chosen)[i], 0] * sign[np.array(chosen)[j], 1]).sum(1)
                     + (sign[np.array(chosen)[j], 0] * sign[np.array(chosen)[i], 1]).sum(1))
    effect, _ = contrast(labels, i, j, groups, ablated[:, None])
    result["exclude_symbol2_sign_effect"] = float(effect[0]) if effect is not None else None
    loo = []
    for candidate in sorted(set(labels[i[used]])):
        selected_groups = [g[(labels[i[g]] != candidate) & (labels[j[g]] != candidate)]
                           for g in groups]
        effect, remaining = contrast(labels, i, j, selected_groups, scores)
        loo.append(dict(removed_candidate=int(candidate), remaining_pairs=len(remaining),
                        effect=effect.tolist() if effect is not None else None))
    result["leave_one_candidate_out"] = loo
    # Preserve every candidate trajectory's visit/RX memberships jointly. This
    # intentionally has no power to reinterpret within-session identity equality.
    # It asks whether cross-session naming adds evidence beyond stable episodes.
    sessions = defaultdict(list)
    for k, r in enumerate(rr):
        sessions[r["session"]].append(k)
    trajectory_null = []
    for _ in range(permutations):
        permuted = labels.copy()
        for group in sessions.values():
            identities = np.unique(labels[group])
            mapping = dict(zip(identities, rng.permutation(identities), strict=True))
            permuted[group] = [mapping[v] for v in labels[group]]
        value, _ = contrast(permuted, i, j, groups, scores)
        if value is not None:
            trajectory_null.append(value)
    trajectory_null = np.array(trajectory_null)
    result["trajectory_preserving_max_p"] = [
        (1 + int((trajectory_null.max(axis=1) >= v - 1e-12).sum()))
        / (len(trajectory_null) + 1) for v in observed]
    return result


def main():
    OUT.mkdir(exist_ok=True)
    rows, arrays = load_features()
    np.savez_compressed(OUT / "features.npz", **dict(zip(FEATURES, arrays, strict=True)))
    (OUT / "rows.json").write_text(json.dumps(rows, indent=2) + "\n")
    results = [experiment(rows, arrays, scope, tier)
               for scope in ("same_channel", "cross_channel_session",
                             "same_channel_pairs", "cross_channel_session_pairs")
               for tier in ("all", "strong")]
    result = dict(experiments=results, rows=len(rows),
                  labeled=sum(r["norad_id"] is not None for r in rows),
                  dataset_counts=dict(Counter(r["dataset"] for r in rows)),
                  metadata_sha256=sha(SOURCE / "qualified-tracks.json"),
                  method_sha256=sha(Path(__file__)),
                  limitations="Exploratory conditional orbit IDs; no RF identities. Cross-half "
                  "comparisons reuse previously inspected frames. Strata match instrument/channel "
                  "pair/session relation/time bin/T-state overlap and pair pilot gap<=.05 "
                  "(<=.1 for separately reported mixed-instrument sensitivity). "
                  "Permutations assume exchangeability within instrument strata, not guaranteed "
                  "by time-varying signal quality. Max over four feature families; Bonferroni "
                  "over eight scopes/tiers. No arbitrary phase/lag optimization.")
    (OUT / "identity.json").write_text(json.dumps(result, indent=2) + "\n")
    for r in results:
        print(json.dumps({k: v for k, v in r.items() if k != "matched_pairs"}), flush=True)


if __name__ == "__main__":
    main()
