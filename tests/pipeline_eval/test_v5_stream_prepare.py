import hashlib
import json

import pytest

from tools.pipeline_eval.variants import v5_stream_prepare as prep


def candidate(rank):
    return dict(
        candidate_rank=rank,
        fractional_epoch_offset_samples=-0.125,
        fractional_margin=0.0,
        fractional_tracking_cfo_hz=-123_456.75,
        integer_epoch_sample=930,
        passed_fractional_margin_gate=False,
        fractional_control_score=0.035,
        fractional_exact_score=0.035,
    )


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_only_native_candidates_are_narrowed_and_every_row_is_kept(tmp_path, encoding):
    metadata_row = candidate(12)
    values = [candidate(8), candidate(10), dict(candidate(13), future_field="unknown")]
    document = {
        "provenance": {"name": "récepteur", "probes": [dict(candidates=[metadata_row])]},
        "source": {"session_id": "a", "probes": [dict(candidates=values), dict(candidates=[])]},
        "other": r'"probes"',
    }
    raw = json.dumps(document, ensure_ascii=False, indent=2).encode(encoding)
    path = tmp_path / "native.json"
    path.write_bytes(raw)
    record = dict(path=str(path), sha256="sha256:" + hashlib.sha256(raw).hexdigest())
    decoded = prep.read_native(record)
    assert decoded["provenance"] == document["provenance"]
    assert decoded["other"] == document["other"]
    actual = decoded["source"]["probes"][0]["candidates"]
    assert len(actual) == len(values) and actual[2] == values[2]
    assert decoded["source"]["probes"][1]["candidates"] == []
    for got, wanted in zip(actual[:2], values[:2], strict=True):
        assert type(got) is prep.TrackCandidate
        assert {key: got[key] for key in got._fields} == {key: wanted[key] for key in got._fields}


@pytest.mark.parametrize(
    "text",
    ['{"source":{"probes":[{},]}}', '{"source":{},}', '{"source" {}}', '{"source":{}} []'],
)
def test_bad_json_fails_closed(text):
    with pytest.raises(json.JSONDecodeError):
        prep.decode_native(text)


def test_bound_native_digest_is_verified_before_decoding(tmp_path):
    path = tmp_path / "native.json"
    path.write_text("not json")
    with pytest.raises(ValueError, match="Native job input changed"):
        prep.read_native({"path": str(path), "sha256": "sha256:wrong"})


def test_duplicate_members_use_the_last_value_and_escaped_keys_follow_the_native_path():
    text = r'{"source":{"probes":[{}]},"\u0073ource":{"probes":[[]],"x":1,"x":2}}'
    assert prep.decode_native(text) == json.loads(text)


def test_native_document_is_released_only_after_the_original_preparation_returns():
    def read(source, config):
        assert config == 42 and source["value"] == 19
        return {"measurement": source["value"]}

    owned = prep.PrivateNativeDocument(value=19)
    ordinary = {"value": 19}
    assert prep.prepare_owned(read, owned, 42) == {"measurement": 19}
    assert prep.prepare_owned(read, ordinary, 42) == {"measurement": 19}
    assert owned == {} and ordinary == {"value": 19}
