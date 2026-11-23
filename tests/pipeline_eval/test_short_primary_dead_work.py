from math import ceil, floor

from reports.ALGO08.v3 import short_primary_dead_work as trial


def test_retained_original_fir_tiles_enclose_every_frame_plane_and_halo():
    width_max = ceil(2_500_000/750) + 128*44//4 - 1
    frame_starts = [j + 88//4 for frame in range(8)
                    for j in (floor(frame*10_000/3), ceil(frame*10_000/3))]
    assert trial.FIRST == min(frame_starts)
    assert max(frame_starts) + width_max <= trial.LAST
    assert (trial.FIRST-10) % 4 == (trial.LAST-10) % 4 == 0
    assert (trial.LAST-1)*4 + 40 < 120_000


def test_short_load_covers_the_extreme_fractional_tap_and_vector_halo():
    last_frame = (7*40_000 + 1)//3 + 13_332
    last_pilot = last_frame + (2 + 64)*44 - 1
    max_fractional_tap = floor(last_pilot + 1.5) + 8
    assert max_fractional_tap == 109_577
    assert max_fractional_tap + 16 < trial.LOAD_LIMIT < 120_000


def test_both_transformations_preserve_the_legacy_public_load():
    original = ("int portable_verifier_load(PortableVerifier *w) {\n"
                "for (int sample = 0; sample < loaded_samples; ++sample) {}\n"
                "return 0;\n}\nstatic unsigned bounded_grid() {}\n")
    scoped = trial.verifier_source(original)
    assert scoped.startswith(original)
    assert "sample < 109600;" in scoped[len(original):]

    original = ("int two_scan() { return portable_verifier_load(w, input, lane); }\n"
                "int cancellation_primary_factors() { return portable_verifier_load(w, input, lane); }\n")
    scoped = trial.wrapper_source(original)
    assert "int two_scan() { return portable_verifier_load(w, input, lane); }" in scoped
    assert "cancellation_primary_factors() { return portable_verifier_load_scout_fractional(w, input, lane); }" in scoped
