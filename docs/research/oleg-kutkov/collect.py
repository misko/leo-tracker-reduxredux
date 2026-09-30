"""Archive public Starlink research sources; never execute downloaded content."""
import concurrent.futures
import hashlib
import json
import re
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOCAL = BASE / 'local'


class Content(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()
        self.words = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ('href', 'src', 'data-src') and value:
                self.links.add(value)
            if key == 'srcset' and value:
                self.links.update(
                    part.strip().split()[0] for part in value.split(',') if part.strip())

    def handle_data(self, data):
        self.words.append(data)


def normalize(url, parent):
    url = urllib.parse.urljoin(parent, url)
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https'):
        return None
    return urllib.parse.urlunsplit(parsed._replace(fragment=''))


def fetch(url):
    name = hashlib.sha256(url.encode()).hexdigest()[:20]
    suffix = Path(urllib.parse.urlsplit(url).path).suffix
    suffix = suffix if re.fullmatch(r'\.[a-zA-Z0-9]{1,8}', suffix) else '.html'
    path = LOCAL / 'objects' / (name + suffix)
    info = dict(url=url, path=str(path.relative_to(BASE)))
    try:
        if path.exists():
            raw = path.read_bytes()
            info['cached'] = True
        else:
            request = urllib.request.Request(
                url, headers={'User-Agent': 'StarlinkResearchArchive/1.0'})
            with urllib.request.urlopen(request, timeout=35) as response:
                info.update(final_url=response.url,
                            content_type=response.headers.get('Content-Type'))
                raw = response.read(256 * 1024 * 1024 + 1)
            if len(raw) > 256 * 1024 * 1024:
                raise ValueError('Resource exceeds 256 MiB per-file bound; cataloged, not saved')
            path.write_bytes(raw)
        info.update(status='downloaded', bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    except Exception as exc:
        info.update(status='failed', error=str(exc))
    return info


def main():
    (LOCAL / 'objects').mkdir(parents=True, exist_ok=True)
    rows = []
    articles = []
    for kind in ('posts', 'pages'):
        url = f'https://olegkutkov.me/wp-json/wp/v2/{kind}?search=starlink&per_page=100'
        row = fetch(url)
        rows.append(row)
        if row['status'] != 'downloaded':
            raise RuntimeError(row)
        articles.extend(json.loads((BASE / row['path']).read_text()))
    graph = []
    downloads = set()
    for article in articles:
        title = Content()
        title.feed(article['title']['rendered'])
        title_text = ''.join(title.words)
        parser = Content()
        parser.feed(article['content']['rendered'])
        downloads.add(article['link'])
        text_path = LOCAL / f'article-{article["id"]}.txt'
        text_path.write_text(title_text + '\n' + article['link'] + '\n\n' + '\n'.join(parser.words))
        for link in sorted(parser.links):
            url = normalize(link, article['link'])
            if not url:
                continue
            parsed = urllib.parse.urlsplit(url)
            asset = '/wp-content/uploads/' in parsed.path
            attachment = bool(re.search(
                r'\.(pdf|zip|7z|gz|bin|srec|sch|brd|kicad_pcb)$', parsed.path, re.I))
            selected = asset or attachment
            if selected:
                downloads.add(url)
            graph.append(dict(source=article['link'], title=title_text, target=url,
                              selected=selected))
    (BASE / 'links.json').write_text(json.dumps(graph, indent=2) + '\n')
    (BASE / 'articles.json').write_text(json.dumps([
        dict(id=a['id'], url=a['link'], title=a['title']['rendered'], date=a['date'],
             modified=a['modified'], text=f'local/article-{a["id"]}.txt') for a in articles
    ], indent=2) + '\n')
    extra = BASE / 'extra-urls.json'
    if extra.exists():
        downloads.update(json.loads(extra.read_text()))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for index, row in enumerate(pool.map(fetch, sorted(downloads)), 1):
            rows.append(row)
            if index % 25 == 0:
                print(f'{index}/{len(downloads)} resources processed', flush=True)
    (BASE / 'manifest.json').write_text(json.dumps(dict(
        retrieved_utc=datetime.now(UTC).isoformat(), resources=rows), indent=2) + '\n')
    print(json.dumps(dict(articles=len(articles), resources=len(rows),
                          failed=sum(r['status'] != 'downloaded' for r in rows),
                          bytes=sum(r.get('bytes', 0) for r in rows))), flush=True)


if __name__ == '__main__':
    main()
