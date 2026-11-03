from types import SimpleNamespace

from ds23_all_family_uncertainty import include_unreplicated, replication_gate_view


def test_unreplicated_families_receive_same_physical_prior_and_bank_order():
    calls=[]
    def builder(scan,labels,supported,kind):
        calls.append((scan,list(labels),list(supported),kind))
        return "bank","metadata"
    p=SimpleNamespace(scan="scan",labels=[7,2,9],supported=[2],supported_local=[1])
    include_unreplicated(p,builder)
    assert p.supported==[7,2,9]
    assert p.supported_local==[0,1,2]
    assert p.new_uncertain_families==[7,9]
    assert p.replication_required_families==[2]
    assert calls==[("scan",[7,2,9],[7,2,9],"physical")]
    assert p.mode_bank=="bank" and p.mode_metadata=="metadata"


def test_replication_gate_view_does_not_remove_geometry_uncertainty_modes():
    class Model:
        def __init__(self):
            self.supported=[7,2,9]
            self.replication_required_families=[2]
        def calculate(self,x):
            return len(self.supported)
        state=calculate
        conditional_frequency=calculate
    p=Model()
    view=replication_gate_view(p)
    assert view.supported==[2]
    assert view.calculate([0,0])==3
    assert view.state([0,0])==3 and view.conditional_frequency([0,0])==3
    assert p.supported==[7,2,9]
