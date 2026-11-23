from pathlib import Path
import runpy


MODULE = runpy.run_path(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/cumulative_medium.py"))


def pressure(full):
    return f"some avg10=70.0 avg60=70.0 avg300=70.0 total=100\nfull avg10={full} avg60=6.0 avg300=2.0 total=90\n"


def test_raw_admission_requires_every_member_page_and_low_service_stalls():
    gate = MODULE["admitted"]
    cache = dict(unavailable={}, members=43, observed_members=43, cached_pages=817_049, observed_file_pages=817_049)
    assert gate(cache, (pressure(8.0), pressure(10.0)))
    assert not gate(cache, (pressure(10.01), pressure(8.0)))
    assert not gate(dict(cache, cached_pages=817_048), (pressure(8.0), pressure(8.0)))
    assert not gate(dict(cache, unavailable={"member": "missing"}), (pressure(8.0), pressure(8.0)))


def test_artist_qualification_rejects_changed_science_and_new_overlap():
    check = MODULE["verify_artist_safety"]
    original = [({"curve": [1.0, 2.0]}, [])]
    assert check(original, original)
    assert not check([({"curve": [1.0, 9.0]}, [])], original)
    assert not check([({"curve": [1.0, 2.0]}, [("new overlap", (0, 0, 1, 1))])], original)
