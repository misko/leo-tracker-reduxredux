from export_native_target_iq import measurement_point


def test_exporter_imports_without_research_tool_dependencies(tmp_path):
    import subprocess,sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    script="""import importlib.util,sys
sys.path.insert(0,sys.argv[1])
spec=importlib.util.spec_from_file_location('exporter',sys.argv[2])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
assert module.digest(b'test')=='sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08'
"""
    subprocess.run([sys.executable,'-I','-c',script,str(root/'src'),str(root/'tools/export_native_target_iq.py')],cwd=tmp_path,check=True,capture_output=True,text=True)


def test_plan_contains_native_frequency_not_alias_lifted_or_orbit_prediction():
    track=dict(observation_ids=['a'],key='track',times=[4.],values=[999999.],norad=123)
    probe=dict(visit_index=3,valid_start_counter=40,edge='lower')
    candidate=dict(fractional_tracking_cfo_hz=12.,integer_epoch_sample=5,fractional_epoch_offset_samples=.2,candidate_rank=0)
    p=measurement_point(track,probe,candidate,0,1)
    assert p['CFO_hz']==12 and p['epoch_sample']==5.2
    assert not {'norad','values','position','residual'} & p.keys()
    assert p['observation_id']=='a' and p['sample_start']==40
