"""History proposals must pass both current scans and the fixed RF support."""

from probe_ds23_rf_supported_history import select_supported


def trial(fraction, score=10., pass_c0=True, pass_fit=True):
    return dict(fraction=fraction,arms=dict(
        c0=dict(compatible=pass_c0,negative_twice_elbo=score),
        fitted_c=dict(compatible=pass_fit,negative_twice_elbo=score)))


def test_highest_history_fraction_must_pass_both_arms_and_rf_loss_budget():
    trials=[trial(0.),trial(.25),trial(.5,pass_fit=False),trial(.75,score=17.),trial(1.,pass_c0=False)]
    assert select_supported(trials,10.)["fraction"]==.25


def test_unavailable_physical_support_has_no_history_output():
    assert select_supported([trial(1.,pass_fit=False)],10.) is None
    assert select_supported([trial(1.,score=16.)],10.)["fraction"]==1.
