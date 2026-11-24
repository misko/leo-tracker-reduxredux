"""Verify the exact fine-salvage shadow work and downstream positive adoption."""

from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent


def clocks(rows):
    modes = ('control','candidate')
    sums = {mode:dict(cpu_ns=sum(row['clocks'][mode]['cpu_ns'] for row in rows),
                      elapsed_ns=sum(row['clocks'][mode]['elapsed_ns'] for row in rows)) for mode in modes}
    counters = {mode:dict(sum((Counter(row['counters'][mode]) for row in rows),Counter())) for mode in modes}
    return dict(aggregate=sums,counters=counters,order=Counter(row['order'][0] for row in rows),matched_calls=len(rows),
                net_cpu_ns=sums['control']['cpu_ns']-sums['candidate']['cpu_ns'],
                net_elapsed_ns=sums['control']['elapsed_ns']-sums['candidate']['elapsed_ns'])


def score(root):
    from aperture_trial import read,write
    from empty_bootstrap import checked
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0402_solver import ARMS,SETTINGS,inspect
    from rescue_phase_prepare_trial import CONTROLS,census

    binding, rows, timed = (read(root/name) for name in ('binding.json','fine-shadow.json','clock.json'))
    for name,pin in binding['sources'].items():
        checked(HERE/name,pin)
    current = root/'candidate'
    clock = timed['timing']
    worker = read(current/SETTINGS['audit_name'])
    observed = inspect(current,'candidate',worker['receipt'],clock,binding['input'],**SETTINGS)
    research = read(current/'joint-research-receipt.json')
    if (clock['exit_code'] or not worker['no_waveform'] or worker['handoffs'] != 1
            or not rows or research['receipt']['decision'] != 'complete' or not worker['graph']['enabled']):
        raise ValueError('Expected the current complete saved positive rescue with no receiver access')
    old_output,pin = CONTROLS['DS30-0402']
    prior = json.loads(checked(old_output/'joint-research-receipt.json',pin))
    old_receipt, receipt = prior['receipt'],research['receipt']
    for key in ('terminal_sha256','region','session_id','window_count','decision','counts'):
        if old_receipt[key] != receipt[key]:
            raise ValueError(f'The positive rescue changed original publication {key}')
    if any(prior['selected_rows'][arm] != observed['selected_rows'][arm] for arm in ARMS):
        raise ValueError('The isolated salvage changed at least one ordered owner')
    now, before = research['route_details'],prior['route_details']
    for key in ('support','salvage_shortlists','pair_passes','finish','signed','decision'):
        if now.get(key) != before.get(key):
            raise ValueError(f'New phase preparation changed exact conditional adoption {key}')
    for key in ('status','fit_calls','pair_admission','move_km','target_after_fit','finish'):
        if now['provisional_salvage'][key] != before['provisional_salvage'][key]:
            raise ValueError(f'Expected the prior adopted isolated and endpoint result ({key})')
    endpoint = now['provisional_salvage']['endpoint_trim']
    original_endpoint = before['provisional_salvage']['endpoint_trim']
    if any(endpoint[key] != original_endpoint[key] for key in ('status','component','dropped_id','finish')):
        raise ValueError('The shared endpoint pass changed its original rescued support')
    old_media = artifacts(old_output,old_receipt)['images']
    actual_media = observed['figures']
    if canonical_digest(old_media) != canonical_digest(actual_media) or len(actual_media) != 8:
        raise ValueError('Expected byte- and pixel-identical old and new eight-figure output')
    comparison = {}
    for name in ('grid','path'):
        docs = [getattr(FastStandardAnalysisStore(path),'position_'+name)(receipt['run_id']) for path in (old_output,current)]
        normalized = [{k:v for k,v in row.items() if k != 'elapsed_seconds'} for row in docs]
        if normalized[0] != normalized[1]:
            raise ValueError(f'Published numerical {name} changed')
        comparison[name] = canonical_digest(normalized[0])
    prices = clocks(rows)
    if prices['matched_calls'] != len(now['salvage_shortlists']):
        raise ValueError('Some genuine certified fine calls did not participate in the matched measurement')
    write(root/'result.json',dict(verified=True,binding=binding,clock=clock,publication=receipt,match=prices,calls=rows,
        current=census(research),prior=census(prior),reference=pin,terminal=observed['terminal'],
        owners={arm:dict(count=len(observed['selected_rows'][arm]),
                        ordered_sha256=canonical_digest(observed['selected_rows'][arm])) for arm in ARMS},
        figures=actual_media,standard_science=observed['science']['scientific_digests'],sidecars=comparison,
        adoption=dict(isolated=now['provisional_salvage']['status'],endpoint=endpoint['status'],
                      original_signed=now['signed']['status']),scorer_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == '__main__':
    sys.path.insert(0,str(HERE))
    app = ArgumentParser(description=__doc__)
    app.add_argument('root',type=Path)
    score(app.parse_args().root)
