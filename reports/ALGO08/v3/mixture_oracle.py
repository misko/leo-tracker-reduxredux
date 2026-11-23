"""Diagnostic-only selection with frozen cold data and supplied oracle labels."""

from collections import Counter, defaultdict

import numpy as np
from scipy.special import logsumexp

from leo.analysis.research.phase_linear_geometry import phase_linear_frequency, prepare_phase_geometry

from mixture_position import ALIAS_NEIGHBORS, DF, PERIOD, lane_design, profile, shortlist


MODES = ("strict_slate", "complete_curved")


def choose_subset(ids, owners, allowed):
    groups = defaultdict(list)
    for oid in ids:
        pair = owners.get(oid)
        if pair is not None and pair in allowed:
            groups[pair].append(oid)
    if not groups:
        return None, ()
    pair = min(groups, key=lambda key: (-len(groups[key]), key))
    return pair, groups[pair]


def capture_labels(context, packet):
    def curved(problem):
        result = {}
        for row, index, section, alias in zip(problem.rows, problem.members, problem.slices, problem.alias, strict=True):
            pair = int(row["candidate_norad"]), int(alias)
            ids = problem.scan.tracks[index]["observation_ids"]
            for oid, keep in zip(ids, problem.keep[section], strict=True):
                if keep:
                    if oid in result:
                        raise ValueError("Duplicate conditional observation")
                    result[oid] = pair
        return result

    values = {}
    for arm, (problem, _) in context["problems"].items():
        candidates = curved(problem)
        published = packet["rows"][arm]
        exact = {r["observation_id"]: candidates[r["observation_id"]]
                 for r in published if r["role"] == "conditional"}
        if any(exact[row["observation_id"]][0] != row["norad"]
               for row in published if row["role"] == "conditional"):
            raise ValueError("Stock selected aliases disagree with its published owners")
        values[arm] = dict(curved=exact, roles=dict(Counter(row["role"] for row in published)))
    if values["c0"] != values["fitted_c"]:
        raise ValueError("The two accepted v3 arms assign different owners or aliases")
    return values["c0"]


def candidate_aliases(row, beta):
    applied = row["design"][:, :len(beta)] @ beta
    raw = row["raw"] - applied
    center = raw.mean(axis=-1) - row["tangent"].mean(axis=-1) * row["phase"]
    return raw, np.rint(-center / PERIOD).astype(int)[:, None] + ALIAS_NEIGHBORS, applied


def choice(row, cold, beta, index, alias, frequency, tangent, widths, sigma):
    raw, aliases, applied = candidate_aliases(row, beta)
    all_square = profile(raw[:, None, :] + PERIOD * aliases[..., None], row["tangent"][:, None, :],
                         sigma, row["widths"][:, None])[0]
    selected_raw = cold["sample"] - cold["q"] * frequency + PERIOD * alias - applied
    cost, phase, intercept, residual, _ = profile(selected_raw, cold["q"] * tangent, sigma, widths[index])
    original = np.flatnonzero(row["labels"] == index)
    present = len(original) > 0 and alias in aliases[original[0]]
    scores = all_square.ravel() if present else np.append(all_square.ravel(), cost)
    n = len(selected_raw)
    prior = np.log(.9 / max(1, scores.size))
    component = prior - .5 * (DF + n) * np.log1p(cost / DF)
    z = cold["sample"] - cold["sample"].mean()
    null = np.log(.1) + n * np.log(sigma / 450.) - .5 * (DF + n) * np.log1p((z @ z) / (DF * 450.**2))
    total = logsumexp(np.append(prior - .5 * (DF + n) * np.log1p(scores / DF), null))
    return dict(index=index, alias=alias, phase_s=float(phase), bias_hz=float(intercept),
                rms_hz=float(np.sqrt(np.mean(residual**2))), weight=float(np.exp(component - total)),
                null=float(np.exp(null - total)), retained=True)


def frozen_at_endpoint(prepared, region, proposal):
    bank = prepared["sky"]["bank"]
    catalogue = [int(value) for value in bank["norad"]]
    if catalogue != proposal["catalogue"]:
        raise ValueError("Causal candidate bank differs from the blind proposal")
    original = {track["key"]: track for track in prepared["tracks"]["tracks"]}
    arm = proposal["arms"]["c0"]
    tracks = []
    for previous in arm["tracks"]:
        track = original[previous["key"]]
        if list(track["observation_ids"]) != previous["observations"]:
            raise ValueError("Prepared observations differ from the frozen blind graph")
        times, values = np.asarray(track["times"]), np.asarray(track["values"])
        choose = np.linspace(0, len(times) - 1, min(9, len(times)), dtype=int)
        sample = times[choose]
        tracks.append(dict(key=track["key"], times=sample, sample=values[choose], design=lane_design(track, sample),
                           q=track["rf_hz"] / 11.5e9, observations=previous["observations"], receiver=track["receiver"]))
    all_times = np.unique(np.concatenate([row["times"] for row in tracks]))
    for row in tracks:
        row["indices"] = np.searchsorted(all_times, row["times"])
    geometry = prepare_phase_geometry(bank, all_times)
    width = np.maximum(1., bank["phase_sigma_s"])
    sigma = float(prepared["noise"]["constant_radio_sigma_hz"])
    point = arm["east_north_km"]
    latitude, longitude = region.latlon(point)
    frequency, _, tangent = phase_linear_frequency(geometry, latitude, (longitude + 180.) % 360. - 180.)
    ranked = shortlist(tracks, width, geometry, region, point, sigma)
    for row, previous in zip(ranked, arm["tracks"], strict=True):
        if [catalogue[int(i)] for i in row["labels"]] != previous["shortlist"]:
            raise ValueError("Reconstructed endpoint shortlist differs from the frozen proposal")
    return tracks, ranked, frequency, tangent, width, sigma, np.asarray(arm["receiver_prior_units"])


def proposal_for(proposal, frozen, labels, mode):
    tracks, ranked, frequency, tangent, widths, sigma, beta = frozen
    catalogue = proposal["catalogue"]
    lookup = {owner: i for i, owner in enumerate(catalogue)}
    owners = labels["curved"]
    counts, selected, masks = Counter(), [], {}
    for cold, row in zip(tracks, ranked, strict=True):
        _, aliases, _ = candidate_aliases(row, beta)
        slate = {(catalogue[int(i)], int(alias)) for i, pair in zip(row["labels"], aliases, strict=True) for alias in pair}
        slate_norads = set(norad for norad, _ in slate)
        original = [(oid, owners[oid]) for oid in cold["observations"] if oid in owners]
        counts["conditional_on_original_curves"] += len(original)
        counts["causal_bank"] += sum(pair[0] in lookup for _, pair in original)
        counts["slate_norad"] += sum(pair[0] in slate_norads for _, pair in original)
        counts["slate_owner_and_alias"] += sum(pair in slate for _, pair in original)
        allowed = slate if mode == "strict_slate" else {pair for _, pair in original if pair[0] in lookup}
        counts["before_single_owner_restriction"] += sum(pair in allowed for _, pair in original)
        pair, ids = choose_subset(cold["observations"], owners, allowed)
        if pair is None:
            continue
        norad, alias = pair
        i = lookup[norad]
        indexes = cold["indices"]
        record = choice(row, cold, beta, i, alias, frequency[i, indexes], tangent[i, indexes], widths, sigma)
        selected.append(dict(record, key=cold["key"], norad=norad, observations=ids, receiver=cold["receiver"]))
        masks[cold["key"]] = set(ids)
    counts["retained"] = sum(map(len, masks.values()))
    counts["curved_outside_original_graph"] = len(owners) - counts["conditional_on_original_curves"]
    original_arms = proposal["arms"]
    common = dict(original_arms["c0"], tracks=selected, sampled_owner_points=counts["retained"],
                  families=len({row["norad"] for row in selected}), receivers=len({row["receiver"] for row in selected}))
    return dict(proposal, arms=dict(original_arms, c0=common)), masks, dict(counts)
