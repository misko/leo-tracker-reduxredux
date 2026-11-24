import pytest

from reports.ALGO08.v3.original_prefix_scaling import guard, marginal, prefixes


def test_prefix_lengths_bind_the_same_consecutive_original_start(tmp_path):
    chunks = [dict(chunk_index=i, first_sequence=64*i, window_count=64, compressed_bytes=80_000_000 + i)
              for i in range(5)]
    results = prefixes({"manifest_digest": "sha256:signed"}, chunks, "original", tmp_path, "original-pin")
    assert results["1"]["inventory"]["prefix_members"] == results["4"]["inventory"]["prefix_members"][:1]
    assert results["1"]["bytes"] == 80_000_000 and results["4"]["bytes"] == 320_000_006
    assert results["1"]["digest"] != results["4"]["digest"]
    with pytest.raises(ValueError, match="consecutive"):
        prefixes({"manifest_digest": "sha256:signed"}, chunks[1:], "original", tmp_path, "original-pin")


def test_waveform_guard_rejects_following_absolute_and_relative_names(tmp_path):
    first = tmp_path / "iq-000000.ci16.zst"
    observe = guard([first])
    observe("open", (str(first), None))
    observe("open", (first.name, None))
    for name in (str(first.with_name("iq-000001.ci16.zst")), "iq-000001.ci16.zst",
                 "/srv/bulk/recording/iq-000000.ci16.zst"):
        with pytest.raises(PermissionError):
            observe("open", (name, None))


def test_two_point_rate_uses_incremental_bytes_and_prices_startup():
    measured = marginal(.5, 1.3, 80_000_000, 320_000_000)
    assert measured["intercept_s"] == pytest.approx(.233333333)
    assert measured["marginal_mb_s"] == pytest.approx(300.)
    assert measured["clears_allowance"]
    with pytest.raises(ValueError, match="positive"):
        marginal(.5, .4, 80_000_000, 320_000_000)
