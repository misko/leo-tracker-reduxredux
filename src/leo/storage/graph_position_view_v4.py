"""ALGO05 presentation through versioned public readers, with ALGO04 fallback."""
from leo.contracts.fast_graph_position_v4 import MODEL_VERSION
from leo.contracts.fast_graph_position_v3 import MODEL_VERSION as PREVIOUS
from leo.storage.graph_position_view import GraphPositionView
from leo.storage.fast_graph_position_v4 import FastGraphPositionStoreV4

class GraphPositionViewV4:
    def __init__(self,root,model_version,*,previous=None,recovery=None):
        if model_version!=MODEL_VERSION:raise ValueError('Explicit ALGO05 model required')
        self.previous=previous if previous is not None else GraphPositionView(root,PREVIOUS)
        self.recovery=recovery if recovery is not None else FastGraphPositionStoreV4(root)

    def detail(self,run_id):
        view=self.previous.detail(run_id)
        view.update(selected_model=MODEL_VERSION,fallback=True,reason='Awaiting qualified ALGO05 result; '+(view.get('reason') or 'ALGO04 retained'))
        try:
            job=next((j for j in self.recovery.inputs(minimum_completed_utc_ns=1) if j['run_id']==run_id),None)
            if job is None:return view
            status=self.recovery.status(job['job_id'])
            if not status or status['state']!='complete':return view
            terminal,_=self.recovery.terminal(job)
            if terminal['decision']=='ALGO05_additive':
                view.update(state='complete',position=terminal['position'],decision=terminal['decision'],fallback=False,
                    selected=dict(model_version=MODEL_VERSION,state='complete',position=terminal['position'],
                        arms={a:dict(endpoint_latlon=r['endpoint_latlon']) for a,r in terminal['candidate']['trial']['arms'].items()}))
            view.update(reason=terminal.get('failure'),incumbent_seconds=terminal['incumbent_seconds'],
                recovery_seconds=terminal['recovery_seconds'],total_seconds=terminal['total_seconds'])
        except (OSError,ValueError,KeyError) as error:view['reason']='ALGO05 unavailable: '+type(error).__name__
        return view

def graph_position_view(root,model_version):
    return GraphPositionViewV4(root,model_version) if model_version==MODEL_VERSION else GraphPositionView(root,model_version)
