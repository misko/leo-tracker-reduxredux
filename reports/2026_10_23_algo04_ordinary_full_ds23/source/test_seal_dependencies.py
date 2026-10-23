import pytest
import seal_dependencies as seal


def test_changed_dependency_is_detected(tmp_path):
    path = tmp_path/'dependency.py'
    path.write_text('original = True\n')
    files = {str(path): seal.digest(path)}
    seal.verify_files(files)
    path.write_text('original = False\n')
    with pytest.raises(ValueError, match='dependency bytes changed'):
        seal.verify_files(files)


def test_missing_dependency_is_detected(tmp_path):
    with pytest.raises(ValueError, match='dependency bytes changed'):
        seal.verify_files({str(tmp_path/'missing.py'): 'absent'})


def test_inventory_includes_lazy_audit_and_external_scipy():
    files = seal.dependencies()
    assert str(seal.SELF) in files
    assert str(seal.Path(seal.repair_algo04_empty_audit.__file__).resolve()) in files
    scipy_root = seal.Path('/tmp/algo03-feasible-deps/scipy').resolve()
    assert any(seal.Path(name).is_relative_to(scipy_root) for name in files)
    assert not any(name.endswith('/report_full.py') or name.endswith('/test_seal_dependencies.py') for name in files)
