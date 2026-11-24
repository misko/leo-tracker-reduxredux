import subprocess

import numpy as np
import pytest

from reports.ALGO08.v3.iq_block_float import COMPILE, SOURCE, Codec
from reports.ALGO08.v3.iq_block_float_trial import comparison, delta


@pytest.fixture(scope="module")
def codec(tmp_path_factory):
    binary = tmp_path_factory.mktemp("bf-iq") / "codec.so"
    subprocess.run([*COMPILE, str(SOURCE), "-o", str(binary)], check=True)
    return Codec(binary)


@pytest.mark.parametrize("width", (8, 10))
def test_all_signed_ci16_words_match_scalar_rule(codec, width):
    raw = np.arange(-32768, 32768, dtype=np.int32).astype("<i2").reshape(-1, 2, 2)
    packet, clips = codec.encode(raw, width)
    out = np.empty_like(raw)
    codec.decode(packet, width, out)
    shift = 16 - width
    rail = 1 << (width - 1)
    widened = raw.astype(np.int32)
    q = np.sign(widened) * ((np.abs(widened) + (1 << (shift - 1))) >> shift)
    assert clips == np.count_nonzero(q >= rail)
    assert packet.size == 1 + raw.size * width // 8 and packet[0] == shift
    np.testing.assert_array_equal(out, q.clip(-rail, rail - 1) << shift)


@pytest.mark.parametrize("width", (8, 10))
def test_small_data_and_malformed_derivative(codec, width):
    raw = np.array([[[0, 7], [-3, -8]], [[2, -6], [3, -4]]], dtype="<i2")
    encoded, clip = codec.encode(raw, width)
    restored = np.empty_like(raw)
    codec.decode(encoded, width, restored)
    np.testing.assert_array_equal(raw, restored)
    assert encoded[0] == clip == 0
    with pytest.raises(ValueError, match="extent"):
        codec.decode(encoded[:-1], width, restored)
    encoded[0] = 31
    with pytest.raises(ValueError, match="header"):
        codec.decode(encoded, width, restored)


def test_pilot_period_and_signed_cfo_are_preserved_in_branch_comparison():
    old, new = (0, 13332, .5, -25., .7, .1), (0, 0, .5, -35., .8, .1)
    change = delta(old, new)
    assert (change["matched"], change["epoch_samples"], change["cfo_hz"]) == (True, 1., -10.)
    first = dict(visit=1, rx=0, mode="full", factors=[old], selected_rank=0,
                 short_continuation=False, kept=0, votes=[4])
    second = dict(first, factors=[new, (1, 200, 0., 20., .2, .1)], votes=[3])
    result = comparison({"lanes": [first]}, {"lanes": [second]})
    assert result["changes"]["native_rank_set_changed"] == 1
    assert result["changes"]["selected_rank_changed"] == 0
    assert result["selected_frequency"]["mean"] == -10.
