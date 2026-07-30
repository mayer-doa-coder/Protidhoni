# Phase 5 evidence

Source-controlled scenario definitions live in `../simulation`. Actual run
records belong in `generated/` and must be created by the automated scenario
runner or `simulation/scripts/record-evidence.ps1`; do not hand-edit them. The
recorder pins fixture identity and software versions, rejects secret-bearing
fields, and hashes referenced artifacts. The committed seven-scenario matrix
was generated from real simulator/backend runs, and the validator checks every
record against the reviewed expectation and its sanitized log digest.

Allowed evidence is limited to non-sensitive timings, counts, outcomes, route
or hop information where the simulator exposes it, and sanitized tool output.
Do not store report text, exact real-world incident coordinates, signatures,
frame bodies, payloads, channel keys, API keys, responder tokens, or internal
service tokens. The frozen fixture message ID and digest are identifiers for
public test material only.

Site Planner exports are different: they may contain only the explicitly
synthetic coordinates in `simulation/site-planner/study-input.json`. Preserve
exports byte-for-byte and record their hashes. Each Site Planner manifest is
also bound to the reviewed input hash, run/capture timestamps, official URL,
browser, limitations, valid GeoJSON study area, and PNG screenshot.

