from infrastructure_v2 import job_env,REPO

def test_frozen_repo_precedes_collection_snapshot(tmp_path):
    paths=job_env(tmp_path)['PYTHONPATH'].split(':')
    assert paths.index(str(REPO/'src'))<paths.index('/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src')
    assert paths[-2:]==['/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src','/tmp/algo03-feasible-deps']
