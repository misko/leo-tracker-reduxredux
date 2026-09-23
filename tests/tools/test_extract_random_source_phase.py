from copy import deepcopy

from tools.research.extract_random_source_phase import select_training_branch


def test_branch_choice_uses_only_training_even_and_weights_groups_equally():
    def row(group, partition, margin):
        return dict(
            group_id=group,
            partition=partition,
            frame=dict(even=dict(coherence_margin=margin, search_boundary=False), odd={}),
        )

    first = [row(0, "train", 0.1)] * 20 + [row(3, "train", 0.5), row(1, "held", 0.9)]
    second = [row(0, "train", 0.25), row(3, "train", 0.25), row(1, "held", 0.01)]
    selected, scores = select_training_branch([first, second])
    assert selected == 0
    assert scores[0] > scores[1]
    altered = deepcopy([first, second])
    for branch in altered:
        for item in branch:
            item["frame"]["odd"] = {"coherence_margin": 1e9}
            if item["partition"] == "held":
                item["frame"]["even"] = None
    assert select_training_branch(altered) == (selected, scores)


def test_boundary_fit_cannot_win_branch_choice():
    rows = [
        [
            dict(
                group_id=0,
                partition="train",
                frame=dict(even=dict(coherence_margin=margin, search_boundary=boundary)),
            )
        ]
        for margin, boundary in [(1.0, True), (0.1, False)]
    ]
    assert select_training_branch(rows)[0] == 1
