"""Choose short-scan detections using their pre-refinement frequencies, then publish refined measurements."""

from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch


CFO = "fractional_tracking_cfo_hz"
FACTOR_FIELDS = ("candidate_rank", "integer_epoch_sample", "fractional_epoch_offset_samples",
                 CFO, "fractional_exact_score", "fractional_control_score")


class FrequencyChanges:
    def __init__(self):
        self.changed = {}
        self.attempted = 0
        self.by_attempt = None

    @contextmanager
    def capture(self, policy):
        amend = policy.amend
        self.by_attempt = {}

        def observe(original, *args):
            amended, reason = amend(original, *args)
            (before,), (after,) = original, amended
            if before[3] != after[3]:
                self.by_attempt[self.attempted] = (before[3], after)
            self.attempted += 1
            return amended, reason

        with patch.object(policy, "amend", observe):
            yield

    def bind_attempts(self, document):
        from anchor_exposure import enroll

        if self.by_attempt is None:
            return
        count = 0
        for row, event in zip(document["source"]["probes"], enroll(document), strict=True):
            if event[4] != "short" or not row["candidates"]:
                continue
            if count in self.by_attempt:
                old, final = self.by_attempt[count]
                (factor,) = row["candidates"]
                if tuple(factor[k] for k in FACTOR_FIELDS) != final:
                    raise ValueError("Captured refinement and signed native result differ")
                self.changed[row["visit_index"], row["receiver_id"]] = old, final[3]
            count += 1
        if count != self.attempted or len(self.changed) != len(self.by_attempt):
            raise ValueError("The short-positive schedule differs from the captured refinements")

    def original_rows(self, probes):
        rows, restored = [], set()
        for probe in probes:
            key = (probe["visit_index"], probe["receiver_id"])
            change = self.changed.get(key)
            if change is not None:
                if (key in restored or len(probe["candidates"]) != 1
                        or probe["candidates"][0][CFO] != change[1]):
                    raise ValueError("Frequency witness differs from the acquired probe")
                factor = dict(probe["candidates"][0], **{CFO: change[0]})
                probe = dict(probe, candidates=[factor])
                restored.add(key)
            rows.append(probe)
        if len(restored) != len(self.changed):
            raise ValueError("Missing acquired probe for a captured frequency change")
        return rows


def select_refined(native, recipe, changes, session, inventory, receipt_file):
    import empty_bootstrap as staged
    from held_anchor_route_publication import SELECTOR_SOURCES, SETTINGS
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.variants import carrier_continuation

    here = Path(__file__).resolve().parent
    for name, pin in SELECTOR_SOURCES.items():
        staged.checked(here / name, pin)
    from anchor_cycle_route import select_route
    from anchor_holds import history_rows
    continuation_pin = staged.EXTRA_SOURCES[staged.CONTINUATION]
    staged.checked(Path(carrier_continuation.__file__), continuation_pin)
    if "fixed_epoch_cfo_refinement" not in recipe:
        raise ValueError("A frozen fixed-epoch measurement recipe is required")
    original_pin = canonical_digest(recipe)
    staged.bind_native(native, session, inventory, original_pin[7:])
    refined = native["source"]["probes"]
    changes.bind_attempts(native)
    rows = changes.original_rows(refined)
    view = dict(native, source=dict(native["source"], probes=rows))
    choice = select_route(view)
    if choice["route"] == "history":
        selected = history_rows(rows)
        projected = [new if kept["candidates"] else dict(new, candidates=[])
                     for new, kept in zip(refined, selected, strict=True)]
    elif choice["route"] == "unfiltered":
        projected = refined
    else:
        raise ValueError("Unexpected held-cycle selection")
    policy = dict(selector_sources=SELECTOR_SOURCES, continuation_sha256=continuation_pin,
                  wrapper_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), settings=SETTINGS,
                  input="pre-refinement short and full detections",
                  output="retain refined measurement on each selected lane")
    combined = dict(recipe, held_cycle_before_cfo=policy)
    detector = canonical_digest(combined).removeprefix("sha256:")
    raw = native["source"]["raw_recording_authority_digest"]
    analysis = canonical_digest(["cancellation", raw, detector, projected])
    packet = dict(native, source=dict(native["source"], probes=projected, analysis_manifest_sha256=analysis),
                  provenance=dict(native["provenance"], detector_sha256="sha256:" + detector,
                                  run_id="blind-compact-" + analysis[7:39]))
    staged.bind_native(packet, session, inventory, detector)
    detail = dict(choice=choice, input_recipe_sha256=original_pin, input_native_sha256=canonical_digest(native),
                  pre_refinement_probes_sha256=canonical_digest(rows), selected_native_sha256=canonical_digest(packet),
                  selected_recipe_sha256="sha256:" + detector, input_inventory=inventory, session=session,
                  selected=sum(bool(row["candidates"]) for row in projected),
                  measured=sum(bool(row["candidates"]) for row in refined), changed=len(changes.changed),
                  refinement_attempts=changes.attempted, policy=policy)
    with Path(receipt_file).open("x") as stream:
        json.dump(detail, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return packet, combined, detector, detail
