import importlib.util
from pathlib import Path
P=Path(__file__).with_name("run.py"); S=importlib.util.spec_from_file_location("local_grid_test",P); R=importlib.util.module_from_spec(S); S.loader.exec_module(R)
def row(pid,east,train,held): return {"point_id":pid,"east_km":east,"north_km":0,"methods":{"baseline":{"training_capped_loss":train,"held_capped_loss":held}}}
def test_held_perturbation_cannot_change_refinement_selection():
 rows=[row("a",0,.2,.9),row("b",1,.3,.1)]; assert R.best_one(rows,"baseline")["point_id"]=="a"
 rows[0]["methods"]["baseline"]["held_capped_loss"]=1e9; rows[1]["methods"]["baseline"]["held_capped_loss"]=-1e9
 assert R.best_one(rows,"baseline")["point_id"]=="a"
def test_frozen_regions_and_methods():
 assert set(R.CENTERS)=={"cell_3","cell_5"}; assert R.WIDTHS==(10.,20.,25.,30.,40.,50.)
