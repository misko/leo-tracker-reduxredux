"""Reconstruct the saved curved-support decisions before comparing published owners."""

from collections import Counter, defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Curve:
    radio: int
    channel: int
    rf_hz: float
    observations: tuple[str, ...]

    @property
    def lane(self):
        return self.radio, self.channel, self.rf_hz


def assignment(signature):
    result = {key:(int(index),int(norad),int(alias)) for key,index,norad,alias in signature}
    if len(result) != len(signature):
        raise ValueError("Duplicate cold component")
    return result


def alternative_ids(curves, key, entry):
    row = curves[key].observations
    start, stop = entry["start_index"], entry["stop_index"]
    if not 0 <= start < stop <= len(row) or stop-start != entry["points"]:
        raise ValueError("Saved salvage span is outside the original ordered observations")
    return row[start:stop]


def as_owners(curves, assign, spans=None):
    owners = {}
    for key, (_,norad,_) in assign.items():
        ids = curves[key].observations if spans is None else spans[key]
        for identity in ids:
            if identity in owners:
                raise ValueError("Curved observations are not disjoint")
            owners[identity] = (norad,"conditional")
    return owners


def drop(active, rejected):
    if len(set(rejected)) != len(rejected) or not set(rejected) <= active.keys():
        raise ValueError("Saved screen rejected an unbound curved component")
    return {k:v for k,v in active.items() if k not in rejected}


def nominate(curves, finalists, winner, first, salvage):
    """Choose at most one early candidate with uniquely strongest opposite-radio support."""
    reviewed = {}
    for key, row in salvage.items():
        if row is None or alternative_ids(curves,key,row) != curves[key].observations:
            continue
        value = row["candidate_index"],row["norad"],row["alias"]
        if value != winner[key] or any(candidate.get(key) != value for candidate in finalists):
            continue
        peer_lanes = {curves[k].lane for k, (_, norad, _) in first.items()
                      if norad == value[1] and curves[k].radio != curves[key].radio}
        if peer_lanes:
            reviewed[key] = len(peer_lanes)
    best = max(reviewed.values(), default=0)
    choices = [key for key, count in reviewed.items() if count==best]
    return dict(components=reviewed, nominee=choices[0] if len(choices)==1 else None)


def activate(nomination, ordinary_eligible):
    """The existing numerical gates remain necessary after the early nomination."""
    nominee = nomination["nominee"]
    return nominee if len(ordinary_eligible)>1 and nominee in ordinary_eligible else None


def prepare(curves, risk):
    attempt, = risk["lean_attempts"]
    cold, support, repair = (attempt[k] for k in ("cold","support","repair"))
    finalists = [assignment(value) for value in risk["two_centre_rank"]["finalist_signatures"]]
    if len(finalists) != 3 or not 1 <= cold["branch"] <= len(finalists):
        raise ValueError("The marked initial branch is not an available paid finalist")
    winner = finalists[cold["branch"]-1]
    if not set().union(*[f.keys() for f in finalists]) <= curves.keys():
        raise ValueError("The ranked cold assignments do not bind original Graph components")
    first = drop(winner,support["cold_rejected_tracks"])
    salvage = {r["component"]:r["selected"] for r in support["salvage"]}
    shortlists = {r["component"]:r["candidate_indices"] for r in attempt["salvage_shortlists"]}
    if (len(salvage)!=len(support["salvage"]) or len(shortlists)!=len(attempt["salvage_shortlists"])
            or salvage.keys()!=shortlists.keys() or salvage.keys()!=set(winner)-set(first)):
        raise ValueError("The stored shortlist and first-screen rejections differ")
    nomination = nominate(curves,finalists,winner,first,salvage)
    accepted = attempt["provisional_salvage"]["eligible"]
    nomination.update(existing_eligible=accepted, invoked=activate(nomination,accepted))
    expanded, spans = dict(first), {k:curves[k].observations for k in first}
    for key,row in salvage.items():
        if row is None:
            continue
        value = row["candidate_index"],row["norad"],row["alias"]
        if value[0] not in shortlists[key]:
            raise ValueError("The selected branch was outside its archived shortlist")
        expanded[key] = value
        spans[key] = alternative_ids(curves,key,row)
    second = drop(expanded,support["second_curved_rejections"])
    final = drop(second,repair["removed_curved"])
    stages = dict(cold=as_owners(curves,winner),first=as_owners(curves,first),
                  before_second=as_owners(curves,expanded,spans),second=as_owners(curves,second,spans),
                  repaired=as_owners(curves,final,spans))
    if (len(stages["cold"])!=support["full_curved"] or len(stages["first"])!=support["initial_curved"]
            or len(stages["before_second"])-len(stages["first"])!=support["curved_restored"]
            or len(stages["second"])!=support["rechecked_curved"]
            or repair["rejection_counts"]["curved"]!=[len(stages["second"]),len(stages["second"])-len(stages["repaired"])]
            or repair["status"]!="complete" or attempt["provisional_salvage"]["status"]=="adopted"):
        raise ValueError("The discrete replay did not reproduce the charted measured support")
    options = defaultdict(set)
    for row in support["salvage"]:
        for alternative in row["alternatives"]:
            for oid in alternative_ids(curves,row["component"],alternative):
                options[oid].add(alternative["norad"])
    offered = nomination["invoked"]
    proposal = {} if offered is None else as_owners(curves,{offered:expanded[offered]},spans)
    return dict(stages=stages, nominee=nomination, options=options, proposal=proposal,
                finalists=[as_owners(curves,f) for f in finalists],cold_assignment=winner,
                second_dropped=support["second_curved_rejections"],signed_status=attempt["signed"]["status"],
                clocks={name:attempt[name] for name in ("predictive_clocks","initial_gate_clocks","cold_clocks",
                      "salvage_clocks","finish_clocks","repair_fit_clocks","repair_prepare_clocks")})


def score(replay, curves, named, charted):
    installed_only = {oid:owner for oid,owner in named.items() if oid not in charted}
    common = named.keys() & charted.keys()
    conditional = {oid:row for oid,row in charted.items() if row[1]=="conditional"}
    new = replay["stages"]["repaired"]
    if conditional != new:
        # Keep an informative exact comparison for trials where a later stage
        # changed the repaired conditional roster.
        parity = dict(shared=sum(conditional.get(key)==value for key,value in new.items()),
                      changed=len(conditional.keys() & new.keys())
                             -sum(conditional.get(key)==value for key,value in new.items()),
                      publication_only=len(conditional.keys()-new.keys()),replay_only=len(new.keys()-conditional.keys()))
    else:
        parity = dict(shared=len(new),changed=0,publication_only=0,replay_only=0)
    group = {oid:k for k,c in curves.items() for oid in c.observations}
    missing = {oid:owner for oid,owner in installed_only.items() if owner[1]=="conditional"}
    first_failure, stages_by_curve = Counter(), defaultdict(Counter)
    for oid,owner in missing.items():
        stages = replay["stages"]
        key = group.get(oid,"untracked")
        if oid not in stages["cold"]:
            cause = "not_in_cold_winner"
        elif stages["cold"][oid]!=owner:
            cause = "different_cold_owner"
        elif stages["before_second"].get(oid)!=owner:
            cause = "not_restored_to_same_owner_before_second"
        elif oid not in stages["second"]:
            cause = "lost_at_second"
        elif oid not in stages["repaired"]:
            cause = "lost_at_paired_repair"
        else:
            cause = "still_present_after_repair"
        first_failure[cause] += 1
        stages_by_curve[key][cause] += 1
    offered = replay["proposal"]
    return dict(installed=len(named),charted=len(charted),same=sum(named[k]==charted[k] for k in common),
                different=sum(named[k]!=charted[k] for k in common),installed_only=len(installed_only),
                charted_only=len(charted.keys()-named.keys()),repaired_publication_parity=parity,
                installed_only_roles=dict(Counter(row[1] for row in installed_only.values())),
                installed_only_conditional_exact_stage={name:sum(owners.get(k)==v for k,v in missing.items())
                                                       for name,owners in replay["stages"].items()},
                installed_only_conditional_first_difference=dict(first_failure),
                installed_only_conditional_curves={key:dict(counts) for key,counts in stages_by_curve.items()},
                installed_only_conditional_any_paid_finalist=sum(any(f.get(k)==v for f in replay["finalists"])
                                                                for k,v in missing.items()),
                installed_only_conditional_any_saved_salvage=sum(v[0] in replay["options"].get(k,()) for k,v in missing.items()),
                nominated_points=len(offered),nominated_installed_only=sum(missing.get(k)==v for k,v in offered.items()),
                nominated_existing=sum(charted.get(k)==v for k,v in offered.items()),
                nominated_without_installed_owner=sum(named.get(k)!=v for k,v in offered.items()))
