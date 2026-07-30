# Phase 5 evidence

Source-controlled scenario definitions live in `../simulation`. Actual run
records belong in `generated/` and must be created by
`simulation/scripts/record-evidence.ps1`; do not hand-edit them. The recorder
pins fixture identity and software versions, rejects secret-bearing fields,
hashes referenced artifacts, and refuses overwrites.

No successful run records are included until the three branches are integrated
and the scenario is actually observed. This is intentional: an empty generated
directory is more accurate than fabricated evidence.

Allowed evidence is limited to non-sensitive timings, counts, outcomes, route
or hop information where the simulator exposes it, and sanitized tool output.
Do not store report text, exact real-world incident coordinates, signatures,
frame bodies, payloads, channel keys, API keys, responder tokens, or internal
service tokens. The frozen fixture message ID and digest are identifiers for
public test material only.

Site Planner exports are different: they may contain only the explicitly
synthetic coordinates in `simulation/site-planner/study-input.json`. Preserve
exports byte-for-byte and record their hashes.

