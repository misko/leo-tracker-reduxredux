"""Read-only standard ALGO07 result and digest-bound figure routes."""
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse
from html import escape
from urllib.parse import quote

from leo.contracts.fast_standard_analysis import ALGO08, MODEL, PLOTS


def standard_analysis_router(reader):
    router=APIRouter(prefix='/api/v2/fast-scans')

    @router.get('/{run_id}/standard-analysis')
    def detail(run_id: str):
        try:
            return reader.detail(run_id)
        except (OSError,ValueError) as error:
            raise HTTPException(404,'Standard analysis not found') from error

    @router.get('/{run_id}/standard-analysis/{name}.png')
    def figure(run_id: str,name: str,sha256: str | None=None):
        try:
            data=reader.artifact(run_id,name,sha256)
            return Response(data,media_type='image/png',headers={'Cache-Control':'public, max-age=31536000, immutable'} if sha256 else {'Cache-Control':'no-cache'})
        except (OSError,ValueError) as error:
            raise HTTPException(404,'Standard figure not found') from error

    @router.get('/{run_id}/standard-analysis/position-grid.json')
    def position_grid(run_id: str):
        try:
            grid=reader.position_grid(run_id)
            if grid is None:raise FileNotFoundError('Position grid unavailable')
            return grid
        except (OSError,ValueError) as error:
            raise HTTPException(404,'Standard position grid not found') from error

    @router.get('/{run_id}/standard-analysis/position-path.json')
    def position_path(run_id: str):
        try:
            path=reader.position_path(run_id)
            if path is None:raise FileNotFoundError('Recorded path unavailable')
            return path
        except (OSError,ValueError) as error:
            raise HTTPException(404,'Standard position path not found') from error
    @router.get('/{run_id}/standard-analysis/compare/{other_id}', response_class=HTMLResponse)
    def compare(run_id: str, other_id: str):
        try:
            pair = sorted((reader.detail(run_id), reader.detail(other_id)),
                          key=lambda row: row['model_version'] == ALGO08)
            if ([row['model_version'] for row in pair] != [MODEL, ALGO08]
                    or any(row['state'] != 'complete' for row in pair)
                    or not pair[0].get('session_id') or pair[0]['session_id'] != pair[1].get('session_id')):
                raise ValueError('Complete ALGO07 and ALGO08 results for one acquisition required')
        except (OSError, ValueError) as error:
            raise HTTPException(404, 'Matched standard analyses unavailable') from error
        plots = []
        for name in ('position', *PLOTS[:-1]):
            columns = []
            for label, row in zip(('ALGO07', 'ALGO08'), pair, strict=True):
                entry = next(a for a in row['artifacts'] if a['name'] == name)
                url = (f"/api/v2/fast-scans/{quote(row['run_id'], safe='')}/standard-analysis/"
                       f"{name}.png?sha256={quote(entry['sha256'], safe='')}")
                columns.append(f'<figure><figcaption>{label}</figcaption><a href="{url}">'
                               f'<img loading="lazy" alt="{label} {name}" src="{url}"></a></figure>')
            label = {'position': 'Position estimates', 'track-rms': 'RMS by track'}.get(name)
            if label is None:
                channels, kind = name.rsplit('-', 1)
                label = channels.upper() + ' · ' + {'all':'All detections', 'unassociated':'Unassociated detections',
                                                       'residuals':'Frequency residuals'}[kind]
            plots.append(f'<h2>{label}</h2><section>{"".join(columns)}</section>')
        return ('<!doctype html><html lang="en"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>ALGO07 and ALGO08 | Fast scan</title><style>'
                'body{font:1rem system-ui;margin:2vw;color:#172534}section{display:grid;'
                'grid-template-columns:repeat(2,minmax(0,1fr));gap:1vw}figure{margin:0}'
                'figcaption{font-weight:600}img{width:100%;height:auto}</style>'
                '<h1>ALGO07 and ALGO08</h1><p>Same recording · '
                + escape(pair[0]['session_id']) + '</p>' + ''.join(plots) + '</html>')
    return router
