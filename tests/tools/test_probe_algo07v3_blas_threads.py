"""Fail closed on incomplete or unexpected loaded BLAS thread configuration."""

from types import SimpleNamespace

import pytest
from probe_algo07v3_blas_threads import configure_backend, library_info


class Function:
    def __init__(self,value):
        self.value=value

    def __call__(self):
        return self.value


class Setter:
    def __init__(self,getter):
        self.getter=getter

    def __call__(self,value):
        self.getter.value=value


def libraries(tmp_path,threads):
    paths,handles=[],{}
    for owner,suffix in [('numpy','64_'),('scipy','')]:
        path=tmp_path/f'{owner}.libs/openblas.so'
        path.parent.mkdir()
        path.write_bytes(owner.encode())
        paths.append(str(path))
        handles[str(path)]=SimpleNamespace(**{
            'scipy_openblas_get_num_threads'+suffix:Function(threads),
            'scipy_openblas_get_config'+suffix:Function(b'OpenBLAS test')})
        setattr(handles[str(path)],'scipy_openblas_set_num_threads'+suffix,
                Setter(getattr(handles[str(path)],'scipy_openblas_get_num_threads'+suffix)))
    return paths,handles


@pytest.mark.parametrize('threads',[1,2,3])
def test_reads_both_actual_c_apis(tmp_path,threads):
    paths,handles=libraries(tmp_path,threads)
    actual=library_info(paths,handles.__getitem__)
    assert [r['owner'] for r in actual]==['numpy','scipy']
    assert all(r['threads']==threads and len(r['sha256'])==64 for r in actual)


def test_missing_backend_rejected(tmp_path):
    paths,handles=libraries(tmp_path,1)
    with pytest.raises(ValueError,match='exactly one'):
        library_info(paths[:1],handles.__getitem__)


def test_unknown_backend_rejected():
    with pytest.raises(ValueError,match='Unexpected loaded'):
        library_info(['/unknown/openblas.so'])


@pytest.mark.parametrize('backend',['numpy','scipy','both'])
def test_backend_configuration_is_verified_independently(tmp_path,backend):
    paths,handles=libraries(tmp_path,1)
    configure_backend(library_info(paths,handles.__getitem__),3,backend,handles.__getitem__)
    actual=library_info(paths,handles.__getitem__)
    assert all(row['threads']==(3 if backend in ('both',row['owner']) else 1) for row in actual)
