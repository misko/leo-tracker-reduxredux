from tools.research import replay_long_dwell_multiscale_phase as frontend
from tools.research.replay_adaptive_multiscale_phase import configure_frontend


def test_adaptive_coarse_carriers_share_declared_reference():
    row = {
        "sample_rate_hz": 2_500_000,
        "sources": [
            {
                "epoch": 100,
                "fractional_epoch": 0.25,
                "rx0_acquired_cfo_hz": 10.0,
                "rx1_applied_acquired_cfo_hz": 20.0,
            },
            {
                "epoch": 200,
                "fractional_epoch": -0.5,
                "rx0_acquired_cfo_hz": 30.0,
                "rx1_applied_acquired_cfo_hz": 40.0,
            },
        ],
    }
    configure_frontend(row)
    assert frontend.MODELS["A"][0][0] == frontend.MODELS["A"][1][0] == 100.25 / 2_500_000
    assert frontend.MODELS["B"][0][0] == frontend.MODELS["B"][1][0] == 199.5 / 2_500_000
