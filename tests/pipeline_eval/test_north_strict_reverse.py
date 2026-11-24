import hashlib
import json

import pytest

from reports.ALGO08.v3.north_strict_reverse import sealed_conversion


def test_reverse_reuses_only_the_externally_verified_conversion(tmp_path):
    conversion = dict(independent_check=True, request={"map": str(tmp_path/"conversion/map.json"),
                                                       "codec": str(tmp_path/"packing.so")})
    raw = json.dumps(conversion).encode()
    item = tmp_path/"conversion.json"
    item.write_bytes(raw)
    bound = {"sources": {"conversion.json": hashlib.sha256(raw).hexdigest()}, "conversion": conversion}
    assert sealed_conversion(bound, tmp_path) == (raw, conversion)

    item.write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="Unreviewed"):
        sealed_conversion(bound, tmp_path)

    wrong = dict(conversion, independent_check=False)
    wrong_raw = json.dumps(wrong).encode()
    item.write_bytes(wrong_raw)
    bound = {"sources": {"conversion.json": hashlib.sha256(wrong_raw).hexdigest()}, "conversion": wrong}
    with pytest.raises(ValueError, match="independently verified"):
        sealed_conversion(bound, tmp_path)
