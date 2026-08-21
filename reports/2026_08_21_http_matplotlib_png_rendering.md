# HTTP-path Matplotlib PNG rendering investigation

Date: 2026-08-21
Scope: FastAPI request handling, Standard/Research PNG publication, disk caching,
and the operator UI call sites in `leo-tracker-reduxredux`.

> **Implementation update:** The on-demand HTTP rendering and presentation PNG
> cache described as the fallback in this investigation were removed on
> 2026-08-21. The Standard PNG endpoint now serves only registered analysis
> artifacts and returns 404 when an artifact was not published. The historical
> detail below records the behavior that motivated that change; it no longer
> describes the active request path.

## Executive conclusion

The API has exactly one route capable of invoking Matplotlib during an HTTP
request:

```text
GET or HEAD
/api/v2/recordings/{session_id}/standard-subjects/{subject_id}/views/{view_kind}.png
```

Even on that route, rendering is the third choice. The handler first tries a
registered immutable analysis artifact, then the local presentation cache, and
only renders after both miss. The current Standard pipeline pre-publishes the
three PNGs used by the operator UI—waterfall, GLRT64/pilot methods, and CFO
trajectories—at receiver-path, radio, and paired scopes. Consequently,
**on-demand Matplotlib rendering is not the expected production UI path for a
successfully completed current Standard run**. It is primarily a fallback for
older/incomplete runs, fixture repositories, or direct API requests for an
otherwise unregistered renderable view.

Research PNG routes, named Standard trajectory PNG routes, and investigation
PNG routes never render on request. They only read existing artifacts.

The fallback is scientifically bounded and has a durable content-addressed
cache, but it is not ideal as a high-concurrency request path. A cache-miss
render is CPU- and memory-intensive, all Matplotlib rendering within one
process is serialized by a global lock, simultaneous misses for the same key
can each render redundantly, and a `HEAD` request can perform the complete
render. The cache also has no retention policy.

No repository HTTP/render latency benchmark was found, and the production
presentation cache currently contains no top-level cached PNG files. There is
therefore no evidence that this fallback is a current operational bottleneck.

## Request decision tree

```text
Standard view PNG request
        |
        +-- view is power or quality? ----------------------> 404
        |
        +-- registered PNG matches subject and kind? ------> serve artifact
        |                                                     X-Leo-PNG-Cache: artifact
        |
        +-- immutable cache identity available?
        |       |
        |       +-- cached SHA-256 PNG exists? ------------> serve cached bytes
        |       |                                             X-Leo-PNG-Cache: hit
        |       |
        |       +-- no cached file
        |
        +-- build and verify bounded JSON view
        +-- optionally load full persisted presentation arrays
        +-- render with Matplotlib/Agg
        +-- publish to disk cache when identity exists
        +-- serve bytes ------------------------------------> X-Leo-PNG-Cache: miss
```

## HTTP routes and whether they render

| Route family | Source returned | HTTP-time Matplotlib possible? | Cache header |
|---|---|---:|---|
| `/standard-subjects/.../views/{view}.png` | Registered artifact, disk-cache entry, or fallback render | **Yes**, only after artifact and cache miss | `artifact`, `hit`, or `miss` |
| `/standard-subjects/.../artifacts/{name}.png` | Registered raw/de-aliased/final/alternate CFO artifact | No | `artifact` |
| `/standard-investigations/{image}.png` | Existing investigation file | No | `investigation-artifact` |
| `/research-subjects/.../views/{view}.png` | Registered Research artifact | No; missing artifact returns 404 | `artifact` |
| `/research-subjects/.../artifacts/{name}.png` | Registered Research artifact | No | `artifact` |

The only rendering handler is `standard_subject_view_png` in
`src/leo/api/app.py`. Its exact order is:

1. Reject `power` and `quality` PNG requests.
2. Call `subject_png_artifact`; return immediately when a registered artifact
   exists.
3. Obtain an immutable `subject_png_cache_identity`, combine it with renderer
   version `standard-png-renderer-v3`, `include_test`, and `maximum_points`, and
   SHA-256 hash that material.
4. Read `{bulk_root}/presentation-cache/{digest}.png`; return on a hit.
5. Build the bounded public view and verify its source-extrema proof and subject
   binding.
6. For GLRT64, also build and verify the CFO companion view.
7. Ask the production repository for full persisted presentation arrays.
8. Render the full source when available, otherwise render the bounded view.
9. Publish the result into the disk cache when an immutable identity exists.
10. Return the PNG as an in-memory `Response`.

## What normally prevents on-demand rendering

The Standard analyzers publish these immutable PNG products during analysis:

| Public view | Registered product | Produced during analysis? | Displayed by current UI? |
|---|---|---:|---:|
| Waterfall | `standard.waterfall-png/v1` | Yes | Yes, eager-loaded |
| GLRT64 / pilot-method comparison | `standard.pilot-methods-png/v1` | Yes | Yes, lazy-loaded unless used in the investigation comparison |
| CFO trajectory | `standard.cfo-trajectories-png/v1` | Yes | Yes, lazy-loaded |
| QAM | No dedicated registered PNG product | No | No; the current `galleryOrder` excludes QAM |
| Power | None | No; HTTP PNG explicitly rejected | No |
| Quality | None | No; HTTP PNG explicitly rejected | No |

`_publish_pngs` also produces de-aliased and final CFO trajectory images. The
pipeline calls `_publish_pngs` for receiver paths, radios, and paired subjects.
The frontend gallery requests only waterfall, GLRT64, and CFO trajectory views,
so a current sealed Standard run should take the registered-artifact branch for
every main gallery image.

QAM is the clearest reachable fallback case: it is accepted by the renderer and
the production repository can supply its full source, but no QAM PNG product is
registered and the current UI does not request it. A direct API caller can
therefore cause QAM rendering and caching.

Older runs or runs lacking the newer presentation PNG products can also enter
the fallback, provided their persisted presentation documents remain readable
and a valid sealed-run cache identity can be constructed.

## Renderer behavior and cost characteristics

`src/leo/presentation/standard_png.py` uses the non-interactive Agg backend and
constructs `Figure` objects directly. It does not use a GUI backend or global
`pyplot` state. That is the correct server-side Matplotlib pattern.

All render entry points share one process-global `RLock`:

- `render_standard_plot_png`
- `render_full_standard_plot_png`
- `render_full_cfo_stage_png`

This protects Matplotlib operations but means only one of these renders can run
at a time in a Uvicorn process. Since the API currently runs one Uvicorn
process, one slow cache-miss render serializes every other render miss. Ordinary
JSON and artifact requests can still run in FastAPI's worker threads, subject
to CPU and memory contention.

Full figures are intentionally publication-sized. Depending on view and path
count they use roughly 15-inch-wide canvases at 120–160 DPI, multiple axes,
scatter plots, rasterized evidence, legends, constrained layout, and PNG
compression. The in-memory working set is substantially larger than the final
PNG because Matplotlib retains arrays, artists, and an RGBA canvas while
encoding. The route then retains the encoded PNG bytes for the response and may
write/fsync the same bytes to the disk cache.

The full-source path is not bounded by the `maximum_points` query value. That
limit controls the verified public JSON view built before rendering, while
`subject_png_source` supplies the persisted full presentation arrays. This is
intentional for publication-quality figures, but it means `maximum_points`
does not bound the principal render cost when the production repository is in
use.

## Disk-cache design

`StandardPngDiskCache` stores immutable files beneath:

```text
{bulk_root}/presentation-cache/{sha256}.png
```

Positive properties:

- refuses relative/QNAP-backed roots;
- validates a lowercase SHA-256 key;
- rejects symlinks, non-regular files, multi-link cache files, empty files, and
  files over 32 MiB;
- validates the PNG signature;
- publishes through an exclusive temporary file and atomic hard link;
- fsyncs both file and directory;
- never overwrites an existing immutable cache entry;
- binds the key to the sealed run, manifest digest, pipeline release, subject,
  view kind, renderer version, and request parameters.

Operational limitations:

1. **No single-flight suppression.** Concurrent requests can all observe a
   miss before acquiring the renderer lock. They then render the same key one
   after another. Publication is race-safe, but redundant rendering is not
   prevented.
2. **Process-local render lock.** Multiple future Uvicorn workers would each
   have a lock, so they could render concurrently and multiply peak memory/CPU.
   The disk publish remains create-once, but duplicate work still occurs.
3. **No eviction or retention.** Cache keys change with runs, releases,
   renderer versions, `include_test`, and `maximum_points`; files accumulate
   indefinitely.
4. **Whole-file reads.** Cache hits and artifacts are loaded into Python bytes
   and returned as a normal `Response`; they are not streamed or served through
   `FileResponse`/kernel sendfile.
5. **Potentially redundant variants.** `maximum_points` is included in the
   cache key even when the full-source renderer produces content independent of
   that value. `include_test` is also keyed although it normally gates
   visibility rather than figure pixels. Direct callers can create distinct
   cache entries for equivalent full-source images.
6. **Cold cache after renderer changes.** The hard-coded renderer version is
   deliberately part of the key, so a version increment invalidates every
   fallback render at once.

The inspected host's `/srv/bulk/leo/presentation-cache` was approximately 12 KiB
and had no top-level `*.png` cache entries at investigation time. This is
consistent with registered artifacts satisfying normal production requests,
although it is only a point-in-time observation of this host.

## HEAD behavior

The render-capable route explicitly registers both `GET` and `HEAD` against the
same handler. There is no HEAD-specific short circuit. On an artifact/cache
miss, a HEAD request therefore performs source loading, verification,
Matplotlib rendering, optional fsync publication, and response construction
even though the response body is discarded by HTTP semantics.

This is observable in the tests, which issue HEAD requests to PNG routes. It is
not dangerous under ordinary UI behavior—the browser uses GET—but health
checks, crawlers, or probing clients could unexpectedly warm the cache at full
render cost.

## Concurrency failure mode

For N simultaneous requests for the same uncached PNG in the current
single-process deployment:

1. All N can miss the disk cache.
2. The first enters `_RENDER_LOCK` and renders.
3. The remaining N-1 wait on the lock.
4. After the first publishes, each waiter enters the renderer in turn without
   rechecking the cache and redundantly renders the same figure.
5. Each later `publish` discovers the existing immutable cache file and returns
   its bytes.

Thus publication is correct and deterministic, but cold-miss latency can grow
approximately serially with the number of simultaneous requests. Adding HTTP
workers would change this from serialized duplicate work to parallel duplicate
work, increasing peak resource contention rather than eliminating it.

## Tests and evidence coverage

Existing tests establish:

- deterministic valid PNG generation and bounded response sizes for fixture
  views;
- registered production artifacts take precedence and report
  `X-Leo-PNG-Cache: artifact`;
- a fallback render is cached and the next request reports
  `X-Leo-PNG-Cache: hit`;
- cache publication is create-once;
- invalid keys, invalid PNG bytes, and QNAP roots are rejected;
- expected production figure dimensions;
- `power` and `quality` PNGs return 404.

Not currently covered:

- concurrent same-key cache misses;
- concurrent different-key renders;
- multiple server processes sharing the cache;
- HEAD behavior on a cold miss;
- cache retention/cleanup;
- latency, CPU time, peak RSS, or response-size distributions on the real radio
  corpus;
- behavior at the 32 MiB cache limit;
- equivalent cache variants caused by different `maximum_points` values;
- browser/client caching behavior over repeated page navigation.

No source files were changed and no golden scientific fixture was regenerated
as part of this investigation.

## Risk assessment

| Risk | Current likelihood | Impact if fallback becomes common | Assessment |
|---|---:|---:|---|
| Normal UI triggers Matplotlib | Low for current sealed Standard runs | Medium | Pre-published artifacts cover the three displayed views |
| Legacy/incomplete run triggers fallback | Plausible | Medium | Depends on retained presentation documents and artifact history |
| Direct QAM PNG request triggers render | Plausible but UI does not do it | Medium | Reachable public API path |
| Same-key request stampede | Low at current operator count | High latency | Correct output, redundant serialized work |
| Multiple-worker resource spike | Not applicable today | High | Relevant before increasing Uvicorn workers |
| Unbounded cache growth | Low today | Medium over time | No PNG entries observed, but no pruning exists |
| HEAD unexpectedly renders | Low | Medium | Easy for probes to trigger |
| HTTP server is the bottleneck | No evidence | Low | Rendering and artifact work dominate this path |

## Recommendations

### Immediate: document and measure, no infrastructure replacement

Keep Uvicorn and the artifact-first design. Before changing behavior, add
request metrics or structured access-log fields for:

- `X-Leo-PNG-Cache` state (`artifact`, `hit`, `miss`);
- total handler latency;
- rendered view kind and subject kind;
- rendered PNG byte size;
- render duration separately from source loading and cache publication.

The first production question is simply whether any `miss` responses occur.
If they do not, this path is not an operational performance concern.

### Small correctness/performance hardening

1. Add a per-key single-flight mechanism, or recheck the cache after acquiring
   a per-key render lock. This prevents a cold page load or multiple clients
   from rendering the same image repeatedly.
2. Give HEAD a cheap policy. It can serve metadata for existing artifacts/cache
   entries, return the same availability result without fallback generation,
   or explicitly document that HEAD warms the cache. It should not silently do
   full scientific rendering merely to discard the body.
3. Canonicalize cache inputs for full-source rendering. If output does not
   depend on `maximum_points` or `include_test`, omit those values from the
   full-source cache key. Preserve them for bounded-view rendering where they
   can affect pixels.
4. Define a bounded cache-retention policy before fallback use grows. Cleanup
   must remain confined to local `presentation-cache`; it must never touch
   `/mnt/qnap01` or registered analysis artifacts.

### Prefer analysis-time publication

If QAM PNG becomes visible in the UI, add it as a registered analysis product
and publish it with the other Standard images rather than making routine page
views generate it. This preserves the repository's existing model: expensive
scientific presentation work belongs to the analysis graph, while HTTP serves
verified immutable products.

For older runs, a bounded reprocessing/backfill operation is preferable to
per-request generation when operators need the images repeatedly. It produces
auditable registered artifacts and avoids cold HTTP latency.

### Only then optimize byte serving

If measurements show artifact delivery itself is significant, consider a
resolver capable of returning a verified local path and use `FileResponse` or a
reverse proxy for immutable PNG bytes. That would reduce Python copies and
enable efficient range/sendfile behavior. It is a secondary optimization: it
does not address Matplotlib render cost and should not weaken digest validation
or expose constructed storage paths.

Do not add Uvicorn workers solely to improve this route. First remove duplicate
rendering and measure peak memory on representative full-resolution figures.
Workers can increase throughput for ordinary requests, but concurrent
Matplotlib renders may compete with radio analysis and acquisition—the
repository intentionally gives the API lower CPU/I/O priority.

## Code map

| Responsibility | Location |
|---|---|
| Render-capable HTTP handler and artifact/cache/render ordering | `src/leo/api/app.py:559-626` |
| PNG response headers | `src/leo/api/app.py:628-644` |
| Named Standard artifact-only routes | `src/leo/api/app.py:646-679` |
| Investigation artifact-only route | `src/leo/api/app.py:703-727` |
| Research artifact-only routes | `src/leo/api/app.py:888-950` |
| Disk cache implementation | `src/leo/api/png_cache.py` |
| Matplotlib/Agg renderer and global lock | `src/leo/presentation/standard_png.py:12-123` |
| PNG encoding | `src/leo/presentation/standard_png.py:830-839` |
| Production artifact lookup and full-source assembly | `src/leo/application/standard_presentation.py:852-918` |
| Immutable cache identity | `src/leo/application/standard_presentation.py:997-1025` |
| Analysis-time PNG publication | `src/leo/analysis/standard/analyzers.py:712-732` |
| Receiver-path, radio, and paired publication call sites | `src/leo/analysis/standard/analyzers.py:825-832, 874-906, 1040-1051` |
| Registered PNG product definitions | `src/leo/analysis/standard/products.py:84-120` |
| Browser PNG URL construction | `web/src/standard-api.ts:113-125` |
| Browser gallery and loading policy | `web/src/StandardAnalysis.tsx:25-29, 407-471` |
| Cache tests | `tests/api/test_png_cache.py` |
| API render/cache tests | `tests/api/test_standard_pipeline_api.py:387-427` and `tests/application/test_standard_presentation_production.py:220-308` |
| Production cache/font configuration | `deploy/systemd/leo-api.service:13,28` |

## Bottom line

The original concern should be stated precisely:

> The API contains an on-demand Matplotlib fallback for Standard view PNGs, but
> the current production pipeline pre-publishes every PNG used by the main UI.
> Normal successful-run browsing should serve immutable artifacts, not render.

That fallback is reasonable for compatibility and recovery at low operator
concurrency. It should not become the normal presentation architecture. If
observability shows real cache misses, the priority order is: identify why the
registered artifact was absent, prevent duplicate/HEAD renders, publish any new
UI figure during analysis, and only afterward consider HTTP-worker or server
changes.
