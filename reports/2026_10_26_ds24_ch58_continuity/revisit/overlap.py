"""Post-outcome descriptive overlap only. Does not modify the sealed forecasts."""
from pathlib import Path
import study

HERE = Path(__file__).resolve().parent


def main():
    predictions = study.load(HERE / 'predictions.json')
    lookup = {(r['request_id'], r['receiver_id']): r for r in predictions['rows']}
    rows = []
    for slot in study.load(HERE / 'panel.json')['slots']:
        for cell in slot['cells']:
            h = cell['header']
            f = lookup[(h['request_id'], h['receiver_id'])]['forecast']
            earlier = sorted(cell['earlier'], key=lambda p: p['valid_start_counter'])
            current = bool(study.donors(cell['target_original'], h['sample_rate_hz']))
            latest = bool(study.donors(earlier[-1], h['sample_rate_hz'])) if earlier else False
            rows.append(dict(request_id=h['request_id'], channel=h['channel'], receiver_id=h['receiver_id'],
                             original_target_gatepass=current, latest_donor_gatepass=latest,
                             forecast_available=f['primary_mode'] is not None))
    def counts(selected):
        return dict(cells=len(selected), original_target_gatepass=sum(r['original_target_gatepass'] for r in selected),
            original_target_and_latest_gatepass=sum(r['original_target_gatepass'] and r['latest_donor_gatepass'] for r in selected),
            original_target_and_forecast_available=sum(r['original_target_gatepass'] and r['forecast_available'] for r in selected))
    study.write(HERE / 'overlap_evaluation.json', dict(evaluation_only=True,
        source_panel_sha256=study.sha(HERE / 'panel.json'), predictions_sha256=study.sha(HERE / 'predictions.json'),
        earlier_only_predictor_unchanged=True, overall=counts(rows),
        by_channel={str(ch): counts([r for r in rows if r['channel'] == ch]) for ch in study.CHANNELS}, rows=rows))


if __name__ == '__main__':
    main()
