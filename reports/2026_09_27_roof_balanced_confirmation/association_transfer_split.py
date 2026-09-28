"""Pure provenance-aware temporal split for association-transfer diagnostics."""
from __future__ import annotations

from collections import defaultdict
import operator


GUARD_NS = 60_000_000


class _UnionFind:
    def __init__(self, size): self.parent=list(range(size));self.rank=[0]*size
    def find(self, value):
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value
    def union(self, left, right):
        left=self.find(left);right=self.find(right)
        if left==right:return
        if self.rank[left] < self.rank[right]:left,right=right,left
        self.parent[right]=left
        if self.rank[left]==self.rank[right]:self.rank[left]+=1


def _key(value, name):
    if value is None:return None
    try: hash(value)
    except TypeError as error: raise ValueError(f"{name} must be hashable") from error
    return value


def _integer(value, name):
    if isinstance(value, bool): raise ValueError(f"{name} must be an integer")
    try: return operator.index(value)
    except TypeError as error: raise ValueError(f"{name} must be an integer") from error


def temporal_association_split(rows, guard_ns=GUARD_NS):
    """Split reserve observations into early A and late B without leakage."""
    values=list(rows)
    guard_ns=_integer(guard_ns,"guard_ns")
    if guard_ns < 0:
        raise ValueError("guard_ns must be a nonnegative integer")
    if not values: raise ValueError("at least one observation row is required")
    parsed=[];seen=set();seen_observation_ids=set()
    for row in values:
        if not isinstance(row,dict):raise ValueError("rows must be mappings")
        try:
            index=_integer(row["observation_index"],"observation_index")
            utc=_integer(row["utc_ns"],"utc_ns")
            start=_integer(row["sample_start"],"sample_start")
            end=_integer(row["sample_end"],"sample_end")
            group=row["source_group_id"];training=row["training"]
        except (KeyError,TypeError,ValueError) as error:
            raise ValueError("row lacks a valid required provenance field") from error
        if index in seen:raise ValueError("observation_index must be unique")
        seen.add(index)
        observation_id=row.get("observation_id")
        if observation_id is not None:
            observation_id=_key(observation_id,"observation_id")
            if observation_id in seen_observation_ids:
                raise ValueError("observation_id must be unique when supplied")
            seen_observation_ids.add(observation_id)
        if not isinstance(training,bool):raise ValueError("training must be boolean")
        if not isinstance(group,str) or not group:raise ValueError("source_group_id must be nonempty text")
        if end <= start:raise ValueError("sample interval must be nonempty half-open")
        parsed.append({"index":index,"utc":utc,"start":start,"end":end,
            "group":group,"training":training,
            "observation_id":observation_id,
            "opportunity":_key(row.get("opportunity_key"),"opportunity_key"),
            "pair":_key(row.get("physical_pair_key"),"physical_pair_key")})
    # Canonical order makes output independent of input iteration order.
    parsed.sort(key=lambda row:(row["index"],row["group"],row["utc"]))
    union=_UnionFind(len(parsed));key_members={}
    for number,row in enumerate(parsed):
        for name in ("opportunity","pair"):
            key=row[name]
            if key is None:continue
            combined=(name,key)
            if combined in key_members:union.union(number,key_members[combined])
            else:key_members[combined]=number
    by_group=defaultdict(list)
    for number,row in enumerate(parsed):by_group[row["group"]].append(number)
    for members in by_group.values():
        for offset,left in enumerate(members):
            a=parsed[left]
            for right in members[offset+1:]:
                b=parsed[right]
                if a["start"] < b["end"] and b["start"] < a["end"]:
                    union.union(left,right)
    components=defaultdict(list)
    for number in range(len(parsed)):components[union.find(number)].append(number)
    ordered=sorted(components.values(),key=lambda members:min(parsed[i]["index"] for i in members))
    training_components=[];eligible=[]
    for members in ordered:
        (training_components if any(parsed[i]["training"] for i in members)
         else eligible).append(members)
    eligible_rows=[parsed[i] for members in eligible for i in members]
    original_reserve=[row for row in parsed if not row["training"]]
    twice_midpoint=(min(row["utc"] for row in original_reserve)+
                    max(row["utc"] for row in original_reserve)
                    if original_reserve else None)
    early=[];late=[];guard=[]
    if twice_midpoint is not None:
        for members in eligible:
            times=[parsed[i]["utc"] for i in members]
            if all(2*value < twice_midpoint-2*guard_ns for value in times):early.extend(members)
            elif all(2*value > twice_midpoint+2*guard_ns for value in times):late.extend(members)
            else:guard.append(members)
    def indices(members):
        flat=(members if members and isinstance(members[0],int)
              else [i for component in members for i in component])
        return sorted(parsed[i]["index"] for i in flat)
    a_indices=indices(early);b_indices=indices(late)
    training_all=indices(training_components);guard_all=indices(guard)
    reserve_dropped=sorted(parsed[i]["index"] for component in training_components
                           for i in component if not parsed[i]["training"])
    supported=bool(a_indices and b_indices)
    reason=None if supported else (
        "no_reserve_component_after_training_exclusion" if not eligible_rows else
        "empty_both_partitions" if not a_indices and not b_indices else
        "empty_early_partition" if not a_indices else "empty_late_partition")
    assignments={index:"A" for index in a_indices}|{index:"B" for index in b_indices}
    assignments.update({index:"training_component" for index in training_all})
    assignments.update({index:"guard" for index in guard_all})
    for members in ordered:
        labels={assignments[parsed[i]["index"]] for i in members}
        if len(labels) != 1:
            raise AssertionError("dependency component crosses split labels")
    group_counts={}
    for group,members in sorted(by_group.items()):
        counts=defaultdict(int)
        for i in members:counts[assignments[parsed[i]["index"]]]+=1
        group_counts[group]={name:counts[name] for name in
            ("A","B","training_component","guard")}
    return {
        "supported":supported,"unsupported_reason":reason,
        "A_observation_indices":a_indices,"B_observation_indices":b_indices,
        "twice_midpoint_utc_ns":twice_midpoint,
        "midpoint_utc_ns":twice_midpoint//2 if twice_midpoint is not None else None,
        "midpoint_utc_ns_floor":twice_midpoint//2 if twice_midpoint is not None else None,
        "midpoint_has_half_ns":bool(twice_midpoint is not None and twice_midpoint%2),
        "guard_ns":guard_ns,
        "training_component_observation_indices":training_all,
        "reserve_dropped_with_training_indices":reserve_dropped,
        "guard_excluded_observation_indices":guard_all,
        "counts":{"rows":len(parsed),"components":len(ordered),
            "training_components":len(training_components),
            "reserve_dropped_with_training":len(reserve_dropped),
            "guard_components":len(guard),"guard_excluded":len(guard_all),
            "A":len(a_indices),"B":len(b_indices)},
        "provenance_group_counts":group_counts,
        "observation_assignments":[{
            "observation_index":row["index"],
            "observation_id":row["observation_id"],
            "utc_ns":row["utc"], "training":row["training"],
            "source_group_id":row["group"],
            "sample_start":row["start"], "sample_end":row["end"],
            "opportunity_key":row["opportunity"],
            "physical_pair_key":row["pair"],
            "split_label":assignments[row["index"]],
        } for row in parsed],
    }
