import io
from pathlib import Path
import sys
import tarfile

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tools'))
from run_arm_cadence import allowed_products, save_products, device_is_busy


def archive(names):
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as tar:
        for name in names:
            entry=tarfile.TarInfo(name);entry.size=2;tar.addfile(entry,io.BytesIO(b'ok'))
    return stream.getvalue()


def test_only_owned_products_saved_once(tmp_path):
    data=archive(['scan-0/detector.stdout','scan-0/results/tracks.stdout'])
    assert len(save_products(data,tmp_path,allowed_products(3)))==2
    assert (tmp_path/'scan-0/detector.stdout').read_bytes()==b'ok'
    with pytest.raises(FileExistsError):save_products(data,tmp_path,allowed_products(3))


@pytest.mark.parametrize('name',['../escape','scan-4/detector.stdout','scan-0/chain.sh','/tmp/escape'])
def test_retrieval_rejects_unowned_paths_before_writing(tmp_path,name):
    data=archive(['scan-0/detector.stdout',name])
    with pytest.raises(ValueError):save_products(data,tmp_path,allowed_products(3))
    assert not list(tmp_path.iterdir())


def test_duplicate_archive_members_rejected(tmp_path):
    with pytest.raises(ValueError):save_products(archive(['scan-0/detector.stdout']*2),tmp_path,allowed_products(3))


def test_idle_between_jobs_does_not_mean_controller_finished():
    assert device_is_busy('100 root /mnt/glrtbench/another-run/controller /mnt/glrtbench/another-run/plan.tsv 300000 5000')
    assert device_is_busy('101 root /mnt/glrtbench/current/measure-run 420 /bin/example')
    assert not device_is_busy('102 root /usr/sbin/sshd\n103 root ps')
