import probe_ds23_iteration013_extra_curve as study


def test_extra_curve_keeps_original_nomination_and_new_evidence_separate():
    module=study.configure()
    assert module.repair.runner is study.runner
    assert module.repair.OUT==study.runner.RAW/'single_curve_reentry'
    assert module.OUT==study.runner.RAW/'point_rich_extra_curve'
    rows=[dict(component='old',curved=True,points=80,original_points=80,span_s=60),
          dict(component='partial',curved=True,points=70,original_points=90,span_s=50),
          dict(component='dense',curved=True,points=50,original_points=50,span_s=40),
          dict(component='shorter',curved=True,points=20,original_points=20,span_s=30)]
    assert [r['component'] for r in module.choose_extra(dict(ranking=rows),{'old'})]==['dense']
