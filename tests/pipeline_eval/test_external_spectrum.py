import io
import zipfile
from datetime import UTC, datetime

import numpy as np
import pytest

from tools.pipeline_eval.qualification import external_spectrum_source as source
from tools.pipeline_eval.qualification import external_spectrum_trial as trial
from tools.pipeline_eval.variants import external_spectrum as scans
from tools.pipeline_eval.variants import external_spectrum_position as position


def test_ridge_uses_measured_frequency_changes_and_deduplicates_tones():
    seconds = 500 + np.arange(60)
    bins = 538 - 2 * np.arange(len(seconds))
    power = np.zeros((len(seconds), 1024))
    power[np.arange(len(seconds)), bins] = 2.4
    power[np.arange(len(seconds)), bins + 45] = 2.2
    power[:, 700] = 4.0
    (ridge,) = scans.extract_ridges(scans.Spectrum(seconds, power))
    np.testing.assert_array_equal(ridge.utc, seconds)
    assert ridge.frequency_hz[-1] - ridge.frequency_hz[0] == -118 * scans.BIN_HZ
    assert not scans.extract_ridges(scans.Spectrum(seconds, np.flip(power, axis=0)))


def test_spectrum_checks_if_band_and_excludes_repeated_edge(tmp_path):
    filename = tmp_path / "input.csv"
    utc = int(datetime(2023, 3, 2, 6, tzinfo=UTC).timestamp())
    fields = ",".join(scans.OFF_BAND_FIELDS)
    power = ",".join(["-12.00"] * 1025)
    filename.write_text(f"2023-03-02, 06:00:00,{fields},974,{power}\n")
    with pytest.raises(ValueError, match="IF grid"):
        scans.read_spectrum(filename, utc, 1)
    result = scans.read_spectrum(filename, utc, 1, scans.OFF_BAND_FIELDS)
    np.testing.assert_array_equal(result.utc, [utc])
    assert result.excess_db.shape == (1, 1024)


def test_later_residual_reuses_offset_from_early_samples():
    expected = np.arange(position.SAMPLES) * 2000
    received = expected + 95000
    received[position.FIT :] += 3600
    early, late = position.change_cost(received, expected)
    assert early == 0
    assert late == 3600**2


def test_same_three_decoys_and_equal_budget_for_both_offers():
    sites = trial.grid()
    pairs = trial.offer_pairs()
    for anchor, offers in pairs.items():
        assert len(set(offers["present"]) & set(offers["omitted"])) == 3
        assert anchor in offers["present"] and anchor not in offers["omitted"]
        assert len(offers["present"]) == len(offers["omitted"]) == 4
        point = tuple(sites.coordinates[anchor])
        others = set(offers["present"] + offers["omitted"]) - {anchor}
        assert min(trial.distance_km(point, tuple(sites.coordinates[i])) for i in others) > 80


def test_zip_directory_maps_only_member_offsets_required_for_range_download():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("230314/starlink.tle", "a" * 1024)
        archive.writestr("230314/06/transits.csv", "transits")
        archive.writestr("230314/06/Kerberos_230314_0600.csv", "scan")
    data = stream.getvalue()
    rows = list(source.archive_entries(data, 0, len(data)))
    assert [entry[0] for entry in rows] == [
        "230314/starlink.tle",
        "230314/06/transits.csv",
        "230314/06/Kerberos_230314_0600.csv",
    ]
    assert all(data[entry[-1] : entry[-1] + 4] == b"PK\x03\x04" for entry in rows)
