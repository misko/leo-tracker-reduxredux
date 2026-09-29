import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('subsecond_evaluate',Path(__file__).with_name('evaluate.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def test_regions_clip_without_wrapping_or_duplicate_cells():
    assert module.region_epochs([0,1,9],10,2)==[0,1,2,3,7,8,9]
    assert module.region_epochs([],10,2)==[]

def test_radius_changes_search_geometry_not_window_inventory():
    assert module.region_epochs([5],12,1)==[4,5,6]
    assert module.region_epochs([5],12,2)==[3,4,5,6,7]
