"""Serve completed ALGO06 proofs without enumerating historical RF inputs."""
import logging
from leo.contracts.fast_graph_position_v5 import MODEL_VERSION
from leo.storage.fast_graph_position_v5 import FastGraphPositionStoreV5
from leo.storage.fast_scan import safe_id
from leo.storage.graph_position_view import summary
from leo.storage.graph_position_view_v5 import GraphPositionViewV5, graph_position_view as previous_view

LOGGER=logging.getLogger(__name__)

class FastGraphPositionLookupV5(FastGraphPositionStoreV5):
    def completed_run(self, run_id):
        """Public lookup over this component's own completed jobs, with full validation."""
        safe_id(run_id)
        for path in sorted((self.namespace/'jobs').glob('*/status.json')):
            try:
                job=self.status(path.parent.name)
                if job is None or job.get('run_id')!=run_id or job.get('state')!='complete':
                    continue
                if job.get('job_id')!=path.parent.name or job.get('model_version')!=MODEL_VERSION:
                    raise ValueError('Stored ALGO06 identity differs from lookup')
                terminal,_=self.terminal(job)
                if terminal['state']=='complete':
                    return terminal
            except (OSError,ValueError,KeyError,TypeError) as error:
                LOGGER.warning('Rejected ALGO06 lookup %s: %s',path.parent.name,type(error).__name__)
        return None

def additive_summary(terminal):
    return dict(model_version=terminal['model_version'],state='complete',position=terminal['position'],
                arms={a:dict(endpoint_latlon=r['endpoint_latlon']) for a,r in terminal['candidate']['trial']['arms'].items()})

def completed_view(run_id, terminal):
    """Project only public, validated terminal contracts into the existing API shape."""
    v4=terminal['incumbent'];v3=v4['incumbent'];v2=v3['incumbent'];v1=v2['baseline']
    if v3['decision']=='ALGO04_additive':
        selected=summary(v3);decision=v3['decision']
    else:
        selected=summary(v1 if v2['decision']=='ALGO02_fallback' else v2)
        decision='ALGO02_fallback' if v2['decision']=='ALGO02_fallback' else 'ALGO03_fallback'
    if v4['decision']=='ALGO05_additive':
        selected=additive_summary(v4);decision=v4['decision']
    if terminal['decision']=='ALGO06_additive':
        selected=additive_summary(terminal);decision=terminal['decision']
    return dict(run_id=run_id,selected_model=MODEL_VERSION,state='complete',baseline=summary(v1),
        incumbent=summary(v2),selected=selected,position=terminal['position'],
        decision=decision,fallback=terminal['decision']!='ALGO06_additive',reason=terminal.get('failure'),
        baseline_seconds=v2['baseline_seconds'],incumbent_seconds=terminal['incumbent_seconds'],
        numerical_seconds=v3['numerical_seconds'],recovery_seconds=terminal['recovery_seconds'],total_seconds=terminal['total_seconds'])

class GraphPositionLookupV5(GraphPositionViewV5):
    def __init__(self,root,model_version,*,lookup=None,**kwargs):
        super().__init__(root,model_version,**kwargs)
        self.lookup=lookup if lookup is not None else FastGraphPositionLookupV5(root)

    def detail(self,run_id):
        safe_id(run_id)
        terminal=self.lookup.completed_run(run_id)
        if terminal is not None:
            return completed_view(run_id,terminal)
        return super().detail(run_id)

def graph_position_view(root,model_version):
    return GraphPositionLookupV5(root,model_version) if model_version==MODEL_VERSION else previous_view(root,model_version)
