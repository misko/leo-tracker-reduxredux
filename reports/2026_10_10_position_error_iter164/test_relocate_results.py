"""Temporary-file audit tests; no actual research output is touched."""
import shutil
import pytest
from relocate_results import inventory


def test_copy_preserves_tree_and_same_size_corruption_is_detected(tmp_path):
    source=tmp_path/'source';source.mkdir()
    (source/'empty').mkdir();(source/'receipt.json').write_text('1234')
    expected=inventory(source)
    copy=tmp_path/'copy';shutil.copytree(source,copy)
    assert inventory(copy)==expected
    (copy/'receipt.json').write_text('4321')
    assert inventory(copy)!=expected


def test_empty_directory_is_part_of_identity(tmp_path):
    (tmp_path/'empty').mkdir();before=inventory(tmp_path)
    (tmp_path/'empty').rmdir()
    assert inventory(tmp_path)!=before


def test_symlink_and_unfinished_write_fail_closed(tmp_path):
    (tmp_path/'link').symlink_to(tmp_path/'missing')
    with pytest.raises(ValueError):inventory(tmp_path)
    (tmp_path/'link').unlink();(tmp_path/'.unfinished').write_text('partial')
    with pytest.raises(ValueError):inventory(tmp_path)
