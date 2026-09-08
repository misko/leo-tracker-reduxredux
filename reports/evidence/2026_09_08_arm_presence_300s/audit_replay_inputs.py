"""Read only the four frozen capture manifests through the storage port."""
from pathlib import Path
import json

from leo.storage.persistent_hop import PersistentHopIqStore
from tools.qualify_native_presence import digest, write_json

root=Path('/tmp/leo-presence-arm-profile.UuBXXp')
inputs=Path('/tmp/leo-native-presence-holdout-v1-20260908/inputs.json')
items=json.loads(inputs.read_text())
sessions={item['provenance']['session_id']:item['provenance']['manifest_sha256'] for item in items}
store=PersistentHopIqStore.open_read_only(Path('/srv/bulk/leo'))
rows=[]
for session,expected in sorted(sessions.items()):
    published=store.inspect(session)
    assert published.manifest_sha256==expected
    manifest=published.manifest
    receipt=manifest.receipt
    rows.append(dict(session_id=session,manifest_sha256=published.manifest_sha256,
        schema_version=manifest.schema_version,manifest_fields=list(type(manifest).model_fields),
        receipt_fields=list(type(receipt).model_fields),visit_fields=list(type(receipt.visits[0]).model_fields),
        chunk_fields=list(type(manifest.chunks[0]).model_fields),plan=manifest.plan.model_dump(mode='json'),
        timing=manifest.timing.model_dump(mode='json') if hasattr(manifest,'timing') else None,
        queue_telemetry=manifest.queue_telemetry.model_dump(mode='json') if manifest.queue_telemetry else None,
        visits=len(receipt.visits),chunks=len(manifest.chunks),qualified=receipt.qualified))
result=dict(recipe_sha256=digest(Path(__file__)),inputs_sha256=digest(inputs),rows=rows,
    conclusion='These stored manifests retain valid-IQ visit counters and aggregate queue/timing evidence, not each original IIO block or per-block host arrival timestamp. Reconstructed pacing must be labeled modeled, not original-arrival replay.',
    no_rf=True,archive_read_only=True)
write_json(root/'arrival-audit.json',result)
print(json.dumps(dict(sessions=len(rows),versions=[r['schema_version'] for r in rows],conclusion=result['conclusion']),indent=2))
