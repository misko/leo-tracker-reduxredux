"""Exercise saved selection under the exact raw-wrapper partial-class binding."""

import argparse
from functools import partial
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


def smoke(output):
    import empty_bootstrap as staged

    staged.load_runtime()
    from anchor_exposure import enroll
    from aperture_trial import write
    from full_short_run import RECIPE_SHA,checked_recipe
    from held_cycle_refined import FrequencyChanges, select_refined
    from leo.contracts.digests import canonical_digest
    import mixed_aperture_receiver as mixed
    from north_factor_swap import rebound
    from raw_cfo_north_trial import native_file
    from short_cfo_raw import RefinedShortDetector, recipe
    from south_cfo_route import CFO, HISTORY, INVENTORY, UNFILTERED, audit_selected

    original,history = (json.loads(staged.checked(native_file(folder),pin)) for folder,pin in (UNFILTERED,HISTORY))
    rows = list(original['source']['probes'])
    retained = history['source']['probes']
    anchor_schedule = list(enroll(original))
    index = next(i for i,(event,selected) in enumerate(zip(anchor_schedule,retained,strict=True))
                 if event[4] == 'short' and selected['candidates'])
    row = rows[index]
    factor, = row['candidates']
    original_cfo = factor[CFO]
    altered_cfo = original_cfo + 0.125
    rows[index] = dict(row,candidates=[dict(factor,**{CFO:altered_cfo})])
    alternate_recipe = recipe(checked_recipe(),RECIPE_SHA)
    alternate = rebound(original,rows,alternate_recipe)
    changes = FrequencyChanges()
    changes.changed[row['visit_index'],row['receiver_id']] = original_cfo,altered_cfo
    changes.attempted = sum(bool(row['candidates']) and entry[4] == 'short' for row,entry in zip(rows,anchor_schedule,strict=True))
    with patch.object(mixed,'MixedApertureDetector',partial(RefinedShortDetector,policy=SimpleNamespace())):
        packet,mapped,detector,detail = select_refined(alternate,alternate_recipe,changes,
            original['source']['session_id'],INVENTORY,output.with_suffix('.selector.json'))
    verified = audit_selected(original,history,packet,detail['choice'])
    if (len(verified['changed']) != 1 or detail['pre_refinement_probes_sha256'] != verified['original_probe_sha256']
            or 'sha256:'+detector != canonical_digest(mapped)):
        raise ValueError('The saved partial-class test changed the old receiver choice or selected CFO witness')
    write(output,dict(verified=True,synthetic_one_cfo_change=True,waveform_calls=0,detail=detail,retained=verified))


if __name__ == '__main__':
    sys.path.insert(0,str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    smoke(parser.parse_args().output)
