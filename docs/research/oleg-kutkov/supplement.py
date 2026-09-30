"""Index embedded references and save public X post text/media without running JS."""
import concurrent.futures
import json
import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

from collect import BASE, LOCAL, Content, fetch, normalize


def literals(raw, key):
    """Read JSON-compatible string literals only; never evaluate downloaded code."""
    values = []
    for match in re.finditer(r'\b' + re.escape(key) + r':("(?:[^"\\]|\\.)*")', raw):
        try:
            values.append(json.loads(match[1]))
        except json.JSONDecodeError:
            continue
    return sorted(set(values))


def main():
    rows = []
    for filename in ('manifest.json', 'additional-manifest.json'):
        rows.extend(json.loads((BASE / filename).read_text())['resources'])
    graph, urls = [], set()
    for row in rows:
        url = row['url']
        if row['status'] != 'downloaded' or urlsplit(url).hostname != 'olegkutkov.me':
            continue
        if '/wp-content/' in url or '/wp-json/' in url:
            continue
        parser = Content()
        parser.feed((BASE / row['path']).read_text(errors='replace'))
        for link in sorted(parser.links):
            target = normalize(link, url)
            if not target:
                continue
            host = urlsplit(target).hostname or ''
            if host == 'olegkutkov.me' and '/wp-content/uploads/' not in target:
                continue
            graph.append(dict(source=url, target=target))
            if re.match(r'https://(?:twitter|x)\.com/olegkutkov/status/\d+', target):
                urls.add(target.split('?')[0])
            # Keep forum illustrations, but don't follow spam or arbitrary external files.
            if host == 'olegkutkov.me' and '/wp-content/uploads/' in target:
                urls.add(target)
    seeds = BASE / 'supplement-urls.json'
    if seeds.exists():
        urls.update(json.loads(seeds.read_text()))
    known = {r['url'] for r in rows}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        added = list(pool.map(fetch, sorted(urls - known)))
    rows.extend(added)
    x_records, media = [], set()
    for row in rows:
        if row['status'] != 'downloaded':
            continue
        if not re.match(r'https://(?:twitter|x)\.com/olegkutkov/status/\d+', row['url']):
            continue
        raw = (BASE / row['path']).read_text(errors='replace')
        # Responses can include replies by other users. Preserve separately, no blanket attribution.
        texts = literals(raw, 'full_text')
        photos = literals(raw, 'media_url_https')
        links = literals(raw, 'expanded_url')
        media.update(u for u in photos if urlsplit(u).hostname == 'pbs.twimg.com')
        x_records.append(dict(url=row['url'], text_literals_including_replies=texts,
                              note_text_literals=literals(raw, 'text'),
                              media=photos, expanded_links=links, has_text=bool(texts)))
    (LOCAL / 'x-posts.json').write_text(json.dumps(x_records, indent=2) + '\n')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        added.extend(pool.map(fetch, sorted(media - known)))
    (BASE / 'embedded-links.json').write_text(json.dumps(graph, indent=2) + '\n')
    (BASE / 'supplement-manifest.json').write_text(json.dumps(dict(
        retrieved_utc=datetime.now(UTC).isoformat(), resources=added), indent=2) + '\n')
    print(f'{len(x_records)} X post pages with extracted literals; '
          f'{len(added)} additional resource attempts', flush=True)


if __name__ == '__main__':
    main()
