from types import SimpleNamespace as NS

from export_ds9_pilot_visit import strongest_pair


def test_selects_weaker_receiver_score_and_rejects_epoch_mismatch():
    choices = []
    for visit, margins, epochs in [
        (1, [0.99, 0.1], [0, 0]),
        (2, [0.7, 0.7], [0, 0]),
        (3, [0.9, 0.9], [0, 5]),
    ]:
        for rx in (0, 1):
            choices.append(
                (
                    NS(visit_index=visit, edge="lower", receiver_id=rx),
                    NS(fractional_margin=margins[rx], integer_epoch_sample=epochs[rx]),
                )
            )
    assert [p.visit_index for p, _ in strongest_pair(choices)] == [2, 2]
