"""Generate a compact per-object index of reproducible local atlas artifacts."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def run():
    summary = json.loads((BASE / 'local/catalog/summary.json').read_text())
    corpus = json.loads((BASE / 'local/corpus.json').read_text())
    locations = {r['sha256']: r['locations'] for r in corpus['objects']}
    lines = ['# Executable inventory', '',
             'Counts are candidate entries, not fully reverse-engineered functions. '
             'Artifacts live in ignored local storage; regenerate using README commands.', '',
             '| Object | Entries | Metadata-supported | Direct call sites | Artifacts |',
             '|---|---:|---:|---:|---|']
    for row in summary['binaries']:
        def link(key, row=row):
            path = Path(row[key])
            if not path.is_absolute():
                path = BASE.parents[3] / path
            return f'[{key}]({path.resolve().relative_to(BASE)})'
        artifacts = ' · '.join(link(key) for key in ('functions', 'calls', 'disassembly')
                               if row.get(key))
        lines.append(f"| {Path(row['path']).name} | {row['function_entries']:,} | "
                     f"{row['metadata_supported_entries']:,} | "
                     f"{row['direct_call_sites']:,} | {artifacts} |")
    lines += ['', '## Archive locations and aliases', '']
    for row in summary['binaries']:
        lines.append(f"- `{Path(row['path']).name}`: " + ', '.join(
            f"`{loc['family']}:{loc['path']}`" for loc in locations[row['sha256']]))
    lines += ['', 'Aliases below are archive links, not separately disassembled executables.', '']
    for alias in corpus['aliases']:
        lines.append(f"- `{alias['family']}:{alias['path']}` → `{alias['target']}`")
    (BASE / 'INVENTORY.md').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    run()
