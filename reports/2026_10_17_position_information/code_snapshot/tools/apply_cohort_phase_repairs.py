"""Apply uniquely passing curved-family phase proposals at fixed supplied GPS."""

import hashlib
import json
from pathlib import Path

from associate_merged_track_catalogue import load_tracks, write
from evaluate_robust_curve_reassociation import population_association
from inventory_clipped_phase_cohort import ROOT, load_study

REPORT = ROOT / "reports/2026_10_17_cohort_phase_repair/curved_only"
RAW_COUNTS = [4797, 3524, 3988, 3719, 4056]


class FamilyBindings:
    """The final evaluator receives immutable prior and jointly vetted labels."""

    def __init__(self, study, fixed_labels):
        self.study, self.fixed_labels = study, fixed_labels
        self.tracks, self.sky = study.tracks, study.sky

    def associate(self, fit):
        return self.study.associate(fit, fixed_labels=self.fixed_labels)


def run():
    output = REPORT / "association"
    output.mkdir(exist_ok=False)
    summaries = []
    for number in range(1, 6):
        case = f"DSX01-S{number:02d}"
        nominations = json.loads((REPORT / "inventory" / case / "nominations.json").read_text())
        approved = []
        proofs = {}
        for nomination in nominations:
            paths = [
                REPORT / "competition" / case / str(nomination["norad"]) / arm / "summary.json"
                for arm in ("c0", "fitted_c")
            ]
            if not all(p.exists() for p in paths):
                # Scalar failures never proceeded to a full-bank competition.
                if any(
                    json.loads(
                        (
                            REPORT
                            / "screen"
                            / case
                            / str(nomination["norad"])
                            / arm
                            / "summary.json"
                        ).read_text()
                    )["passing_candidates"]
                    for arm in ("c0", "fitted_c")
                ):
                    raise ValueError("a scalar pass is missing its candidate competition")
                continue
            studies = [json.loads(p.read_text()) for p in paths]
            if all(r["uniquely_passing_nomination"] for r in studies):
                if any(r["members"] != nomination["members"] for r in studies):
                    raise ValueError("candidate competition changed the nomination population")
                approved.append((nomination, studies))
                for p in paths:
                    proofs[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
        for fitted_c in (False, True):
            arm = "fitted_c" if fitted_c else "c0"
            study, fit, source, recording, background = load_study(case, fitted_c)
            before = study.associate(fit)
            prior = json.loads(
                (REPORT / "inventory" / case / arm / "baseline_association.json").read_text()
            )
            for a, b in zip(before["rows"], prior["rows"], strict=True):
                if (
                    a["component"] != b["component"]
                    or a["candidate_norad"] != b["candidate_norad"]
                    or a["compatible"] != b["compatible"]
                    or abs(a["rms_hz"] - b["rms_hz"]) > 1e-5
                ):
                    raise ValueError("baseline no longer reproduces frozen inventory")
            labels = {
                r["component"]: r["candidate_norad"] for r in before["rows"] if r["compatible"]
            }
            established_norads = {
                r["candidate_norad"]
                for r in before["rows"]
                if r["compatible"] and r["active_curvature"]
            }
            after_fit = dict(fit, phases_s=list(fit["phases_s"]))
            lookup = {int(n): j for j, n in enumerate(study.sky["norad"])}
            updates = []
            for nomination, studies in approved:
                n = nomination["norad"]
                if n in established_norads or set(nomination["members"]) & labels.keys():
                    raise ValueError("new phase attempts to alter an established binding")
                row = studies[int(fitted_c)]["passing_candidates"][0]
                after_fit["phases_s"][lookup[n]] = row["phase_s"]
                labels.update({key: n for key in nomination["members"]})
                updates.append(
                    dict(
                        norad=n,
                        phase_s=row["phase_s"],
                        original_phase_s=fit["phases_s"][lookup[n]],
                        calibration_members=nomination["members"],
                        calibration_points=nomination["points"],
                    )
                )
            if fit["beta"] != after_fit["beta"] or any(
                fit["phases_s"][lookup[n]] != after_fit["phases_s"][lookup[n]]
                for n in established_norads
            ):
                raise ValueError("established predictions changed")
            association = population_association(
                FamilyBindings(study, labels), after_fit, load_tracks(recording), background
            )
            mapping = {t["key"]: t for t in study.tracks}
            old_ids = {
                oid: r["candidate_norad"]
                for r in before["rows"]
                if r["compatible"]
                for oid in mapping[r["component"]]["observation_ids"]
            }
            new_ids = {
                oid: r["candidate_norad"]
                for r in association["association"]["rows"]
                if r["compatible"]
                for oid in mapping[r["component"]]["observation_ids"]
            }
            old_curved_ids = {
                oid
                for r in before["rows"]
                if r["compatible"] and r["active_curvature"]
                for oid in mapping[r["component"]]["observation_ids"]
            }
            if not old_curved_ids <= new_ids.keys() or any(
                new_ids[o] != n for o, n in old_ids.items() if o in new_ids
            ):
                raise ValueError("incremental association changed an established curved binding")
            bykey = {r["component"]: r for r in association["association"]["rows"]}
            for update in updates:
                if not all(
                    bykey[k]["compatible"] and bykey[k]["candidate_norad"] == update["norad"]
                    for k in update["calibration_members"]
                ):
                    raise ValueError("joint curved calibration family failed final physical checks")
            gained = set(new_ids) - old_ids.keys()
            added_curved = sum(
                r["points"]
                for r in association["association"]["rows"]
                if r["compatible"]
                and r["active_curvature"]
                and mapping[r["component"]]["observation_ids"][0] in gained
            )
            folder = output / case / arm
            folder.mkdir(parents=True)
            write(folder / "fit.json", after_fit)
            write(folder / "association.json", association)
            write(folder / "updates.json", updates)
            write(
                folder / "protocol.json",
                dict(
                    source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    original_fit_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    competition_sha256=proofs,
                    hardware_frozen=True,
                    old_curved_supported_phases_frozen=True,
                    old_linear_matches_do_not_lock_or_veto_curved_phase_proposals=True,
                    phase_proposals_ranked_by_curved_measurements_only=True,
                    jointly_vetted_curved_family_labels_preserved_in_final_association=True,
                    every_member_still_requires_all_frequency_and_support_gates=True,
                    linear_tracks_can_associate_but_never_calibrate=True,
                    supplied_position_fixed=True,
                    not_a_localization_result=True,
                ),
            )
            row = dict(
                case=case,
                arm=arm,
                before_points=len(old_ids),
                after_points=len(new_ids),
                gained_points=len(gained),
                gained_curved_points=added_curved,
                gained_linear_points=len(gained) - added_curved,
                lost_points=len(old_ids.keys() - new_ids.keys()),
                relabelled_points=0,
                raw_glrt_points=RAW_COUNTS[number - 1],
                percent_raw_glrt=100 * len(new_ids) / RAW_COUNTS[number - 1],
                merged_tracks=association["merged_tracks"],
                points_per_merged_track=len(new_ids) / association["merged_tracks"],
                updates=updates,
            )
            summaries.append(row)
            write(folder / "summary.json", row)
            print(json.dumps(row), flush=True)
    write(output / "summary.json", summaries)


if __name__ == "__main__":
    run()
