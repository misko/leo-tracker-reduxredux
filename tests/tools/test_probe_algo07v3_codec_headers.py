from dataclasses import dataclass

import numpy as np
import pytest
from probe_algo07v3_codec_headers import codec, profiled_pack, transform

from tests.localization_v3_fixture import evidence_fixture


@pytest.mark.parametrize('dtype', ['<f8', '>f8', '<i4', 'U3', 'S3', 'V8', 'datetime64[ns]',
                                  [('n', '<i4'), ('x', '<f8')]])
def test_complete_archive_bytes_match_for_shapes_layouts_and_dataclasses(dtype):
    _, pngs = evidence_fixture()
    array = np.zeros((4, 5), dtype=dtype)

    @dataclass
    class Value:
        values: object

    value = Value([array, array.copy(), np.asfortranarray(array), np.asfortranarray(array),
                   array[:, ::2], array[:, ::2], np.zeros((0, 2), dtype=dtype),
                   np.zeros((0, 2), dtype=dtype), np.array(0, dtype='>f8'),
                   np.array(-0., dtype='>f8'), np.float32(-0.)])
    actual, _, _ = transform()
    expected = codec.pack(value, pngs)
    assert actual(value, pngs) == expected
    profiled, measurement = profiled_pack(value, pngs)
    assert profiled == expected and measurement['counts']['numpy_save'] > 1


def test_array_data_is_never_cached_even_when_changed_during_traversal():
    _, pngs = evidence_fixture()

    class Changing(dict):
        def items(self):
            value = np.zeros(3)
            yield 'old', value
            value[:] = [-0., 2., 3.]
            yield 'new', value

    candidate, _, _ = transform()
    assert candidate(Changing(), pngs) == codec.pack(Changing(), pngs)


def test_nonzero_fortran_endian_and_special_float_bits_are_preserved():
    _, pngs = evidence_fixture()
    candidate, _, _ = transform()
    array = np.arange(24, dtype='>f8').reshape(4, 6)
    array[0, :3] = [-0., np.nan, np.inf]
    values = [array, array + 1, np.asfortranarray(array), np.asfortranarray(array + 2)]
    before = [v.tobytes(order='A') for v in values]
    assert candidate(values, pngs) == codec.pack(values, pngs)
    assert [v.tobytes(order='A') for v in values] == before


@pytest.mark.parametrize('dtype', ['f8', 'c16', np.longdouble])
def test_unaligned_contiguous_arrays_keep_their_original_bytes(dtype):
    _, pngs = evidence_fixture()
    candidate, _, _ = transform()
    backing = bytearray(np.dtype(dtype).itemsize * 12 + 1)
    value = np.ndarray((3, 4), dtype=dtype, buffer=backing, offset=1)
    value[:] = np.arange(12).reshape(3, 4)
    assert not value.flags.aligned and value.flags.c_contiguous
    assert candidate([value, value], pngs) == codec.pack([value, value], pngs)


def test_metadata_warnings_and_object_rejection_are_preserved():
    _, pngs = evidence_fixture()
    candidate, _, _ = transform()
    values = [np.zeros(2, dtype=np.dtype('f8', metadata={'units': 'Hz'})) for _ in range(2)]
    with pytest.warns(UserWarning) as before:
        expected = codec.pack(values, pngs)
    with pytest.warns(UserWarning) as after:
        actual = candidate(values, pngs)
    assert actual == expected and len(before) == len(after)
    for pack in (codec.pack, candidate):
        with pytest.raises(ValueError, match='Object arrays'):
            pack([np.arange(2), np.array([object()], dtype=object)], pngs)
