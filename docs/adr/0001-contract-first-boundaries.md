# ADR 0001: Contract-first component boundaries

Status: accepted

## Decision

Persisted and cross-component values use immutable, versioned contracts. Runtime
components communicate through narrow protocols. Implementations must not pass
private ORM models, construct another component's paths, or import another
component's internal implementation.

Pydantic models are the source for persisted JSON contracts. In-process IQ
arrays remain domain objects and are never embedded in those models.

## Consequences

- Acquisition, storage, analysis, catalog, presentation, API, and CLI can be
  implemented and tested against fakes independently.
- Published contracts require additive evolution or a new major version.
- Integration code performs explicit conversion at boundaries.

