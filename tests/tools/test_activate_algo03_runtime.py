from activate_algo03_runtime import activity


def test_job_owner_blocks_activation_even_before_numerical_child_launch(tmp_path):
    root = tmp_path/'42'
    (root/'task/42').mkdir(parents=True)
    (root/'task/42/children').write_text('')
    (root/'fd').mkdir()
    (root/'fd/3').symlink_to('/observed/jobs/watcher/owner.lock')
    assert activity(42, tmp_path)['idle']
    (root/'fd/4').symlink_to('/observed/jobs/a-real-job/owner.lock')
    assert not activity(42, tmp_path)['idle']
    (root/'fd/4').unlink()
    (root/'task/43').mkdir()
    (root/'task/43/children').write_text('100')
    assert activity(42, tmp_path)['children'] == [100]
    assert not activity(42, tmp_path)['idle']


def test_watcher_ownership_must_be_observed(tmp_path):
    (tmp_path/'42/task/42').mkdir(parents=True)
    (tmp_path/'42/task/42/children').write_text('')
    (tmp_path/'42/fd').mkdir()
    assert not activity(42, tmp_path)['idle']
