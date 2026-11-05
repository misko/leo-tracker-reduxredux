"""External bounded exact oracle for joint position likelihood and descent.

Default mode independently nominates one zero-calibration hypothesis. Discovery
mode compares seed proposals. Initial-search mode compares the complete initial
regional branch policy using explicitly declared solver budgets. None includes
the later recovery or publication stages. Old imports occur only in reference mode.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signed_snapshot(context):
    """Every numerical context field plus its resulting likelihood and physical state."""
    result = {k:v for k,v in context.items() if k not in ('scan', 'base')}
    result['original_protected'] = sorted(result['original_protected'])
    p, x = context['base'], context['x']
    result['base'] = dict(calculated=p.calculate(x), state=p.state(x),
        residual=p.residual(x), conditional_frequency=p.conditional_frequency(x),
        members=p.members, labels=p.labels, keep=p.keep, reference=p.reference,
        events=p.events, event_start=p.event_start)
    return result


def run(args):
    if args.additional_position:
        args.residual_screen = True
    if args.residual_screen:
        args.additional_preflight = True
    if args.additional_preflight:
        args.gap_recovery = True
    if args.side == 'candidate':
        from check_algo07v3_track_preparation import deny_legacy

        sys.addaudithook(deny_legacy)
        from leo.analysis.localization_v3.discovery import fresh_discovery
        from leo.analysis.localization_v3.families import AnchoredFamilies, nomination_rows
        from leo.analysis.localization_v3.position import NormalPosition as Position
        from leo.analysis.localization_v3.position import fit
        from leo.analysis.localization_v3.region import SearchRegion
        from leo.analysis.localization_v3.scan import ScanLikelihood
    else:
        if args.reference_runtime is None:
            raise ValueError('Explicit reference runtime required')
        sys.path[:0] = [str(args.reference_runtime/'src'), str(args.reference_runtime/'tools')]
        from evaluate_ds23_phase_refreshed import FreshScan
        from investigate_dsx01_localization_failures import DiagnosticNormal as Position
        from investigate_dsx01_localization_failures import fit
        from iterate_dsx01_position_nominations import AnchoredFamilies, nomination_rows
        from prototype_dsx01_continuous_position import CENTER, native_point
        from run_dsx01_clean_region import fresh_discovery

        if tuple(args.search_center) != tuple(CENTER):
            raise ValueError('Reference has a frozen search center; it cannot be overridden')

    import numpy as np

    from leo.analysis.research.phase_linear_geometry import phase_linear_frequency

    def read(name):
        return json.loads((args.source/name).read_text())

    started = time.monotonic()
    if args.side == 'candidate':
        summary = read('summary.json')
        for name, sha in summary['source_files'].items():
            if digest(args.source/name) != sha:
                raise ValueError('Candidate preparation binding differs')
        metadata = read('metadata.json')
        with np.load(args.source/'bank.npz') as arrays:
            bank = dict(arrays)
        region = SearchRegion(tuple(args.search_center))
        scan = ScanLikelihood(read('tracks.json')['tracks'], bank, read('nominal_elements.json'),
            origin_utc_ns=metadata['origin_utc_ns'], regional_center=metadata['regional_center'],
            noise=read('radio_noise.json'), noise_sha256=digest(args.source/'radio_noise.json'),
            search_region=region, previous_tle=(args.source/'previous.tle').read_text(),
            previous_tle_sha256=digest(args.source/'previous.tle'))
        point = region.native_point(scan, [0., 0.])
    else:
        scan = FreshScan(args.source, noise_mode='radio')
        point = native_point(scan, [0., 0.])
    annotation_mode = args.predictive_annotation or args.predictive_inclusion
    recovery_mode = args.predictive_recovery or args.numerical_recovery or args.gap_recovery
    inventory_mode = args.recovery_inventory or annotation_mode or recovery_mode
    cavity_mode = args.cavity_policy or inventory_mode
    signed_mode = args.signed_policy or cavity_mode
    history_mode = args.history_policy or signed_mode
    if args.initial_search or args.conservative or history_mode:
        if (args.conservative or history_mode) and (args.rounds, args.iterations) != (5, 48):
            raise ValueError('Recovery comparisons require full production fitting budgets')
        if args.side == 'candidate':
            from leo.analysis.localization_v3.initial_search import initial_search
        else:
            from algo07v3_initial_search_oracle import reference_initial_search as initial_search
        initial = initial_search(scan, scan.radio_sigma_hz,
            seed_budget=args.seed_budget, branch_budget=args.branch_budget,
            rounds=args.rounds, iterations=args.iterations)
        if args.conservative or history_mode:
            if args.side == 'candidate':
                from leo.analysis.localization_v3.conservative_recovery import conservative_recovery

                prior = read('genuine_previous_receipt.json')
                def final_scan():
                    return ScanLikelihood(read('tracks.json')['tracks'], bank,
                        read('nominal_elements.json'), origin_utc_ns=metadata['origin_utc_ns'],
                        regional_center=metadata['regional_center'], noise=read('radio_noise.json'),
                        noise_sha256=digest(args.source/'radio_noise.json'), search_region=region,
                        previous_tle=(args.source/'genuine_previous.tle').read_text(),
                        previous_tle_sha256=prior['catalogue_sha256'],
                        previous_sources=prior['sources'])
                observations = read('tracks.json')['observations']
            else:
                from algo07v3_initial_search_oracle import reference_conservative_recovery

                conservative_recovery = reference_conservative_recovery
                prior_root = args.source.parent/'causal_prior'/args.source.name
                def final_scan():
                    scan = FreshScan(args.source, noise_mode='radio')
                    scan.previous_tle_path = prior_root/'previous.tle'
                    scan.receipt = json.loads((prior_root/'receipt.json').read_text())
                    return scan
                observations = read('observations.json')
            scan = final_scan()
            recovery = conservative_recovery(scan, initial, observations)
            result = dict(initial=fingerprint(initial), recovery=fingerprint(recovery))
            if history_mode:
                scan = final_scan()
                if args.side == 'candidate':
                    from leo.analysis.localization_v3.history_policy import history_policy

                    history_path = args.source/'phase_history.json'
                    forecast_path = args.source/'phase_forecast.json'
                    raw = json.loads(history_path.read_text())
                    forecast = json.loads(forecast_path.read_text())
                    history_result = history_policy(scan, recovery, raw, forecast,
                        case='SCAN', cutoff_utc_ns=metadata['cutoff_utc_ns'],
                        history_sha256=digest(history_path))
                else:
                    from algo07v3_initial_search_oracle import reference_history_policy

                    history_path = args.source.parent/'causal_phase_history'/(
                        args.source.name+'.json')
                    forecast_path = history_path.with_name(args.source.name+'_forecast.json')
                    raw = json.loads(history_path.read_text())
                    forecast = json.loads(forecast_path.read_text())
                    history_result = reference_history_policy(scan, recovery, raw, forecast,
                                                               digest(history_path))
                result['history_policy'] = fingerprint(history_result)
                if signed_mode:
                    scan = final_scan()
                    if args.side == 'candidate':
                        from leo.analysis.localization_v3.signed_context import signed_context

                        context = signed_context(scan, recovery, history_result, raw, forecast,
                            observations, case='SCAN', history_sha256=digest(history_path),
                            cutoff_utc_ns=metadata['cutoff_utc_ns'])
                    else:
                        from algo07v3_signed_oracle import reference_signed_context

                        context = reference_signed_context(scan, recovery, history_result,
                            raw, forecast, observations, case='SCAN',
                            history_sha256=digest(history_path))
                    result['signed_policy'] = fingerprint(signed_snapshot(context))
                    if cavity_mode:
                        if args.side == 'candidate':
                            from leo.analysis.localization_v3.family_cavity import (
                                cavity_policy,
                                nominate_families,
                            )
                        else:
                            from algo07v3_cavity_oracle import (
                                reference_cavity_policy as cavity_policy,
                            )
                            from algo07v3_cavity_oracle import (
                                reference_nominate_families as nominate_families,
                            )
                        nominations = nominate_families(context)
                        result['cavity_nominations'] = fingerprint(nominations)
                        print('cavity nominations', nominations['status'], flush=True)
                        selected = cavity_policy(context, nominations)
                        result['cavity_policy'] = fingerprint(selected)
                        print('cavity position', selected['status'], flush=True)
                        if inventory_mode:
                            if args.side != 'candidate' or not args.scan_identities:
                                raise ValueError('Inventory mode requires candidate and scan IDs; '
                                                 'use the separate inventory oracle for reference')
                            from leo.analysis.localization_v3.recovery_inventory import (
                                prepare_recovery,
                            )

                            inventory_began = time.monotonic()
                            recovery_context, inventory_result = prepare_recovery(
                                scan, selected, observations,
                                identities=args.scan_identities)
                            inventory_seconds = time.monotonic() - inventory_began
                            result['recovery_inventory'] = fingerprint(inventory_result)
                            print('recovery inventory', inventory_result['eligible_targets'],
                                  flush=True)
                            if recovery_mode:
                                from leo.analysis.localization_v3.recovery_controller import (
                                    recover_tracks,
                                )

                                completed_stages = {'inventory': dict(value=inventory_result,
                                                                      seconds=inventory_seconds)}

                                def complete_stage(name, operation):
                                    began_stage = time.monotonic()
                                    try:
                                        value = operation()
                                    except Exception as error:
                                        print('recovery stage failed', name, type(error).__name__,
                                              str(error), flush=True)
                                        return False, None
                                    print('recovery stage complete', name, flush=True)
                                    completed_stages[name] = dict(value=value,
                                        seconds=time.monotonic()-began_stage)
                                    return True, value

                                selected_states = []
                                recovered = recover_tracks(recovery_context, inventory_result,
                                    run_stage=complete_stage, discovery_allowed=lambda: True,
                                    on_selection=selected_states.append)
                                result['predictive_recovery'] = fingerprint(recovered)
                                if args.numerical_recovery or args.gap_recovery:
                                    from leo.analysis.localization_v3.numerical_recovery import (
                                        replay_recovery,
                                    )

                                    def numerical_stage(name, operation):
                                        try:
                                            return True, operation()
                                        except Exception as error:
                                            print('numerical stage failed', name,
                                                  type(error).__name__, str(error), flush=True)
                                            return False, None

                                    if args.gap_recovery:
                                        from leo.application.localization_v3 import (
                                            prepare_additional_checkpoint, recover_gap_checkpoint,
                                            recover_numerical_checkpoint,
                                        )

                                        prepared_recovery = dict(status='track_recovery_prepared',
                                            recovery_context=recovery_context,
                                            inventory=inventory_result)
                                        predictive = dict(status='predictive_recovery_evaluated',
                                            recovery=recovered, completed_stages=completed_stages,
                                            selected_state=selected_states[0])
                                        numerical = recover_numerical_checkpoint(prepared_recovery,
                                            predictive, run_stage=numerical_stage,
                                            discovery_allowed=lambda: True, clock=time.monotonic,
                                            charge_reused=lambda _: None)
                                        replay = numerical['recovery']
                                    else:
                                        replay = replay_recovery(recovery_context, inventory_result,
                                            recovered, completed_stages, run_stage=numerical_stage,
                                            discovery_allowed=lambda: True, clock=time.monotonic,
                                            charge_reused=lambda _: None)
                                    # All-work qualification: logical charge is not admission.
                                    # Keep deterministic scientific reuse decisions separately.
                                    result['numerical_recovery'] = fingerprint({
                                        k:v for k,v in replay.items() if k != 'stage_replay'})
                                    result['numerical_stage_replay'] = [{
                                        k:v for k,v in row.items() if k not in (
                                            'charged_original_seconds',
                                            'additional_logical_seconds', 'reuse_wall_seconds')}
                                        for row in replay['stage_replay']]
                                    if args.gap_recovery:
                                        def gap_stage(name, operation, cap):
                                            started_stage = time.monotonic()
                                            value = operation()
                                            if time.monotonic() - started_stage >= cap:
                                                raise TimeoutError('gap stage exceeded its cap')
                                            print('gap stage complete', name, flush=True)
                                            return True, value

                                        gaps = recover_gap_checkpoint(prepared_recovery, numerical,
                                            observations, run_stage=gap_stage,
                                            clock=time.monotonic, maximum_seconds=1200)
                                        if gaps['status'] != 'gap_recovery_evaluated':
                                            raise ValueError('gap source checkpoint incomplete')
                                        gap_result = dict(gaps['recovery'])
                                        gap_result['stages'] = [
                                            {k:v for k,v in row.items() if k != 'seconds'}
                                            for row in gap_result['stages']]
                                        result['gap_recovery'] = fingerprint(gap_result)
                                        if args.additional_preflight:
                                            additional = prepare_additional_checkpoint(
                                                prepared_recovery, read('tracks.json'), metadata,
                                                gaps, identities=sorted(args.scan_identities))
                                            if additional['status'] != 'additional_recovery_prepared':
                                                raise ValueError('selected checkpoint did not prepare')
                                            selected = additional['residual_context']
                                            result['additional_recovery'] = fingerprint(dict(
                                                status=additional['status'],
                                                inventory=additional['residual_inventory'],
                                                preflight=additional['preflight'],
                                                selected_owners=gaps['selected_state']['owners'],
                                                families=[f.receipt for f in selected['families']],
                                                replay_checks=selected['replay_checks'],
                                                recovery_complete=False))
                                            if args.residual_screen:
                                                from leo.application.localization_v3 import (
                                                    screen_additional_recovery,
                                                )
                                                catalogue = json.loads(args.recovery_catalogue.read_text())
                                                screened = screen_additional_recovery(additional,
                                                    catalogue, region, on_target=lambda row: print(
                                                        'residual screen', row['source']['fragment_id'],
                                                        len(row['finalists']), flush=True))
                                                result['residual_screen'] = fingerprint(screened)
                                                if args.additional_position:
                                                    from leo.application.localization_v3 import fit_additional_recovery
                                                    result['additional_position'] = fingerprint(fit_additional_recovery(
                                                        additional, screened, catalogue, observations,
                                                        clock=time.monotonic, on_arm=lambda tag, arm, row: print(
                                                            'additional position', tag, arm,
                                                            row['all_checked_gates_pass'], flush=True)))
                                            if args.preflight_packet:
                                                with args.preflight_packet.open('x') as stream:
                                                    json.dump(additional['preflight'], stream,
                                                        default=lambda value: np.asarray(value).tolist(),
                                                        allow_nan=False)
                                                    stream.write('\n')
                            if annotation_mode:
                                from leo.analysis.localization_v3.predictive_annotation import (
                                    annotate,
                                )

                                target = inventory_result['selected_targets'][args.target_rank]
                                annotation = annotate(recovery_context,
                                    inventory_result['inventory'], target['track_id'],
                                    inactive_fragment=target['inactive_fragment'],
                                    on_proposal=lambda seed, q: print(
                                        'predictive proposal', seed, q['norad'], flush=True))
                                result['predictive_annotation'] = fingerprint(annotation)
                                if args.predictive_inclusion:
                                    from leo.analysis.localization_v3.recovery_inclusion import (
                                        include_annotation,
                                    )

                                    inv = dict(inventory_result['inventory'],publication_support=
                                               inventory_result['publication_support'])
                                    inclusion = include_annotation(recovery_context,inv,annotation)
                                    result['predictive_inclusion'] = fingerprint(inclusion)
                                    print('predictive inclusion',inclusion['status'],flush=True)
        else:
            result = fingerprint(initial)
    elif args.discovery:
        result = dict(candidates=fingerprint(fresh_discovery(
            scan, scan.radio_sigma_hz, budget=args.seed_budget)))
    else:
        base = phase_linear_frequency(scan.geometry, *args.search_center)
        state = dict(beta=np.zeros(8), phases=np.zeros(len(scan.norads)), extra={},
                     smooth=np.zeros((2, scan.rx_basis[0].shape[1])))
        _, rows, nominees, _ = scan.association(state, base, point, 'receiver_smooth')
        seed = dict(state=state, rows=nomination_rows(scan, rows, nominees))
        anchored = AnchoredFamilies(scan, seed, 'receiver_smooth', False, [0., 0.])
        node = dict(seed=seed, aliases=anchored.alias)
        result = dict(node=fingerprint(node), arms={})
        for arm in ('c0', 'fitted_c'):
            problem = Position(scan, node, scan.radio_sigma_hz, arm == 'fitted_c')
            names = ('rows', 'members', 'labels', 'flat_labels', 'flat_times', 'alias', 'reference',
                     'phase_sigma', 'values', 'q', 'hardware', 'smooth', 'constants', 'supported',
                     'supported_local', 'mode_bank', 'mode_metadata', 'initial', 'lower', 'upper',
                     'noise_groups', 'point_noise', 'keep', 'noise_volume')
            record = dict(design={name:fingerprint(getattr(problem, name)) for name in names},
                          evaluations=[], fits=[])
            for xy in ([0., 0.], [3., -4.], [-7., 8.]):
                x = np.asarray(xy)
                record['evaluations'].append(dict(point=xy,
                    calculated=fingerprint(problem.calculate(x)),
                    residual=fingerprint(problem.residual(x)), state=fingerprint(problem.state(x)),
                    conditional_frequency=fingerprint(problem.conditional_frequency(x))))
            print(arm, 'design and three evaluations complete', flush=True)
            phase, anchor = np.zeros(len(problem.labels)), np.zeros(2)
            for epoch in range(args.rounds):
                problem = Position(scan, node, scan.radio_sigma_hz, arm == 'fitted_c',
                                   reference=phase)
                fitted = fit(problem, anchor, iterations=args.iterations)
                anchor = np.array(fitted['parameters'])
                posterior = problem.state(anchor)['phases'][problem.labels]
                record['fits'].append(fingerprint(dict(epoch=epoch, fit=fitted,
                    phase_reference=phase.copy(), posterior_phase_s=posterior,
                    max_reference_change_s=float(np.max(abs(posterior-phase))))))
                phase = np.clip(posterior, -15, 15)
                print(arm, 'phase round', epoch, 'complete', flush=True)
            result['arms'][arm] = record
    with args.output.open('x') as stream:
        json.dump(result, stream, sort_keys=True, allow_nan=False)
        stream.write('\n')
    modules = {name:str(module.__file__) for name, module in sys.modules.items()
               if getattr(module, '__file__', None) and (name.startswith('leo.')
               or (args.side == 'reference'
                   and str(module.__file__).startswith(str(args.reference_runtime))))}
    additional_inputs = {}
    if args.conservative or history_mode:
        paths = ([args.source/'genuine_previous.tle', args.source/'genuine_previous_receipt.json']
                 if args.side == 'candidate' else
                 [prior_root/'previous.tle', prior_root/'previous_receipt.json',
                  prior_root/'receipt.json', args.source/'observations.json'])
        additional_inputs = {str(path):digest(path) for path in paths}
        if history_mode:
            additional_inputs.update({str(path):digest(path)
                                      for path in (history_path, forecast_path)})
    receipt = dict(side=args.side, source=str(args.source), seconds=time.monotonic()-started,
        output_sha256=digest(args.output), rounds=args.rounds, iterations=args.iterations,
        discovery=args.discovery, initial_search=args.initial_search,
        conservative=args.conservative, history_policy=history_mode,
        signed_policy=signed_mode, cavity_policy=cavity_mode,
        recovery_inventory=inventory_mode, scan_identities=args.scan_identities,
        predictive_annotation=annotation_mode, predictive_inclusion=args.predictive_inclusion,
        predictive_recovery=recovery_mode,
        numerical_recovery=args.numerical_recovery or args.gap_recovery,
        gap_recovery=args.gap_recovery,
        additional_preflight=args.additional_preflight,
        residual_screen=args.residual_screen,
        additional_position=args.additional_position,
        recovery_catalogue=(dict(path=str(args.recovery_catalogue),
                                  sha256=digest(args.recovery_catalogue))
                            if args.recovery_catalogue else None),
        preflight_packet=(dict(path=str(args.preflight_packet), sha256=digest(args.preflight_packet))
                          if args.preflight_packet else None),
        recovery_admission=('all predeclared targets; test harness only'
                            if recovery_mode else None),
        target_rank=args.target_rank,
        additional_inputs=additional_inputs,
        seed_budget=args.seed_budget, branch_budget=args.branch_budget,
        search_center=args.search_center, full_localization_parity=False,
        modules={name:dict(path=path, sha256=digest(Path(path))) for name,path in modules.items()},
        tool_sources={str(Path(path).resolve()):digest(Path(path)) for path in (
            __file__, sys.modules['check_algo07v3_scan_likelihood'].__file__,
            *([sys.modules['algo07v3_initial_search_oracle'].__file__]
              if (args.initial_search or args.conservative or history_mode)
              and args.side == 'reference' else []),
            *([sys.modules['algo07v3_signed_oracle'].__file__]
              if signed_mode and args.side == 'reference' else []),
            *([sys.modules['algo07v3_cavity_oracle'].__file__]
              if cavity_mode and args.side == 'reference' else []))},
        inputs={name:digest(args.source/name) for name in ('tracks.json', 'bank.npz',
               'nominal_elements.json', 'radio_noise.json', 'previous.tle')})
    with args.output.with_suffix('.receipt.json').open('x') as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({k:receipt[k] for k in ('side','seconds','output_sha256')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--side', choices=('reference', 'candidate'), required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference-runtime', type=Path)
    parser.add_argument('--search-center', type=float, nargs=2, required=True)
    parser.add_argument('--rounds', type=int, default=2)
    parser.add_argument('--iterations', type=int, default=8)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--discovery', action='store_true')
    mode.add_argument('--initial-search', action='store_true')
    mode.add_argument('--conservative', action='store_true')
    mode.add_argument('--history-policy', action='store_true')
    mode.add_argument('--signed-policy', action='store_true')
    mode.add_argument('--cavity-policy', action='store_true')
    mode.add_argument('--recovery-inventory', action='store_true')
    mode.add_argument('--predictive-annotation', action='store_true')
    mode.add_argument('--predictive-inclusion', action='store_true')
    mode.add_argument('--predictive-recovery', action='store_true',
                      help='Test harness: complete all predeclared recovery work; no time-based omissions')
    mode.add_argument('--numerical-recovery', action='store_true',
                      help='Test harness: fresh predictive loop then conditional numerical replay')
    mode.add_argument('--gap-recovery', action='store_true',
                      help='Test harness: fresh prefix through owned numerical and gap checkpoints')
    mode.add_argument('--additional-preflight', action='store_true',
                      help='Test harness: bind selected checkpoints and prepare residual screening')
    mode.add_argument('--residual-screen', action='store_true',
                      help='Test harness: fresh implemented prefix through causal residual screen')
    mode.add_argument('--additional-position', action='store_true',
                      help='Test harness: fresh prefix through matched additional-family position trials')
    parser.add_argument('--recovery-catalogue', type=Path)
    parser.add_argument('--preflight-packet', type=Path)
    parser.add_argument('--target-rank', type=int, default=0)
    parser.add_argument('--scan-identities', nargs='+')
    parser.add_argument('--branch-budget', type=int, default=3)
    parser.add_argument('--seed-budget', type=int, default=4)
    args = parser.parse_args()
    if (args.residual_screen or args.additional_position) and args.recovery_catalogue is None:
        parser.error('Residual screening/position requires --recovery-catalogue')
    if args.preflight_packet and not (args.additional_preflight or args.residual_screen or args.additional_position):
        parser.error('--preflight-packet requires a preflight-producing mode')
    run(args)
