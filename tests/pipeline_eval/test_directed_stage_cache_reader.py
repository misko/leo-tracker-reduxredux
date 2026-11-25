import ctypes
import errno
import json
import os

import numpy as np
import pytest

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.fast_scan import FastSegmentSource
from leo.storage.short_window import ShortWindowWriter
from reports.ALGO08.v3 import directed_0208_reuse as case
from reports.ALGO08.v3 import directed_stage_cache_reader as check


@pytest.fixture
def capture(tmp_path):
    targets = [dict(target_id="pilot",edge="lower",channel=1,rf_center_hz=11_000_000_000,
                    lnb_lo_hz=9_750_000_000)]
    writer = ShortWindowWriter(tmp_path,"signed",configuration=dict(window_ms=20,sample_rate_hz=10_000_000,targets=targets),
                               radio={},receiver_ids=(0,1),chunk_windows=2,schema_version=2)
    for i in range(6):
        data = np.full((16,2,2),17*i,dtype="<i2")
        writer.append(sequence=i,target_id="pilot",samples=data,acquisition={"chronology":i},powers=({},{}))
    return writer.finish(stop_reason="max_visits")


def extents(directory):
    metadata = json.loads((directory/"manifest.json").read_bytes())
    names = {"manifest.json":"manifest"}
    for chunk in metadata["chunks"]:
        names[chunk["index_relative_path"]] = "index"
        names[chunk["payload_relative_path"]] = "payload"
    values = {name:(directory/name).read_bytes() for name in names}
    return {name:check.Extent(len(value),sha256_digest(value),names[name]) for name,value in values.items()}


def mock_cached(monkeypatch):
    reads = []
    def preadv(fd,view,offset):
        body = os.pread(fd,len(view),offset)
        view[:len(body)] = body
        reads.append((offset,len(body)))
        return len(body)
    monkeypatch.setattr(check,"preadv_nowait",preadv)
    monkeypatch.setattr(check,"thread_io",lambda:(0,0))
    return reads


def checked(path, ledger):
    entry = dict(path=path,manifest_digest=ledger["manifest.json"].sha256)
    return list(FastSegmentSource(entry,stop_sequence=6).windows())


def test_nowait_port_matches_every_released_row_without_copy_or_second_payload(capture,monkeypatch):
    ledger = extents(capture)
    expected = checked(capture,ledger)
    calls = mock_cached(monkeypatch)
    reader = check.CacheReader(capture,ledger)
    with check.signed_windows(reader):
        hashes = check.ordered_hashes(capture,ledger["manifest.json"].sha256,members=3,windows_per_member=2)
        actual = checked(capture,ledger)
        reader.verify_complete()
        assert reader.receipt()["metadata_reuses"] == 4  # manifest and three indexes
        assert len(calls) == len(ledger)
        assert reader.receipt()["bytes"] == sum(extent.size for extent in ledger.values())
        assert reader.receipt()["persistent_copy_bytes"] == 0
    assert [row.iq_sha256 for row in actual] == hashes
    for x,y in zip(expected,actual,strict=True):
        assert x.sequence == y.sequence and x.iq_sha256 == y.iq_sha256 and x.acquisition == y.acquisition
        np.testing.assert_array_equal(x.samples,y.samples)


@pytest.mark.parametrize("damage",("encoded","index","window","whole"))
def test_signed_encoded_index_and_released_decoded_checks_remain_independent(capture,monkeypatch,damage):
    ledger = extents(capture)
    metadata_path = capture/"manifest.json"
    metadata = json.loads(metadata_path.read_bytes())
    chunk = metadata["chunks"][1]
    if damage == "encoded":
        path = capture/chunk["payload_relative_path"]
        data = path.read_bytes()
        path.write_bytes(bytes([data[0]^1])+data[1:])
    elif damage in ("index","window"):
        path = capture/chunk["index_relative_path"]
        values = [json.loads(line) for line in path.read_bytes().splitlines()]
        values[0]["iq_sha256"] = "sha256:"+"0"*64
        payload = b"".join(canonical_json_bytes(row)+b"\n" for row in values)
        path.write_bytes(payload)
        if damage == "window":
            chunk["index_bytes"],chunk["index_sha256"] = len(payload),sha256_digest(payload)
            metadata_path.write_bytes(canonical_json_bytes(metadata))
            ledger = extents(capture)
    else:
        chunk["uncompressed_sha256"] = "sha256:"+"0"*64
        metadata_path.write_bytes(canonical_json_bytes(metadata))
        ledger = extents(capture)
    mock_cached(monkeypatch)
    kind = check.CacheSourceUnavailable if damage in {"encoded","index"} else BundleCorruptionError
    with check.signed_windows(check.CacheReader(capture,ledger)):
        with pytest.raises(kind):
            checked(capture,ledger)


@pytest.mark.parametrize("fault",(errno.EAGAIN,errno.EOPNOTSUPP,"short","physical"))
def test_faults_abort_once_without_blocking_fallback(capture,monkeypatch,fault):
    ledger = extents(capture)
    calls = []
    def preadv(fd,view,offset):
        calls.append(offset)
        if isinstance(fault,int):
            raise OSError(fault,"fixture denial")
        return len(view) - int(fault=="short")
    counters = iter(((0,0),(int(fault=="physical"),512*int(fault=="physical"))))
    monkeypatch.setattr(check,"preadv_nowait",preadv)
    monkeypatch.setattr(check,"thread_io",lambda:next(counters))
    with check.CacheReader(capture,ledger) as reader:
        with pytest.raises(check.CacheSourceUnavailable):
            reader.read(capture/"manifest.json",16<<20)
        assert calls == [0]
        assert not reader.read_files


def test_path_and_metadata_reuse_fail_closed(capture,monkeypatch):
    ledger = extents(capture)
    mock_cached(monkeypatch)
    with check.CacheReader(capture,ledger) as reader:
        with pytest.raises(check.CacheSourceUnavailable,match="escaped"):
            reader.read(capture.parent/"manifest.json",16<<20)
        metadata = capture/"manifest.json"
        reader.read(metadata,16<<20)
        metadata.write_bytes(metadata.read_bytes()+b" ")
        with pytest.raises(check.CacheSourceUnavailable,match="metadata changed"):
            reader.read(metadata,16<<20)
    name = next(name for name,extent in ledger.items() if extent.kind=="payload")
    alias = capture.parent/"copy"
    os.link(capture/name,alias)
    with pytest.raises(check.CacheSourceUnavailable,match="regular-file"):
        with check.CacheReader(capture,ledger):
            pytest.fail("The hard-linked member passed preflight")


def test_partial_scope_cannot_seal_as_a_completed_replay(capture,monkeypatch):
    ledger = extents(capture)
    mock_cached(monkeypatch)
    with check.signed_windows(check.CacheReader(capture,ledger)) as reader:
        check.ordered_hashes(capture,ledger["manifest.json"].sha256,members=3,windows_per_member=2)
        with pytest.raises(check.CacheSourceUnavailable,match="incomplete"):
            reader.verify_complete()


@pytest.mark.parametrize("present",(0,1))
def test_cold_or_mixed_later_extent_refuses_before_any_data_syscall(capture,monkeypatch,present):
    ledger = extents(capture)
    calls = iter([(2,2),(present,2)])
    reads = mock_cached(monkeypatch)
    monkeypatch.setattr(check,"resident_pages",lambda *a:next(calls))
    reader = check.CacheReader(capture,ledger)
    with pytest.raises(check.CacheSourceUnavailable,match="before any data read"):
        with reader:
            pytest.fail("A later unavailable extent must prevent the first data read")
    assert not reads and reader.dir_fd is None
    assert reader.receipt()["refused_read"]["attempted"] is False


def test_eviction_after_initial_census_refuses_before_progressing_to_syscall(capture,monkeypatch):
    ledger = extents(capture)
    reads = mock_cached(monkeypatch)
    calls = iter([(2,2)]*len(ledger)+[(0,1)])
    monkeypatch.setattr(check,"resident_pages",lambda *a:next(calls))
    with check.CacheReader(capture,ledger) as reader:
        with pytest.raises(check.CacheSourceUnavailable,match="before data call"):
            reader.read(capture/"manifest.json",16<<20)
        assert reader.receipt()["refused_read"]["condition"] == "pre_call_cache_census"
    assert not reads


def test_eagain_with_readahead_preserves_all_observed_charge_and_never_retries(capture,monkeypatch):
    ledger = extents(capture)
    calls = []
    def preadv(fd,iovec,count,offset,flags):
        calls.append(flags)
        assert count == 1 and offset == 0 and ctypes.cast(iovec,ctypes.POINTER(check.IOVec))[0].size > 0
        ctypes.set_errno(errno.EAGAIN)
        return -1
    io = iter(((11,5632),(267,136704)))
    monkeypatch.setattr(check,"PREADV2",preadv)
    monkeypatch.setattr(check,"thread_io",lambda:next(io))
    with check.CacheReader(capture,ledger) as reader:
        with pytest.raises(check.CacheSourceUnavailable,match="Detached read refused"):
            reader.read(capture/"manifest.json",16<<20)
    outcome = reader.receipt()
    assert calls == [check.RWF_NOWAIT]
    assert outcome["returned_bytes"] == 0
    assert outcome["read_input_blocks"] == 256
    assert outcome["charged_read_bytes"] == 131072
    assert outcome["refused_read"]["condition"] == "incidental_read_charge"
    assert outcome["refused_read"]["syscall_errno"] == errno.EAGAIN


def test_score_refuses_real_read_charge_even_with_external_clean_marker(tmp_path,monkeypatch):
    wave = dict(admitted=True,no_observed_source_read_charge=True,verified_prefix_bytes=0,
                cache=dict(read_input_blocks=256,charged_read_bytes=131072,refused_read=None))
    monkeypatch.setattr(case.book,"load",lambda *_:wave)
    with pytest.raises(ValueError,match="no observed source read charge"):
        case.score(tmp_path,{},"capture","plan","waveform")


def test_requires_sealed_completed_original_custody_before_opening_a_prefix(tmp_path,monkeypatch):
    official, stage = tmp_path/"official",tmp_path/"stage"
    folder = official/"cases"/case.CASE
    folder.mkdir(parents=True)
    stage.mkdir()
    monkeypatch.setattr(case,"CAMPAIGN",official)
    monkeypatch.setattr(case,"STAGE",stage)
    authority = dict(recording="/frozen/lower",region_sha256="offer")
    def write(path,document):
        data = canonical_json_bytes(document)
        path.write_bytes(data)
        return sha256_digest(data)[7:]
    auth = write(folder/"authority.json",authority)
    pair = write(folder/"pair.json",dict(authority_sha256=auth,verified_pair=True,state="observed_pair",generation=1,
                                       attempt_result_sha256={"installed":"one","successor":"two"}))
    book = dict(case=case.CASE,rank=96,bytes=10,files=[dict(target="one")],expected=authority,offer_sha256="offer")
    capture = dict(case=case.CASE,state="complete",origin="strict_RWF_NOWAIT",pair_sha256=pair,authority=authority,
                   zero_input_blocks_per_admitted_source_read=True,copied_bytes=10,completed=["one"])
    pin = write(stage/"cache-capture-result.json",capture)
    assert case.authority(book,pin)[3] == authority
    pin = write(stage/"cache-capture-result.json",dict(capture,completed=[]))
    with pytest.raises(ValueError,match="complete independently captured stage"):
        case.authority(book,pin)
