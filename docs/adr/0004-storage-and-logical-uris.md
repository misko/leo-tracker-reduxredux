# ADR 0004: Local bulk storage and logical URIs

Status: accepted

## Decision

The canonical data root is `/srv/bulk/leo`. Raw IQ and large analysis products
live there; PostgreSQL stores searchable lifecycle state and logical references.
Catalog references use `bulk://` URIs resolved by the storage component so the
mount can be relocated without changing scientific records.

`/mnt/qnap01` is a read-only import source. No retention or general storage
resolver may produce it as a deletion target.

