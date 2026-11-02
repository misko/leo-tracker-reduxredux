"""Pure public ALGO07 projection shared by API and standard publication."""
from leo.contracts.fast_graph_position_v6 import MODEL_VERSION
from leo.storage.graph_position_lookup_v5 import completed_view as previous_completed_view


def completed_view(run_id, terminal):
    view=previous_completed_view(run_id,terminal['incumbent'])
    accepted=terminal['decision']=='ALGO07_reassociation'
    if accepted:
        view['selected']=dict(model_version=MODEL_VERSION,state='complete',
                              position=terminal['position'],arms=terminal['candidate']['arms'])
    view.update(selected_model=MODEL_VERSION,state='complete',position=terminal['position'],
        decision=terminal['decision'],fallback=not accepted,reason=terminal.get('failure'),
        incumbent_seconds=terminal['incumbent_seconds'],recovery_seconds=terminal['recovery_seconds'],
        total_seconds=terminal['total_seconds'])
    return view
