export interface FrozenAdaptivePhaseArtifact {
  sessionId: string;
  sha256: `sha256:${string}`;
  byteCount: number;
  href: string;
}

const artifact = (
  sessionId: string,
  digest: string,
  byteCount: number,
): FrozenAdaptivePhaseArtifact => ({
  sessionId,
  sha256: `sha256:${digest}`,
  byteCount,
  href: `/reports/adaptive-dual-rx-phase/${sessionId}-${digest.slice(0, 16)}.png`,
});

const frozenAdaptivePhaseArtifacts = new Map<string, FrozenAdaptivePhaseArtifact>([
  artifact("scan-hop-45b79e4e8b5e4d72", "dc8d0dcc6b4c4e70b6b3b5bbf3812e3316dad1f4b91fbb8d2feb2d48e560e227", 408_638),
  artifact("scan-hop-9626fed2bb56f5c4", "cb516e37ccec525cf9cd1e8382af9258f20be80f1d89675e0bfcb5a5e0d7ff5f", 429_389),
  artifact("scan-hop-bfc60ea18ace593b", "c0e379c8d7c897a2d676d95102450dbe4caf6dd40c31c60bb96acfc52fdfbb2d", 541_025),
  artifact("scan-hop-ca76f0138c3d5538", "09e9330dd0a97f34cbf9684f4d8626ac6f71bdab13cbc58c0c917564e6d93a82", 404_403),
  artifact("scan-hop-ebe72de635485b4e", "771d7f95085aacd7bd5011e23c5ba00bdfc79520609e934f74a41cf18d1671bb", 471_361),
].map((item) => [item.sessionId, item]));

export function frozenAdaptivePhaseArtifact(
  sessionId: string,
): FrozenAdaptivePhaseArtifact | null {
  return frozenAdaptivePhaseArtifacts.get(sessionId) ?? null;
}
