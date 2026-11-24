import pytest

from reports.ALGO08.v3.ds30_0359_agg_reuse import budget


def test_cost_ceiling_keeps_required_compression_and_includes_setup():
    def clock(value):
        return {"cpu_s": value, "elapsed_s": value}

    spans = {stage: list(map(clock, values)) for stage, values in {
        "whole_orbit": [1.2], "make_figure": [.25, .25], "base_draw": [.15, .15],
        "copy": [.005, .005], "restore": [.004, .006, .004, .006],
        "encode": [.07, .07, .07, .07], "tight_layout": [.06, .06], "subplots": [.01, .01],
    }.items()}
    encodes = [dict(header_cpu_s=.001, filter_cpu_s=.005, compress_cpu_s=.061, write_cpu_s=.002,
                    encode_cpu_s=.069) for _ in range(4)]
    result = budget(spans, encodes, clock(1.25), "cpu_s")
    assert result["complete"] == 1.25
    assert result["first_restores"] == .008
    assert result["optimistic_shared_layout_and_buffers"] == pytest.approx(.17)
    assert result["optimistic_second_band_layout_and_buffers"] == pytest.approx(.1)
    assert result["encoder_cpu_except_deflate"] == pytest.approx(.036)
    spans["restore"] = [clock(.006), clock(.006)]
    assert budget(spans, encodes, clock(1.25), "cpu_s")["first_restores"] == 0.0
