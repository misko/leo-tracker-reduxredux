"""Collect public forum pages, pinned repository sources, and linked references."""
import concurrent.futures
import json
import re
import urllib.parse

from collect import BASE, LOCAL, Content, fetch, normalize


def topic_id(url):
    parsed = urllib.parse.urlsplit(url)
    match = re.fullmatch(r'topic=(\d+)\.\d+', parsed.query)
    return match[1] if parsed.hostname == 'olegkutkov.me' and match else None


def main():
    rows, repositories = [], []

    def get(url):
        row = fetch(url)
        rows.append(row)
        if row['status'] != 'downloaded':
            return ''
        return (BASE / row['path']).read_text(errors='replace')

    topics, pages, attachments = set(), set(), set()
    # Board 2 is Starlink; board 3 is Direct to Cell. Pagination is discovered.
    pending = {'https://olegkutkov.me/forum/index.php?board=2.0',
               'https://olegkutkov.me/forum/index.php?board=3.0'}
    while pending:
        url = pending.pop()
        if url in pages:
            continue
        pages.add(url)
        content = Content()
        content.feed(get(url))
        for link in content.links:
            if re.search(r'\?board=(2|3)\.\d+$', link) and link not in pages:
                pending.add(link)
            match = re.search(r'\?topic=(\d+)\.', link)
            if match:
                topics.add(f'https://olegkutkov.me/forum/index.php?topic={match[1]}.0')
    pending = set(topics)
    allowed_topics = {topic_id(t) for t in topics}
    seen = set()
    while pending:
        url = pending.pop()
        if url in seen:
            continue
        seen.add(url)
        raw = get(url)
        content = Content()
        content.feed(re.sub(r'<(script|style)\b.*?</\1>', '', raw, flags=re.S | re.I))
        tid = urllib.parse.urlsplit(url).query.replace('=', '-')
        (LOCAL / (tid + '.txt')).write_text(
            '\n'.join(w.strip() for w in content.words if w.strip()))
        for link in content.links:
            # Only pagination for discovered topics, not arbitrary neighboring threads.
            if topic_id(link) in allowed_topics and topic_id(link) is not None and link not in seen:
                pending.add(link)
            if 'action=dlattach' in link:
                attachments.add(normalize(link, url))
        if len(seen) % 20 == 0:
            print(f'{len(seen)} forum pages archived', flush=True)
    urls = set(attachments)
    for repo in ('Space-Debugger', 'starlink-wifi-gen2', 'satellite-lnb-controller'):
        metadata = json.loads(get(f'https://api.github.com/repos/olegkutkov/{repo}'))
        commit = json.loads(get(f'https://api.github.com/repos/olegkutkov/{repo}/commits/{metadata["default_branch"]}'))['sha']
        tree = json.loads(get(f'https://api.github.com/repos/olegkutkov/{repo}/git/trees/{commit}?recursive=1'))
        selected = []
        for entry in tree['tree']:
            path = entry['path']
            if entry['type'] != 'blob':
                continue
            if repo == 'Space-Debugger':
                choose = not path.startswith('build/windows/')
            elif repo == 'satellite-lnb-controller':
                choose = True
            else:
                choose = ('spacex' in path.lower() or path.startswith('payload/') or
                          '/' not in path or path == 'storage/cfg.ini')
            if choose:
                selected.append(path)
                urls.add(f'https://raw.githubusercontent.com/olegkutkov/{repo}/{commit}/{path}')
        repositories.append(dict(repository=repo, commit=commit,
                                 tree_truncated=tree.get('truncated'),
                                 selected=selected, total_entries=len(tree['tree'])))
    # Article links are archived one hop; do not request private-network URLs.
    for link in json.loads((BASE / 'links.json').read_text()):
        url = link['target']
        host = urllib.parse.urlsplit(url).netloc
        if link['selected'] or host in ('192.168.100.1', ''):
            continue
        if any(domain in host for domain in ('github.com', 'st.com', 'mipi.org', 'ti.com',
               'openwrt.org', 'linux-mtd', 'tldp.org', 'analog.com', 'monolithicpower.com',
               'qualcomm.com', 'mediatek.com', 'winbond.com', 'skyworksinc.com',
               'gpsworld.com', 'airoha.com', 'renesas.com', 'bufferbloat', 'thegoodpenguin')):
            urls.add(url)
        if host == 'github.com' and '/blob/' in url:
            urls.add(url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/'))
    urls.update([
        'https://x.com/olegkutkov',
        'https://x.com/olegkutkov/status/1787995742188994604',
        'https://twitter.com/olegkutkov/status/1655697905263542272',
        'https://twitter.com/olegkutkov/status/1750288105406390376',
        'https://twitter.com/olegkutkov/status/1595069902632923137',
        'https://twitter.com/olegkutkov/status/1624568258211840000',
        'https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/8719/emmc-4gb-8gb-ps8225-v50-it.pdf',
        'https://lists.bufferbloat.net/starlink/3ade5a67-2186-4008-80f9-4e85a4e38615%40olegkutkov.me/',
        'https://lists.bufferbloat.net/starlink/d9aebf16-ef80-431a-935f-2e7e9c30e814%40olegkutkov.me/',
        'https://lists.bufferbloat.net/starlink/f88f460e-97fe-764a-dd2a-87863798e30b%40olegkutkov.me/t/',
    ])
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for index, row in enumerate(pool.map(fetch, sorted(urls)), 1):
            rows.append(row)
            if index % 25 == 0:
                print(f'{index}/{len(urls)} linked resources processed', flush=True)
    (BASE / 'repositories.json').write_text(json.dumps(repositories, indent=2) + '\n')
    (BASE / 'additional-manifest.json').write_text(json.dumps(dict(
        forum_boards=sorted(pages), forum_pages=sorted(seen), resources=rows), indent=2) + '\n')
    print(f'Archived {len(seen)} forum pages; '
          f'{len(rows)} total additional resource attempts', flush=True)


if __name__ == '__main__':
    main()
