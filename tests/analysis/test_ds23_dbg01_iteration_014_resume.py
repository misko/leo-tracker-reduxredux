import pytest
import resume_ds23_dbg01_iteration_014 as resume


def progress():
    return dict(all_terminal=False,stages=[dict(stage='inventory',scientific_passed=True)],running_stage='screen',cases=['DS23-0202','DS23-0262'])


def test_resume_requires_terminal_scientific_receipt(monkeypatch):
    monkeypatch.setattr(resume.study,'stage_passed',lambda *_:False)
    with pytest.raises(ValueError,match='scientific receipt'):resume.recovered_progress(progress())


def test_resume_preserves_finished_stages_without_fabricating_an_exit_code(monkeypatch):
    monkeypatch.setattr(resume.study,'stage_passed',lambda *_:True)
    p=progress();r=resume.recovered_progress(p)
    assert len(p['stages'])==1 and len(r['stages'])==2
    assert r['stages'][0]==p['stages'][0]
    assert r['stages'][1]['returncode'] is None
    assert r['running_stage'] is None
