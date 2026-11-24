"""Bind a saved candidate-only CFO view to the actual lean rank call."""

from collections import Counter
from contextlib import contextmanager
from copy import copy
from math import isfinite
from unittest.mock import patch

import numpy as np


class ProposalBindingError(RuntimeError):
    """Incomplete custody must exit the trial instead of invoking a fallback."""


def make_ledger(plan, graph, native, native_pin, *, expected=57):
    if plan["native_sha256"] != native_pin or graph["candidate_native_sha256"] != native_pin:
        raise ProposalBindingError("The original detector packet changed")
    rows = {row["observation_id"]: row for row in graph["observation_rows"]}
    changes = {
        oid: .5*row["interpolation_minus_center_hz"]
        for oid, row in plan["proposals"].items()
    }
    if (len(rows)!=len(graph["observation_rows"]) or len(changes)!=expected
            or graph["graph"]!=plan["scope"] or len(rows)!=graph["graph"]["assigned"]
            or not changes.keys() <= rows.keys()):
        raise ProposalBindingError("Require every sealed Graph row and all enrolled proposals")
    for oid, row in rows.items():
        raw = native.get(oid)
        facts = ("receiver_id", "edge", "channel", "actual_rf_hz", "sample_counter",
                 "measured_signed_cfo_hz")
        if raw is None or any(raw[key]!=row[key] for key in facts):
            raise ProposalBindingError("Raw CFO, clock, RF or signed opportunity changed")
        delta = changes.get(oid)
        if (row["half_blend_delta_hz"]!=delta or delta is not None and (
                not isfinite(delta) or abs(delta)>125 or not row["short"]
                or plan["proposals"][oid]["graph_alias_changes"]
                or row["donor_ids"]!=plan["proposals"][oid]["neighbors"])):
            raise ProposalBindingError("The original signed half-blend ledger changed")
    return rows, changes


def verify_graph(tracks, rows):
    seen = set()
    for track in tracks:
        ids = track["observation_ids"]
        by_index = dict(zip(sorted(track["indices"]), ids, strict=True))
        piece_by_id = {
            by_index[i]: ([track["key"], j], order)
            for j, piece in enumerate(track["pieces"])
            for order, i in enumerate(sorted(piece["indices"]))
        }
        if len(piece_by_id)!=len(ids) or seen.intersection(ids):
            raise ProposalBindingError("Ordinary Graph piece membership is ambiguous")
        for oid, t, value in zip(ids, track["times"], track["values"], strict=True):
            row = rows.get(oid)
            if (row is None or row["graph_time_s"]!=t or row["graph_lifted_cfo_hz"]!=value
                    or row["receiver_id"]!=track["receiver"]-1 or row["channel"]!=track["channel"]
                    or row["actual_rf_hz"]!=track["rf_hz"]
                    or (row["piece"],row["ordinal"])!=piece_by_id.get(oid)):
                raise ProposalBindingError("Live Graph differs in topology, time or lifted CFO")
        seen.update(ids)
    if seen!=rows.keys():
        raise ProposalBindingError("Live Graph omits sealed observation IDs")


def proposal_view(scan, changes):
    view = copy(scan)
    # Preserve immutable orbit/geometry arrays and the roster. Keep lazy
    # cache dictionaries private to this synchronous temporary view.
    for name, value in vars(scan).items():
        if type(value) is dict:
            setattr(view, name, value.copy())
    view.tracks = []
    for track in scan.tracks:
        values = np.array(track["values"], copy=True)
        for i, oid in enumerate(track["observation_ids"]):
            if oid in changes:
                values[i] += changes[oid]
        view.tracks.append(dict(track, values=values))
    view.groups = [(view.tracks[i]["key"], [view.tracks[i]]) for i in scan.curved]
    return view


def nominations(scan, nodes, cold_node):
    """Transport only proposal choices, with the released cold initialization."""
    expected = {scan.tracks[i]["key"] for i in scan.curved}
    result, ranked = [], []
    for node in nodes:
        aliases = node["aliases"]
        original = node["seed"]["rows"]
        if len(original)!=len(expected) or {row["component"] for row in original}!=expected:
            raise ProposalBindingError("A rank nomination changed the curved roster")
        fields = []
        for row, alias in zip(original, aliases, strict=True):
            j = int(row["candidate_index"])
            if (not 0<=j<len(scan.norads) or int(scan.norads[j])!=row["candidate_norad"]
                    or not row["active_curvature"] or int(alias)!=alias):
                raise ProposalBindingError("Invalid categorical nomination")
            fields.append(dict(component=row["component"], active_curvature=True,
                               candidate_index=j, candidate_norad=int(scan.norads[j])))
        result.append(cold_node(scan, dict(seed=dict(rows=fields), aliases=list(map(int, aliases)))))
        ranked.append([[x["component"], x["candidate_norad"], int(alias)]
                       for x, alias in zip(fields, aliases, strict=True)])
    if not result:
        raise ProposalBindingError("No nominated ordinal survived the original rank")
    return result, ranked


def raw_values(tracks, native, period):
    seen = set()
    for track in tracks:
        for oid, y in zip(track["observation_ids"], track["values"], strict=True):
            ref = native.get(oid)
            if ref is None or not isfinite(y):
                raise ProposalBindingError("Scientific fit received a foreign observation")
            original = ref["measured_signed_cfo_hz"]
            reconstructed = original+round((y-original)/period)*period
            if abs(reconstructed-y)>1e-8:
                raise ProposalBindingError("A nonnative CFO reached a scientific fit")
            seen.add(oid)
    return len(seen)


@contextmanager
def scoped_rank(cold, v5, normal, evidence, rows, native, changes, period, audit):
    """Select on the proposal view and keep the raw scan at every fit seam."""
    original_refine = cold.refine
    original_init = normal.__init__
    original_packet = evidence.selected_packet

    def refine(mode, prepared, region, bound):
        if audit.get("cold_calls") or mode!="race":
            raise ProposalBindingError("Require exactly one normal lean cold finalist race")
        audit["cold_calls"] = 1
        ordinary_rank = v5.ranked_initial_nodes
        proposal = None

        def rank(scan):
            nonlocal proposal
            if proposal is not None:
                raise ProposalBindingError("The rank view must be confined to one call")
            verify_graph(scan.tracks, rows)
            proposal = proposal_view(scan, changes)
            audit["changed_curved"] = sum(oid in changes for j in scan.curved
                                           for oid in scan.tracks[j]["observation_ids"])
            nodes = ordinary_rank(proposal)
            verify_graph(scan.tracks, rows)
            returned, ordered = nominations(scan, nodes, v5.cold_node)
            audit.update(ranked=ordered, graph_rows=len(rows), changes=len(changes),
                         curated_track_count=len(scan.tracks), curvature_classes=len(scan.curved))
            return returned

        def check_init(problem, scan, *args, **kwargs):
            if scan is not proposal:
                verify_graph(scan.tracks, rows)
                audit["raw_cold_models"] += 1
            original_init(problem, scan, *args, **kwargs)

        with (patch.object(v5, "ranked_initial_nodes", rank),
              patch.object(normal, "__init__", check_init)):
            answer = original_refine(mode, prepared, region, bound)
        if proposal is None or not audit["raw_cold_models"]:
            raise ProposalBindingError("Missing proposal or independently raw-scored finalist")
        audit["winning_proposal"] = answer[3]["branch"]
        return answer

    def packet(prepared, signed, fit):
        original = prepared["tracks"]["observations"]
        ids = {row["observation_id"] for row in original}
        if ids!=native.keys() or len(ids)!=len(original) or any(
            row["measured_cfo_hz"]!=native[row["observation_id"]]["measured_signed_cfo_hz"]
            for row in original
        ):
            raise ProposalBindingError("Terminal evidence lost its original native observations")
        verify_graph(prepared["tracks"]["tracks"], rows)
        used = raw_values(signed["scan"].tracks, native, period)
        if set(signed["arms"])!={"c0", "fitted_c"}:
            raise ProposalBindingError("Final science must contain both calibration arms")
        audit["evidence_calls"] += 1
        audit["evidence_raw_measurements"] = len(ids)
        audit["evidence_raw_track_points"] = used
        return original_packet(prepared, signed, fit)

    audit.update(raw_cold_models=0, evidence_calls=0)
    with (patch.object(cold, "refine", refine),
          patch.object(evidence, "selected_packet", packet)):
        yield
