"""Additive manifest-authoritative topology for Standard-native-v1."""

from __future__ import annotations

from leo.contracts.digests import canonical_digest
from leo.contracts.mixed_rate_schedule import (
    ProductionDwellClassV2,
    ProductionDwellClassV3,
)
from leo.contracts.pipeline_lanes import PipelineDefinitionV1, PipelineLane
from leo.contracts.recording import (
    RecordingManifestV3,
    RecordingManifestV5,
    RecordingManifestV6,
)
from leo.contracts.standard_pipeline import resolve_manifest_starlink_tuning
from leo.contracts.starlink_frequency import (
    starlink_maximum_coverage_if_center_frequency_hz,
)
from leo.contracts.states import GainMode, SourceType
from leo.pipeline.contracts import ResourceClass
from leo.pipeline.planning import ExpandedRunPlanV1, IqAccess, JobDependencyRefV1, JobNodeV1
from leo.pipeline.scopes import ScopeIdentityV1
from leo.pipeline.topology import CompiledScopeInventory

STANDARD_NATIVE_SAMPLE_RATES_HZ = (
    2_500_000,
    3_000_000,
    5_000_000,
    10_000_000,
    15_000_000,
    20_000_000,
    25_000_000,
)
STANDARD_NATIVE_PROFILE_RATE_HZ = {
    "starlink-ch4-lower-2p5m-60s-device-axis-v3": 2_500_000,
    "starlink-ch4-lower-3m-60s-device-axis-v3": 3_000_000,
    "starlink-ch4-lower-5m-60s-device-axis-v3": 5_000_000,
    "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4": 2_500_000,
    "starlink-ch4-lower-3m-60s-native-bandwidth-v4": 3_000_000,
    "starlink-ch4-lower-5m-60s-native-bandwidth-v4": 5_000_000,
    "starlink-ch4-lower-10m-60s-native-bandwidth-v4": 10_000_000,
}
STANDARD_NATIVE_PROFILE_REVISION_DIGESTS = {
    "starlink-ch4-lower-2p5m-60s-device-axis-v3": (
        "sha256:b30f80c13c8003ebf57f5530bcca73e3928102597f8fb6342618f4820ab91101"
    ),
    "starlink-ch4-lower-3m-60s-device-axis-v3": (
        "sha256:4533ac4a3348721e0bf7bda50c5701f505e47ef579ef9a47cbc7c38b9c9b4c3e"
    ),
    "starlink-ch4-lower-5m-60s-device-axis-v3": (
        "sha256:8851c20e4c6e79bc5d4cb92f8fd0e09eaf24e59b742239b92bc248fd4d09ba5d"
    ),
    "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4": (
        "sha256:140d4f834fd27b94754ea9017f2be45da21af2662dfef8ec97c4487fbf15bc89"
    ),
    "starlink-ch4-lower-3m-60s-native-bandwidth-v4": (
        "sha256:523402d005564d97177ee139f1a616c01b6b65d9a6c4ad11a0564c074216865c"
    ),
    "starlink-ch4-lower-5m-60s-native-bandwidth-v4": (
        "sha256:6f8ec4a5dec0f6b18d09c0f464c22c143ac363f2088242db830b0757a6316294"
    ),
    "starlink-ch4-lower-10m-60s-native-bandwidth-v4": (
        "sha256:3b4a970db3c891f4327a2c5713e5deaf1161429d5a9ce5c2f0d597e7808205ce"
    ),
}
STANDARD_NATIVE_MIXED_PROFILE_REVISION_DIGESTS = {
    2_500_000: "sha256:e5f088ba153a893eb5f5324c6c411ebe189acc9de5bfa68211a841edc9bbdb44",
    5_000_000: "sha256:e5d593c1711ddb65be6adeb2f3fe620afe99948aed2881dabc142b5737e81afc",
    10_000_000: "sha256:c3062bf57769d14682206855c8d4b8ec011aa1a005e411252ea4234291216d63",
}
STANDARD_NATIVE_MIXED_REFILL_SAMPLES = 1_048_576
STANDARD_NATIVE_MIXED_KERNEL_BUFFERS = 4
STANDARD_NATIVE_MIXED_QUEUE_CAPACITY = 32
STANDARD_NATIVE_MIXED_PROFILE_NAMES = {
    2_500_000: "starlink-ch4-lower-2p5m-60s-mixed-device-axis-v4",
    5_000_000: "starlink-ch4-lower-5m-60s-mixed-device-axis-v4",
    10_000_000: "starlink-ch4-lower-10m-60s-mixed-device-axis-v4",
}
STANDARD_NATIVE_PRODUCTION_PROFILE_IDENTITIES = {
    "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4": (
        2_500_000,
        (0, 1),
        "sha256:140d4f834fd27b94754ea9017f2be45da21af2662dfef8ec97c4487fbf15bc89",
        1_048_576,
    ),
    "starlink-ch4-lower-5m-60s-native-bandwidth-v4": (
        5_000_000,
        (0, 1),
        "sha256:6f8ec4a5dec0f6b18d09c0f464c22c143ac363f2088242db830b0757a6316294",
        1_048_576,
    ),
    "starlink-ch4-lower-2p5m-60s-mixed-device-axis-v4": (
        2_500_000,
        (0, 1),
        "sha256:e5f088ba153a893eb5f5324c6c411ebe189acc9de5bfa68211a841edc9bbdb44",
        1_048_576,
    ),
    "starlink-ch4-lower-5m-60s-mixed-device-axis-v4": (
        5_000_000,
        (0, 1),
        "sha256:e5d593c1711ddb65be6adeb2f3fe620afe99948aed2881dabc142b5737e81afc",
        1_048_576,
    ),
    "starlink-ch4-lower-10m-60s-rx0-production-v5": (
        10_000_000,
        (0,),
        "sha256:5f58b6a4afaf77649f389eaf2e167af53d61e851ca294c5d7622b495fa24bf0e",
        1_048_576,
    ),
    "starlink-ch4-lower-10m-60s-rx1-production-v5": (
        10_000_000,
        (1,),
        "sha256:446a7d5637f3e1bc8a8fe62ecb8f7b4ad6eeac2ece367d9e022ae0b4cc12ba1f",
        1_048_576,
    ),
    "starlink-ch4-lower-15m-60s-rx0-production-v5": (
        15_000_000,
        (0,),
        "sha256:9336da0d5cc00d006a80e35180812d7ad8cf09ca7f590f0b03b7786b259583ba",
        1_048_576,
    ),
    "starlink-ch4-lower-15m-60s-rx1-production-v5": (
        15_000_000,
        (1,),
        "sha256:b69997f7ad37b484d22dd21dab95c31ea74af67e7909142a21c94cbf1df174e8",
        1_048_576,
    ),
    "starlink-ch4-lower-20m-60s-rx0-production-v5": (
        20_000_000,
        (0,),
        "sha256:9c9b4e34515f536bcb01751650a7e8c396d2f03f4ae979f6451f6b9d9fe1f0a1",
        1_048_576,
    ),
    "starlink-ch4-lower-20m-60s-rx1-production-v5": (
        20_000_000,
        (1,),
        "sha256:5fad84a88fe487a812598fd3de2697aef443ee14b8b64eefc253256dd9006410",
        1_048_576,
    ),
    "starlink-ch4-lower-10m-60s-rx0-ddr-ring-v6": (
        10_000_000,
        (0,),
        "sha256:4c9fcc3fe27af3a6f9341c0ac42beb9f6e135731541114f9a7cb15b95d9e71f4",
        1_000_000,
    ),
    "starlink-ch4-lower-10m-60s-rx1-ddr-ring-v6": (
        10_000_000,
        (1,),
        "sha256:9fce2e136b1f1e002282520d7ce4f2df60afd9e2dcff8db0586a388b976f0b43",
        1_000_000,
    ),
    "starlink-ch4-lower-15m-60s-rx0-ddr-ring-v6": (
        15_000_000,
        (0,),
        "sha256:2dab9044d0b11f4f3af57882e90d248bbafcda684a68182f00fef686aa58cb63",
        1_000_000,
    ),
    "starlink-ch4-lower-15m-60s-rx1-ddr-ring-v6": (
        15_000_000,
        (1,),
        "sha256:17335b014966a45505d46e94bb754ce13f11f52498fa0a2ddfabed07f41ec320",
        1_000_000,
    ),
    "starlink-ch4-lower-20m-60s-rx0-ddr-ring-v6": (
        20_000_000,
        (0,),
        "sha256:3131e4776d9dd6bc9a986adbdce35d6cb431dcfb31178fff1ef9aa285c11cc5a",
        1_000_000,
    ),
    "starlink-ch4-lower-20m-60s-rx1-ddr-ring-v6": (
        20_000_000,
        (1,),
        "sha256:baf767d6a04a183283b606874042138969939d3064e7840b773b1394be7df88a",
        1_000_000,
    ),
}
STANDARD_NATIVE_DIRECT_ASYNC_PROFILE_IDENTITIES = {
    "starlink-ch4-lower-10m-60s-rx0-direct-async-v7": (
        10_000_000,
        (0,),
        "sha256:22172543ea6139b98eed978a2c994f8384932a2f88dc3135e6ef7e560074aa59",
    ),
    "starlink-ch4-lower-10m-60s-rx1-direct-async-v7": (
        10_000_000,
        (1,),
        "sha256:34dd3ea083b62305ecdbc8a9a3563b91bef0e0d37cf598e4168a9217098cef83",
    ),
    "starlink-ch4-lower-15m-60s-rx0-direct-async-v7": (
        15_000_000,
        (0,),
        "sha256:7786970fe19bc5f75da2f3bf61219716d306fe69d3e3403b89fa080b2eb07bfd",
    ),
    "starlink-ch4-lower-15m-60s-rx1-direct-async-v7": (
        15_000_000,
        (1,),
        "sha256:cdb3734d0bdab0e741e9d855998ee6c5c735fbc1d4b7034b5b4e81340ad33cc2",
    ),
    "starlink-ch4-lower-25m-60s-rx0-direct-async-v7": (
        25_000_000,
        (0,),
        "sha256:17794a88d89b35149fe6976b1de8344b5c58d0e52393c69e027d6759b9ee369e",
    ),
    "starlink-ch4-lower-25m-60s-rx1-direct-async-v7": (
        25_000_000,
        (1,),
        "sha256:6675fbf3d6e6899a2c0fec29b078181a7f843df1cb8941906ab11ac3c7f7adb9",
    ),
    "starlink-ch4-lower-25m-60s-rx0-direct-async-v8": (
        25_000_000,
        (0,),
        "sha256:91ee768cb8d96ae7c6e0462c91585847e504db1c9e66a96ceec08469d13d2a18",
    ),
    "starlink-ch4-lower-25m-60s-rx1-direct-async-v8": (
        25_000_000,
        (1,),
        "sha256:2f08108db6f9ed5c8e9b259c23ecb1c9b11376a72f2c1ff234c152b8efe84db4",
    ),
    "starlink-ch4-lower-10m-60s-rx0-direct-async-ram-drop-v9": (
        10_000_000,
        (0,),
        "sha256:741353a4f21fbcf798ebfbc292ce8f3de3645f518ef8a7f5e0121fc7c1f07875",
    ),
    "starlink-ch4-lower-10m-60s-rx1-direct-async-ram-drop-v9": (
        10_000_000,
        (1,),
        "sha256:306fac2fbf58e9978cdc39a2314e15f1d00394e4c85ba558df7cac364de68271",
    ),
    "starlink-ch4-lower-15m-60s-rx0-direct-async-ram-drop-v9": (
        15_000_000,
        (0,),
        "sha256:96543d27db022bcc4c179f61a4028ef2209684632ee9add021f2060fc8b9bde6",
    ),
    "starlink-ch4-lower-15m-60s-rx1-direct-async-ram-drop-v9": (
        15_000_000,
        (1,),
        "sha256:129e4ba840adace7eb3648228f966ef08ef160a042fd6b622cb99f8bb75f0aab",
    ),
    "starlink-ch4-lower-20m-60s-rx0-direct-async-ram-drop-v9": (
        20_000_000,
        (0,),
        "sha256:cd8aa94677162329df799712f55483df082ab457fe94b782e9f91141cc47d696",
    ),
    "starlink-ch4-lower-20m-60s-rx1-direct-async-ram-drop-v9": (
        20_000_000,
        (1,),
        "sha256:a3eca7b5bde9f0dbf007bbd006222dd45818ef1563fdf5eb53def323a28d0e68",
    ),
    "starlink-ch4-lower-25m-60s-rx0-direct-async-ram-drop-v9": (
        25_000_000,
        (0,),
        "sha256:c6dae16bb7bbbb27305c91fa4426cde27b4d712b97694d4cac680972bcf86cc6",
    ),
    "starlink-ch4-lower-25m-60s-rx1-direct-async-ram-drop-v9": (
        25_000_000,
        (1,),
        "sha256:117a77ac1250f86a11bee00df8653b26c9747250d6aa54cad2d42be1595d071e",
    ),
    "starlink-ch4-lower-10m-60s-rx0-direct-async-ram-drop-v10": (
        10_000_000,
        (0,),
        "sha256:335ba1585253ec1f2357626b16f2f32cbc5368cc1c082c8220fbd283ed1ef9bd",
    ),
    "starlink-ch4-lower-10m-60s-rx1-direct-async-ram-drop-v10": (
        10_000_000,
        (1,),
        "sha256:81de78394131fe6904f7a1b6b9d4a4900bdb477464376563364782a12ed86ef4",
    ),
    "starlink-ch4-lower-15m-60s-rx0-direct-async-ram-drop-v10": (
        15_000_000,
        (0,),
        "sha256:49c51b945f9c7c2a80b4f5e32f103cff694056736bb41047075188748f33539d",
    ),
    "starlink-ch4-lower-15m-60s-rx1-direct-async-ram-drop-v10": (
        15_000_000,
        (1,),
        "sha256:69a5ad262cece68ab4a44266dd44f9cc1c7648ea18ce331ed1ab02263ab28165",
    ),
    "starlink-ch4-lower-20m-60s-rx0-direct-async-ram-drop-v10": (
        20_000_000,
        (0,),
        "sha256:077f8254cd91ebe6642b9513bd8a51150c55bac0ab1f7101175bfcb66fd83d59",
    ),
    "starlink-ch4-lower-20m-60s-rx1-direct-async-ram-drop-v10": (
        20_000_000,
        (1,),
        "sha256:364fafc64c73412dcd1e95f523ac77b4943a6430f7a0e958532e32219772c54e",
    ),
    "starlink-ch4-lower-25m-60s-rx0-direct-async-ram-drop-v10": (
        25_000_000,
        (0,),
        "sha256:faf2ad1ab3153c15228ec9332f3bff3bead7c615668ddf784fff757657f88eaf",
    ),
    "starlink-ch4-lower-25m-60s-rx1-direct-async-ram-drop-v10": (
        25_000_000,
        (1,),
        "sha256:722ee701893e402822f33e1802b3d984005d9c3ee7b1cd882f8f9c23f5962292",
    ),
    "starlink-ch4-lower-20m-60s-rx0-direct-async-ram-drop-v11": (
        20_000_000,
        (0,),
        "sha256:544e77f9bfe1a3f2b37de07f838833089b1022852cd1f257f09e0dc7c911767b",
    ),
    "starlink-ch4-lower-20m-60s-rx1-direct-async-ram-drop-v11": (
        20_000_000,
        (1,),
        "sha256:f8399cd80ab8b8379139d44190142dc9c62b82b4e0a24750c9b822a54fb3d7b0",
    ),
    "starlink-ch4-lower-25m-60s-rx0-direct-async-ram-drop-v11": (
        25_000_000,
        (0,),
        "sha256:da020908350e8b96b38ce1b5957b26b7f0ab73bdf0d6a204073c69f1bd64f894",
    ),
    "starlink-ch4-lower-25m-60s-rx1-direct-async-ram-drop-v11": (
        25_000_000,
        (1,),
        "sha256:4710ba1fec16ac0d0841de5115fa53432cbb3a57653cc85516829cd48757e1d0",
    ),
    "starlink-ch4-lower-10m-60s-rx0-direct-async-exact-dma-drop-v12": (
        10_000_000,
        (0,),
        "sha256:b08edacbbfafcfd525e9320c2a582503751d851a8bb5b8c2a58cf3997ff132ce",
    ),
    "starlink-ch4-lower-10m-60s-rx1-direct-async-exact-dma-drop-v12": (
        10_000_000,
        (1,),
        "sha256:29dadfed53366653b5666d077ffb30be6b268479b191117487499072592644dc",
    ),
    "starlink-ch4-lower-15m-60s-rx0-direct-async-exact-dma-drop-v12": (
        15_000_000,
        (0,),
        "sha256:6e012fad806cec955929521e992a87b88b4fa0624fb501cbb4a9a0574ae3a860",
    ),
    "starlink-ch4-lower-15m-60s-rx1-direct-async-exact-dma-drop-v12": (
        15_000_000,
        (1,),
        "sha256:8b92ea68da761389ff0ae64844f85af3f7c2e6c4c5245627d79cb52e261cd30c",
    ),
    "starlink-ch4-lower-20m-60s-rx0-direct-async-exact-dma-drop-v12": (
        20_000_000,
        (0,),
        "sha256:0fe7aec03eb65de32693327f29527a6f6342ee93a875169324ef9cfa2fa670a6",
    ),
    "starlink-ch4-lower-20m-60s-rx1-direct-async-exact-dma-drop-v12": (
        20_000_000,
        (1,),
        "sha256:4874ed78ffaac7424158f021d87f13730817ffc23427e215d2279279d4281a43",
    ),
    "starlink-ch4-lower-25m-60s-rx0-direct-async-exact-dma-drop-v12": (
        25_000_000,
        (0,),
        "sha256:d833e8c4ba727db490eb1a33cb8290508ff705dd921bf96c816048ae77d91927",
    ),
    "starlink-ch4-lower-25m-60s-rx1-direct-async-exact-dma-drop-v12": (
        25_000_000,
        (1,),
        "sha256:1e631a4adbc892e9fb2d610c795953d22db8cbb15485767785b23fdaa9b4c64e",
    ),
}


STANDARD_NATIVE_STAGE_KEYS = (
    "path-standard-native",
    "path-pss-native",
    "path-alternate-tracks-native",
    "radio-scientific-report-native",
    "paired-scientific-report-native",
    "paired-presentation-native",
    "paired-pss-glrt-presentation-native",
)


def standard_native_pipeline_definition_v1(
    *,
    executable_git_sha: str,
    graph_digest: str,
    configuration_digest: str,
) -> PipelineDefinitionV1:
    """Build the pure promotable definition for the reviewed native graph.

    The release authority supplies the immutable executable, graph, and
    configuration identities.  The expanded run plan independently binds the
    manifest-derived topology for one capture.
    """

    values = {
        "schema_version": 1,
        "lane": PipelineLane.STANDARD,
        "executable_git_sha": executable_git_sha,
        "graph_digest": graph_digest,
        "configuration_digest": configuration_digest,
        "product_namespace": "standard",
        "automatic_eligible": True,
        "promotion_allowed": True,
    }
    return PipelineDefinitionV1(
        lane=PipelineLane.STANDARD,
        executable_git_sha=executable_git_sha,
        graph_digest=graph_digest,
        configuration_digest=configuration_digest,
        product_namespace="standard",
        automatic_eligible=True,
        promotion_allowed=True,
        definition_id=canonical_digest(values),
    )


def compile_standard_native_run_plan(
    manifest: RecordingManifestV3 | RecordingManifestV5 | RecordingManifestV6,
    *,
    manifest_digest: str,
    pipeline_release_id: str,
) -> ExpandedRunPlanV1:
    """Expand the disjoint Standard-native graph without changing Standard-v2.

    This pure compiler closes reviewed native-rate/profile geometry and
    produces a stage inventory that cannot be mistaken for the frozen Standard
    graph. Promotion policy remains the run coordinator's responsibility.
    """

    _require_reviewed_native_geometry(manifest)
    rates = {
        (stream.applied_settings or stream.requested_settings).sample_rate_hz
        for stream in manifest.streams
    }
    return _compile_standard_native_run_plan(
        manifest,
        manifest_digest=manifest_digest,
        pipeline_release_id=pipeline_release_id,
        standard_stream_ids=None,
        pss_stream_ids=None,
        include_pss_glrt_comparison=(rates == {2_500_000, 25_000_000}),
    )


def compile_standard_native_default_run_plan(
    manifest: RecordingManifestV3 | RecordingManifestV5 | RecordingManifestV6,
    *,
    manifest_digest: str,
    pipeline_release_id: str,
) -> ExpandedRunPlanV1:
    """Compile the production default while retaining explicit all-rate analysis.

    Exact paired 2.5/25 MS/s captures run Standard GLRT/stateful analysis only
    on the 2.5 MS/s paths and native PSS only on the 25 MS/s paths.  Other
    reviewed native geometries retain the complete all-rate graph compiled by
    :func:`compile_standard_native_run_plan`.
    """

    _require_reviewed_native_geometry(manifest)
    rates = {
        (stream.applied_settings or stream.requested_settings).sample_rate_hz
        for stream in manifest.streams
    }
    compiler = (
        compile_standard_native_automatic_run_plan
        if rates == {2_500_000, 25_000_000}
        else compile_standard_native_run_plan
    )
    return compiler(
        manifest,
        manifest_digest=manifest_digest,
        pipeline_release_id=pipeline_release_id,
    )


def compile_standard_native_automatic_run_plan(
    manifest: RecordingManifestV3 | RecordingManifestV5 | RecordingManifestV6,
    *,
    manifest_digest: str,
    pipeline_release_id: str,
) -> ExpandedRunPlanV1:
    """Compile low-rate GLRT plus isolated native-25 PSS for paired captures.

    The full Standard path remains confined to 2.5 MS/s.  A co-captured
    25 MS/s leg enters the dedicated PSS module and paired comparison without
    running stateful analysis or GLRT at 25 MS/s.  High-rate-only recordings
    remain manual.
    """

    _require_reviewed_native_geometry(manifest)
    rates = {
        stream.stream_id: (stream.applied_settings or stream.requested_settings).sample_rate_hz
        for stream in manifest.streams
    }
    low_stream_ids = frozenset(stream_id for stream_id, rate in rates.items() if rate == 2_500_000)
    if not low_stream_ids:
        raise ValueError("automatic Standard-native analysis requires a 2.5 MS/s stream")
    native_25_stream_ids = frozenset(
        stream_id for stream_id, rate in rates.items() if rate == 25_000_000
    )
    return _compile_standard_native_run_plan(
        manifest,
        manifest_digest=manifest_digest,
        pipeline_release_id=pipeline_release_id,
        standard_stream_ids=low_stream_ids,
        pss_stream_ids=native_25_stream_ids,
        include_pss_glrt_comparison=bool(native_25_stream_ids),
    )


def _compile_standard_native_run_plan(
    manifest: RecordingManifestV3 | RecordingManifestV5 | RecordingManifestV6,
    *,
    manifest_digest: str,
    pipeline_release_id: str,
    standard_stream_ids: frozenset[str] | None,
    pss_stream_ids: frozenset[str] | None,
    include_pss_glrt_comparison: bool,
) -> ExpandedRunPlanV1:
    standard_topology = compile_standard_native_scope_inventory(
        manifest,
        selected_stream_ids=standard_stream_ids,
    )
    pss_topology = (
        None
        if pss_stream_ids == frozenset()
        else compile_standard_native_scope_inventory(
            manifest,
            selected_stream_ids=pss_stream_ids,
        )
    )
    all_stream_ids = frozenset(stream.stream_id for stream in manifest.streams)
    selected_stream_ids = (
        all_stream_ids if standard_stream_ids is None else standard_stream_ids
    ) | (all_stream_ids if pss_stream_ids is None else pss_stream_ids)
    full_topology = compile_standard_native_scope_inventory(
        manifest,
        selected_stream_ids=selected_stream_ids,
    )
    jobs: list[JobNodeV1] = []
    edges: list[JobDependencyRefV1] = []
    path_terminals: dict[str, list[str]] = {}

    standard_path_nodes: list[str] = []
    for path_ordinal, scope in enumerate(standard_topology.receiver_paths):
        assert scope.stream_id is not None
        path_node_id = f"path-{path_ordinal:02d}-standard-native"
        jobs.append(
            JobNodeV1(
                node_id=path_node_id,
                stage_key="path-standard-native",
                scope=scope,
                iq_access=IqAccess.RECEIVER_PATH,
                resource_class=ResourceClass.HEAVY,
            )
        )
        standard_path_nodes.append(path_node_id)
        alternate_node_id = f"path-{path_ordinal:02d}-alternate-tracks-native"
        jobs.append(
            JobNodeV1(
                node_id=alternate_node_id,
                stage_key="path-alternate-tracks-native",
                scope=scope,
                iq_access=IqAccess.NONE,
                resource_class=ResourceClass.CPU,
            )
        )
        edges.append(
            JobDependencyRefV1(
                job_node_id=alternate_node_id,
                depends_on_job_node_id=path_node_id,
            )
        )
        path_terminals.setdefault(scope.stream_id, []).append(path_node_id)

    pss_nodes: list[str] = []
    if pss_topology is not None:
        for path_ordinal, scope in enumerate(pss_topology.receiver_paths):
            node_id = f"pss-path-{path_ordinal:02d}-native"
            jobs.append(
                JobNodeV1(
                    node_id=node_id,
                    stage_key="path-pss-native",
                    scope=scope,
                    iq_access=IqAccess.RECEIVER_PATH,
                    resource_class=ResourceClass.HEAVY,
                )
            )
            pss_nodes.append(node_id)

    radio_nodes: list[str] = []
    for radio_ordinal, scope in enumerate(standard_topology.radios):
        assert scope.stream_id is not None
        node_id = f"radio-{radio_ordinal:02d}-reduce-native"
        jobs.append(
            JobNodeV1(
                node_id=node_id,
                stage_key="radio-scientific-report-native",
                scope=scope,
                iq_access=IqAccess.NONE,
                resource_class=ResourceClass.CPU,
            )
        )
        edges.extend(
            JobDependencyRefV1(job_node_id=node_id, depends_on_job_node_id=dependency)
            for dependency in sorted(path_terminals[scope.stream_id])
        )
        radio_nodes.append(node_id)

    if standard_topology.paired is not None:
        paired_node_id = "paired-00-reduce-native"
        jobs.append(
            JobNodeV1(
                node_id=paired_node_id,
                stage_key="paired-scientific-report-native",
                scope=standard_topology.paired,
                iq_access=IqAccess.NONE,
                resource_class=ResourceClass.CPU,
            )
        )
        edges.extend(
            JobDependencyRefV1(
                job_node_id=paired_node_id,
                depends_on_job_node_id=dependency,
            )
            for dependency in sorted(radio_nodes)
        )

        presentation_node_id = "paired-00-presentation-native"
        jobs.append(
            JobNodeV1(
                node_id=presentation_node_id,
                stage_key="paired-presentation-native",
                scope=standard_topology.paired,
                iq_access=IqAccess.NONE,
                resource_class=ResourceClass.CPU,
            )
        )
        # The paired presentation consumes every sealed path plot source plus
        # the paired report's exact common-valid UTC authority.
        edges.extend(
            JobDependencyRefV1(
                job_node_id=presentation_node_id,
                depends_on_job_node_id=node.node_id,
            )
            for node in jobs
            if node.stage_key == "path-standard-native"
        )
        edges.append(
            JobDependencyRefV1(
                job_node_id=presentation_node_id,
                depends_on_job_node_id=paired_node_id,
            )
        )

    if include_pss_glrt_comparison:
        if full_topology.paired is None or not pss_nodes:
            raise ValueError("paired PSS/GLRT comparison requires both native path families")
        rates_by_stream_id = {
            stream.stream_id: (stream.applied_settings or stream.requested_settings).sample_rate_hz
            for stream in manifest.streams
        }
        comparison_scopes = tuple(
            scope
            for scope in standard_topology.radios
            if scope.stream_id is not None and rates_by_stream_id[scope.stream_id] == 2_500_000
        )
        if len(comparison_scopes) != 1:
            raise ValueError("paired PSS/GLRT comparison requires one 2.5 MS/s radio scope")
        comparison_node_id = "paired-00-pss-glrt-presentation-native"
        jobs.append(
            JobNodeV1(
                node_id=comparison_node_id,
                stage_key="paired-pss-glrt-presentation-native",
                scope=comparison_scopes[0],
                iq_access=IqAccess.NONE,
                resource_class=ResourceClass.CPU,
            )
        )
        edges.extend(
            JobDependencyRefV1(
                job_node_id=comparison_node_id,
                depends_on_job_node_id=dependency,
            )
            for dependency in sorted((*standard_path_nodes, *pss_nodes))
        )

    return ExpandedRunPlanV1.create(
        session_id=manifest.session_id,
        manifest_digest=manifest_digest,
        pipeline_release_id=pipeline_release_id,
        jobs=tuple(jobs),
        edges=tuple(edges),
    )


def compile_standard_native_scope_inventory(
    manifest: RecordingManifestV3 | RecordingManifestV5 | RecordingManifestV6,
    *,
    selected_stream_ids: frozenset[str] | None = None,
) -> CompiledScopeInventory:
    """Build native scopes for current online recording formats."""

    if manifest.schema_version not in {3, 5, 6}:
        raise ValueError("Standard-native scope inventory requires recording schema 3, 5, or 6")
    all_stream_ids = frozenset(stream.stream_id for stream in manifest.streams)
    selected = all_stream_ids if selected_stream_ids is None else selected_stream_ids
    if not selected or not selected.issubset(all_stream_ids):
        raise ValueError("Standard-native stream selection must be a non-empty manifest subset")
    ordered = tuple(
        sorted(manifest.streams, key=lambda item: (item.stream_id, item.radio.radio_id))
    )
    identities = tuple((item.stream_id, item.radio.radio_id) for item in ordered)
    if (
        len(set(identities)) != len(identities)
        or len({item.stream_id for item in ordered}) != len(ordered)
        or len({item.radio.radio_id for item in ordered}) != len(ordered)
    ):
        raise ValueError("Standard-native manifest repeats a stream/radio topology identity")
    synchronization_inventory_digest = canonical_digest(
        [
            {
                "ordinal": ordinal,
                "stream_id": stream.stream_id,
                "radio": {
                    "radio_id": stream.radio.radio_id,
                    "serial": stream.radio.serial,
                    "uri": stream.radio.uri,
                    "transport": stream.radio.transport.value,
                },
                "receiver_ids": list(stream.applied_settings.receiver_ids),
                "sample_rate_hz": stream.applied_settings.sample_rate_hz,
                "logical_sample_count": stream.logical_sample_count,
                "observed_sample_count": stream.observed_sample_count,
                "timing": stream.timing.model_dump(mode="json"),
                "state": stream.state.value,
            }
            for ordinal, stream in enumerate(ordered)
        ]
    )
    selected_streams = tuple(stream for stream in ordered if stream.stream_id in selected)
    receiver_paths = tuple(
        ScopeIdentityV1.receiver_path(
            session_id=manifest.session_id,
            stream_id=stream.stream_id,
            receiver_id=receiver_id,
        )
        for stream in selected_streams
        for receiver_id in stream.applied_settings.receiver_ids
    )
    radios = tuple(
        ScopeIdentityV1.radio(
            session_id=manifest.session_id,
            stream_id=stream.stream_id,
            radio_id=stream.radio.radio_id,
        )
        for stream in selected_streams
    )
    return CompiledScopeInventory(
        receiver_paths=receiver_paths,
        radios=radios,
        paired=(
            None
            if len(selected_streams) != 2
            else ScopeIdentityV1.paired(
                session_id=manifest.session_id,
                synchronization_inventory_digest=synchronization_inventory_digest,
            )
        ),
        synchronization_inventory_digest=synchronization_inventory_digest,
    )


def _require_reviewed_native_geometry(
    manifest: RecordingManifestV3 | RecordingManifestV5 | RecordingManifestV6,
) -> None:
    if type(manifest) is RecordingManifestV6:
        _require_reviewed_direct_async_v6_geometry(manifest)
        return
    if type(manifest) is RecordingManifestV5:
        _require_reviewed_production_v5_geometry(manifest)
        return
    if type(manifest) is not RecordingManifestV3:
        raise ValueError("Standard-native expanded runs require recording schema 3, 5, or 6")
    if not manifest.streams:
        raise ValueError("Standard-native requires at least one recorded stream")
    revision = manifest.capture_plan.profile_revision
    profile = revision.profile
    expected_rate = STANDARD_NATIVE_PROFILE_RATE_HZ.get(profile.name)
    expected_revision = STANDARD_NATIVE_PROFILE_REVISION_DIGESTS.get(profile.name)
    if expected_rate is None or revision.revision_digest != expected_revision:
        raise ValueError("Standard-native capture profile identity is not reviewed")
    required_tags = {
        "CAPTURE_ONLY",
        "DEVICE_AXIS_ZERO_FILL",
        "LIVE",
        "RANDOM_TUNING",
        "STANDARD_NATIVE",
    }
    if (
        profile.schema_version != 2
        or profile.sample_rate_hz != expected_rate
        or profile.storage_policy != "zstd-128m-device-axis-zero-v1"
        or profile.continuity_policy.value != "allow_segments"
        or profile.peer_failure_policy.value != "fail_session"
        or not required_tags.issubset(profile.tags)
        or not required_tags.issubset(manifest.tags)
    ):
        raise ValueError("Standard-native capture profile capability is incomplete")
    if "NATIVE_BANDWIDTH" in profile.tags and (
        profile.bandwidth_hz != profile.sample_rate_hz
        or profile.refill_samples != STANDARD_NATIVE_MIXED_REFILL_SAMPLES
        or profile.kernel_buffers != STANDARD_NATIVE_MIXED_KERNEL_BUFFERS
        or profile.refill_queue_capacity != STANDARD_NATIVE_MIXED_QUEUE_CAPACITY
    ):
        raise ValueError("Standard-native native-bandwidth capture geometry is incomplete")
    rates = {
        (stream.applied_settings or stream.requested_settings).sample_rate_hz
        for stream in manifest.streams
    }
    if len(rates) != 1 or next(iter(rates)) != expected_rate:
        raise ValueError("Standard-native requires one reviewed common native sample rate")
    expected_samples = manifest.capture_plan.resolved_sample_count
    if any(
        stream.requested_sample_count != expected_samples
        or stream.logical_sample_count != expected_samples
        or stream.requested_settings.sample_rate_hz != profile.sample_rate_hz
        or stream.requested_settings.bandwidth_hz != profile.bandwidth_hz
        or stream.applied_settings.sample_rate_hz != profile.sample_rate_hz
        or stream.applied_settings.bandwidth_hz != profile.bandwidth_hz
        or abs(
            stream.applied_settings.center_frequency_hz
            - stream.requested_settings.center_frequency_hz
        )
        > max(1, round(stream.requested_settings.center_frequency_hz * 1e-6))
        for stream in manifest.streams
    ):
        raise ValueError("Standard-native stream geometry differs from the reviewed capture plan")
    if any(
        tuple((stream.applied_settings or stream.requested_settings).receiver_ids) != (0, 1)
        for stream in manifest.streams
    ):
        raise ValueError("Standard-native requires the reviewed dual-receiver geometry")
    tuning_by_stream = resolve_manifest_starlink_tuning(manifest)
    if "NATIVE_BANDWIDTH" in profile.tags:
        for stream in manifest.streams:
            tuning = tuning_by_stream[stream.stream_id]
            expected_center_hz = starlink_maximum_coverage_if_center_frequency_hz(
                tuning.channel,
                tuning.edge,
                bandwidth_hz=profile.bandwidth_hz,
            )
            if (
                stream.requested_settings.center_frequency_hz != expected_center_hz
                or stream.applied_settings.center_frequency_hz != expected_center_hz
            ):
                raise ValueError("Standard-native RF center does not maximize in-channel coverage")


def _require_reviewed_production_v5_geometry(manifest: RecordingManifestV5) -> None:
    """Admit exact V2-policy captures, including one-path high-rate radio legs."""

    plan = manifest.capture_plan
    if manifest.source_type is not SourceType.LIVE or len(manifest.streams) != 2:
        raise ValueError("Standard-native production capture requires exactly two LIVE streams")
    expected_rates = {
        ProductionDwellClassV2.BOTH_2P5: (2_500_000, 2_500_000),
        ProductionDwellClassV2.BOTH_5: (5_000_000, 5_000_000),
        ProductionDwellClassV2.MIXED_2P5_5: (2_500_000, 5_000_000),
        ProductionDwellClassV2.MIXED_2P5_10: (2_500_000, 10_000_000),
        ProductionDwellClassV2.MIXED_2P5_15: (2_500_000, 15_000_000),
        ProductionDwellClassV2.MIXED_2P5_20: (2_500_000, 20_000_000),
    }[plan.dwell_class]
    if sorted(item.requested_settings.sample_rate_hz for item in plan.radio_plans) != sorted(
        expected_rates
    ):
        raise ValueError("Standard-native production rates disagree with dwell class")
    required_manifest_tags = {
        "CAPTURE_ONLY",
        "DEVICE_AXIS_ZERO_FILL",
        "LIVE",
        "NATIVE_BANDWIDTH",
        "RANDOM_TUNING",
        "STANDARD_NATIVE",
        "PRODUCTION_NATIVE_RATES_V2",
    }
    if not required_manifest_tags.issubset(manifest.tags):
        raise ValueError("Standard-native production manifest capability is incomplete")
    is_mixed = plan.dwell_class.value.startswith("mixed_")
    for stream, leg in zip(manifest.streams, plan.radio_plans, strict=True):
        profile = leg.profile_revision.profile
        identity = STANDARD_NATIVE_PRODUCTION_PROFILE_IDENTITIES.get(profile.name)
        rate = leg.requested_settings.sample_rate_hz
        required_receiver_count = 1 if is_mixed and rate > 5_000_000 else 2
        required_profile_tags: set[str] = set()
        if identity is not None:
            expected_rate, expected_receivers, expected_digest, expected_refill_samples = identity
            expected_kernel_buffers = STANDARD_NATIVE_MIXED_KERNEL_BUFFERS
            expected_queue_capacity = STANDARD_NATIVE_MIXED_QUEUE_CAPACITY
        else:
            direct_identity = STANDARD_NATIVE_DIRECT_ASYNC_PROFILE_IDENTITIES.get(profile.name)
            if direct_identity is None:
                raise ValueError("Standard-native production profile identity is not reviewed")
            expected_rate, expected_receivers, expected_digest = direct_identity
            exact_dma_v5 = "DEVICE_BUFFER:DIRECT_ASYNC_EXACT_DMA_DROP_V5" in profile.tags
            expected_refill_samples = 1_000_000 if exact_dma_v5 else 1_048_576
            ram_drop_v4 = "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V4" in profile.tags
            ram_drop_v3 = "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V3" in profile.tags
            ram_drop_v2 = "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V2" in profile.tags
            expected_kernel_buffers = (
                50
                if exact_dma_v5
                else 11
                if ram_drop_v4 or ram_drop_v3
                else 12
                if ram_drop_v2
                else 15
            )
            expected_queue_capacity = 64
            required_profile_tags = {
                (
                    "DEVICE_BUFFER:DIRECT_ASYNC_EXACT_DMA_DROP_V5"
                    if exact_dma_v5
                    else (
                        "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V4"
                        if ram_drop_v4
                        else (
                            "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V3"
                            if ram_drop_v3
                            else (
                                "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V2"
                                if ram_drop_v2
                                else "DEVICE_BUFFER:DIRECT_ASYNC_SEGMENTED_V1"
                            )
                        )
                    )
                ),
                "SINGLE_RX",
            }
        settings = stream.applied_settings
        if (
            leg.profile_revision.revision_digest != expected_digest
            or profile.sample_rate_hz != expected_rate
            or profile.bandwidth_hz != expected_rate
            or profile.receivers != expected_receivers
            or len(profile.receivers) != required_receiver_count
            or profile.duration_seconds != plan.duration_seconds
            or profile.refill_samples != expected_refill_samples
            or profile.kernel_buffers != expected_kernel_buffers
            or profile.refill_queue_capacity != expected_queue_capacity
            or profile.storage_policy != "zstd-128m-device-axis-zero-v1"
            or profile.continuity_policy.value != "allow_segments"
            or profile.peer_failure_policy.value != "fail_session"
            or not required_profile_tags.issubset(profile.tags)
            or stream.radio.radio_id != leg.radio_id
            or stream.requested_sample_count != leg.resolved_sample_count
            or stream.logical_sample_count != leg.resolved_sample_count
            or stream.requested_settings != leg.requested_settings
            or settings.sample_rate_hz != rate
            or settings.bandwidth_hz != rate
            or settings.receiver_ids != profile.receivers
            or settings.center_frequency_hz != leg.requested_settings.center_frequency_hz
            or settings.gain_mode is not GainMode.MANUAL
            or stream.continuity.metadata_abi_version != 3
            or not stream.continuity.sample_loss_observable
        ):
            raise ValueError(
                "Standard-native production profile, stream, or metadata geometry is not reviewed"
            )
    tuning = resolve_manifest_starlink_tuning(manifest)
    for stream, leg in zip(manifest.streams, plan.radio_plans, strict=True):
        resolved = tuning[stream.stream_id]
        if resolved.channel != leg.starlink_channel or resolved.edge is not leg.starlink_edge:
            raise ValueError("Standard-native production tuning tags disagree with capture plan")


def _require_reviewed_direct_async_v6_geometry(manifest: RecordingManifestV6) -> None:
    """Admit exact same-target 2.5 x 10/15/25 MS/s direct-async captures."""

    plan = manifest.capture_plan
    if manifest.source_type is not SourceType.LIVE or len(manifest.streams) != 2:
        raise ValueError("Standard-native direct-async capture requires two LIVE streams")
    high_rate = {
        ProductionDwellClassV3.MIXED_2P5_10: 10_000_000,
        ProductionDwellClassV3.MIXED_2P5_15: 15_000_000,
        ProductionDwellClassV3.MIXED_2P5_25: 25_000_000,
    }[plan.dwell_class]
    if sorted(item.requested_settings.sample_rate_hz for item in plan.radio_plans) != [
        2_500_000,
        high_rate,
    ]:
        raise ValueError("Standard-native direct-async rates disagree with dwell class")
    required_manifest_tags = {
        "CAPTURE_ONLY",
        "DEVICE_AXIS_ZERO_FILL",
        "LIVE",
        "MIXED_RATE",
        "NATIVE_BANDWIDTH",
        "RANDOM_TUNING",
        "STANDARD_NATIVE",
        "PRODUCTION_DIRECT_ASYNC_RATES_V3",
    }
    if not required_manifest_tags.issubset(manifest.tags):
        raise ValueError("Standard-native direct-async manifest capability is incomplete")
    for stream, leg in zip(manifest.streams, plan.radio_plans, strict=True):
        profile = leg.profile_revision.profile
        rate = leg.requested_settings.sample_rate_hz
        high_leg = rate != 2_500_000
        if high_leg:
            identity = STANDARD_NATIVE_DIRECT_ASYNC_PROFILE_IDENTITIES.get(profile.name)
            if identity is None:
                raise ValueError("Standard-native direct-async profile identity is not reviewed")
            expected_rate, direct_receivers, expected_digest = identity
            expected_receivers: tuple[int, ...] = direct_receivers
            exact_dma_v5 = "DEVICE_BUFFER:DIRECT_ASYNC_EXACT_DMA_DROP_V5" in profile.tags
            expected_refill_samples = 1_000_000 if exact_dma_v5 else 1_048_576
            ram_drop_v4 = "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V4" in profile.tags
            ram_drop_v3 = "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V3" in profile.tags
            ram_drop_v2 = "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V2" in profile.tags
            expected_kernel_buffers = (
                50
                if exact_dma_v5
                else 11
                if ram_drop_v4 or ram_drop_v3
                else 12
                if ram_drop_v2
                else 15
            )
            expected_queue_capacity = 64
            required_profile_tags = {
                (
                    "DEVICE_BUFFER:DIRECT_ASYNC_EXACT_DMA_DROP_V5"
                    if exact_dma_v5
                    else (
                        "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V4"
                        if ram_drop_v4
                        else (
                            "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V3"
                            if ram_drop_v3
                            else (
                                "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V2"
                                if ram_drop_v2
                                else "DEVICE_BUFFER:DIRECT_ASYNC_SEGMENTED_V1"
                            )
                        )
                    )
                ),
                "SINGLE_RX",
            }
        else:
            production_identity = STANDARD_NATIVE_PRODUCTION_PROFILE_IDENTITIES.get(profile.name)
            if production_identity is None:
                raise ValueError("Standard-native 2.5 MS/s profile identity is not reviewed")
            (
                expected_rate,
                production_receivers,
                expected_digest,
                expected_refill_samples,
            ) = production_identity
            expected_receivers = production_receivers
            expected_kernel_buffers = STANDARD_NATIVE_MIXED_KERNEL_BUFFERS
            expected_queue_capacity = STANDARD_NATIVE_MIXED_QUEUE_CAPACITY
            required_profile_tags = set()
        settings = stream.applied_settings
        if (
            leg.profile_revision.revision_digest != expected_digest
            or profile.sample_rate_hz != expected_rate
            or profile.bandwidth_hz != expected_rate
            or profile.receivers != expected_receivers
            or len(profile.receivers) != (1 if high_leg else 2)
            or profile.duration_seconds != plan.duration_seconds
            or profile.refill_samples != expected_refill_samples
            or profile.kernel_buffers != expected_kernel_buffers
            or profile.refill_queue_capacity != expected_queue_capacity
            or profile.storage_policy != "zstd-128m-device-axis-zero-v1"
            or profile.continuity_policy.value != "allow_segments"
            or profile.peer_failure_policy.value != "fail_session"
            or not required_profile_tags.issubset(profile.tags)
            or stream.radio.radio_id != leg.radio_id
            or stream.requested_sample_count != leg.resolved_sample_count
            or stream.logical_sample_count != leg.resolved_sample_count
            or stream.requested_settings != leg.requested_settings
            or settings.sample_rate_hz != rate
            or settings.bandwidth_hz != rate
            or settings.receiver_ids != profile.receivers
            or settings.center_frequency_hz != leg.requested_settings.center_frequency_hz
            or settings.gain_mode is not GainMode.MANUAL
            or stream.continuity.metadata_abi_version != 3
            or not stream.continuity.sample_loss_observable
        ):
            raise ValueError(
                "Standard-native direct-async profile, stream, or metadata geometry is not reviewed"
            )
    tuning = resolve_manifest_starlink_tuning(manifest)
    targets = set()
    for stream, leg in zip(manifest.streams, plan.radio_plans, strict=True):
        resolved = tuning[stream.stream_id]
        targets.add((resolved.channel, resolved.edge))
        if resolved.channel != leg.starlink_channel or resolved.edge is not leg.starlink_edge:
            raise ValueError("Standard-native direct-async tuning tags disagree with capture plan")
    if len(targets) != 1:
        raise ValueError("Standard-native direct-async capture requires one common RF target")
