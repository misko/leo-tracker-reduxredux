from itertools import combinations

from leo.analysis.localization_v3.history_policy import pair_passes

from blind_joint_repair import small_rejection
from reports.ALGO08.v3.repair_cap_prefix import INSTANT, first_arm_certificate


def arm(support, failed):
    return dict(active_points=sum(support), endpoint_east_north_km=[0, 0], linear_gates=[],
                gates={"tracks": [dict(component=str(i), points=points, compatible=i not in failed)
                                  for i, points in enumerate(support)]})


def test_first_arm_upper_cap_proves_every_second_arm_continuation():
    support = [6, 20, 24, 50]
    ruined = {0}
    c0 = arm(support, ruined)
    assert first_arm_certificate(c0, 100)["refusal"] == INSTANT

    for size in range(len(support)+1):
        for indices in combinations(range(len(support)), size):
            failed = ruined | set(indices)
            pair = dict(c0=c0, fitted_c=arm(support, set(indices)))
            # A large hypothetical track denominator isolates the curved cap.
            full = dict(tracks=(100, len(failed)), curved=(100, sum(support[i] for i in failed)), predictive=(0, 0))
            assert not pair_passes(pair)
            assert not small_rejection(full)


def test_exact_cap_boundary_and_zero_failures_preserve_original_path():
    support = [5, 95]
    qualifying = arm(support, {0})
    assert first_arm_certificate(qualifying, 100)["refusal"] is None
    assert small_rejection(dict(tracks=(100, 1), curved=(100, 5), predictive=(100, 0)))
    passing = arm(support, set())
    assert first_arm_certificate(passing, 100)["refusal"] is None
    assert pair_passes(dict(c0=passing, fitted_c=passing))


def test_incomplete_and_duplicate_gates_abstain():
    bad = arm([6, 94], {0})
    assert first_arm_certificate(bad, 99) is None
    bad["gates"]["tracks"][1]["component"] = "0"
    assert first_arm_certificate(bad, 100) is None

    inconsistent = arm([6, 94], {0})
    inconsistent["gates"]["tracks"].pop()
    assert first_arm_certificate(inconsistent, 100) is None
