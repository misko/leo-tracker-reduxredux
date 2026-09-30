"""Archive public video metadata/captions and record X search coverage."""
import concurrent.futures
import json
import re
from urllib.parse import quote

from collect import BASE, fetch


def acquire(urls):
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(fetch, sorted(set(urls))))


def main():
    queries = ['firmware', 'beamformer', 'Catapult', 'Starlink teardown', 'GPS', 'xp70']
    searches = acquire('https://x.com/search?q=' + quote('from:olegkutkov ' + q)
                       + '&src=typed_query&f=live' for q in queries)
    (BASE / 'search-manifest.json').write_text(
        json.dumps(dict(resources=searches), indent=2) + '\n')
    ids = set()
    for link in json.loads((BASE / 'embedded-links.json').read_text()):
        match = re.search(r'youtube.com/embed/([\w-]+)', link['target'])
        if match:
            ids.add(match[1])
    urls = ['https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v='
            + vid + '&format=json' for vid in ids]
    urls += ['https://www.youtube.com/watch?v=' + vid
             for vid in ('FobTifrG1VI', 'oGQlVcpmyD4', 'R2IzXjXjJhs')]
    rows = acquire(urls)
    captions, tracks = [], []
    for row in rows:
        if row['status'] != 'downloaded' or '/watch?' not in row['url']:
            continue
        raw = (BASE / row['path']).read_text(errors='replace')
        match = re.search(r'"captionTracks"\s*:\s*', raw)
        if match:
            entries, _ = json.JSONDecoder().raw_decode(raw[match.end():])
            for entry in entries:
                url = entry['baseUrl'] + '&fmt=json3'
                captions.append(url)
                tracks.append(dict(video=row['url'], language=entry['languageCode'], url=url))
    rows.extend(acquire(captions))
    (BASE / 'video-manifest.json').write_text(json.dumps(dict(
        scope='15 embedded video metadata pages, three teardown watch pages, available captions; '
              'video streams not downloaded', tracks=tracks, resources=rows), indent=2) + '\n')
    for row in rows:
        if 'timedtext' in row['url']:
            print(row['status'], row.get('bytes'), row['path'], flush=True)


if __name__ == '__main__':
    main()
