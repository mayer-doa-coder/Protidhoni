# Protidhoni — Complete Build Roadmap
### Crisis communication system for the July Hackathon 2026 (Track A: Crisis Tech)

---

## 0. Read this first

Two honest notes before the roadmap:

1. **The clock.** By the hackathon's own timeline, the build sprint started 28 July 00:00 and submission closes 30 July 23:59 (BST). You asked me to plan assuming you have enough time to do this end‑to‑end, properly, and I've done that below. But if you are reading this on 29 or 30 July, you don't have that time inside the hackathon window. So every phase below is tagged:
   - **MUST (hackathon)** — build this or you have nothing to submit.
   - **SHOULD (hackathon)** — build this if the MUST list is done early.
   - **LATER (post‑hackathon)** — the "complete, production" version of the idea. Real, worth building, not realistic in 72 hours.
   
   Use the tags to triage. Everything else in this document is the honest full picture you asked for.

2. **Your repo is currently empty** (just a LICENSE file), so you're starting completely from scratch — which is good, it means there's no legacy code to work around, and it fits Section 06 Rule 01 (all core work must be produced during the sprint) cleanly.

---

## 1. What you're actually building, in plain words

Three separate paths into the same pool of information:

- A **phone with an app** can talk to other nearby phones directly over Bluetooth/Wi‑Fi Direct, even with zero internet and zero cell signal — like passing notes hand to hand, except phones do it automatically and silently.
- A **button phone** (no app, no internet) can send a plain text SMS or dial a short code, and get understood the same way.
- Whenever *any* phone in the chain touches the internet again (even for ten seconds), it uploads everything it's carrying to a cloud server.
- That server tags and prioritises each report automatically (is this urgent? is it a duplicate of five other reports? what does it need?) and shows it on a map to responders, who can act on it and push instructions back down the same paths.

That's the whole system. Everything below is how to build each piece and how to split it three ways without anyone stepping on anyone else's code.

---

## 2. Reference architecture

See the diagram above. In words, five layers:

1. **Smartphone app** — the primary client. Works fully offline. Lets someone fill in a structured report (SOS, medical need, resource need, safety status, shelter info, hazard update, safe route request) and broadcasts it over the mesh.
2. **Offline mesh relay** — the Bluetooth/Wi‑Fi Direct layer that moves a report from phone to phone, hop by hop, until it reaches a phone that has internet.
3. **SMS/USSD/IVR gateway** — the parallel path for feature phones. A person texts a short code or short message; a gateway service turns it into the same structured report format.
4. **Cloud sync and AI backend** — one server that stores every report, deduplicates it, scores its urgency, translates it if needed, and exposes it through an API.
5. **Responder dashboard** — a map-based web app for responders to see, verify, prioritise, and act on incoming reports, and push updates (safe routes, shelter capacity, instructions) back out.

---

## 3. Tech stack — decided, not open-ended

Pick these and don't relitigate them mid-sprint. Reasoning is in brackets.

| Layer | Choice | Why |
|---|---|---|
| Mobile client | **React Native (TypeScript), Android-first** | React Native gives the team a fast shared UI and offline workflow. Nearby Connections still needs a small Android-native Kotlin bridge (Turbo Native Module) for radio access; Android is the Phase 0 test target. |
| Mesh transport | **Google Nearby Connections API** (`P2P_CLUSTER` strategy) | It abstracts direct nearby transport across Bluetooth, Wi‑Fi, and related radios. `P2P_CLUSTER` provides an M-to-N cluster of direct links; the app's store-and-forward queue implements multi-hop relaying above it. |
| Local on-device storage | **SQLite / Room** | Store-and-forward needs a durable local queue; Room gives you that with almost no boilerplate. |
| Backend | **Python + FastAPI** (or Node + Express, pick whichever your Person A knows best) | Fast to write, auto-generates OpenAPI docs, which you need anyway for the contract (§4). |
| Database | **PostgreSQL + PostGIS** | You need geographic queries (nearby reports, clustering) from day one; PostGIS is the standard answer. |
| AI/NLP service | **Separate microservice, Python (FastAPI) + BanglaBERT / BanglishBERT** | Keeping it separate from the main backend means Person C never touches Person A's code (see §5). |
| Responder dashboard | **React + Leaflet (OpenStreetMap tiles)** | Free, no API key hassle (unlike Google Maps billing), well documented, plenty of hackathon-proven examples. |
| Deployment | **Docker Compose locally, Render or Railway or Fly.io for the live demo** | Free tiers, fast to deploy, no cloud-console yak-shaving. |
| SMS/USSD gateway | **Twilio (or a local aggregator like SSL Wireless/Alpha SMS if you can get a sandbox key in time)** | Twilio's trial tier is enough for a live demo; disclose in the submission that this stands in for a local telco integration. |
| Encryption/signing | **libsodium (Ed25519 signatures, X25519 key exchange)** | Battle-tested, small, available as a library on every platform you're using. |
| LoRa simulation / hardware readiness | **Meshtasticator + Meshtastic Site Planner**; optional **Wokwi** for ESP32-only controller tests | This costs nothing while exercising Meshtastic's Linux-native device software in a simulated mesh and modelling terrain/link budgets. Wokwi does not simulate the SX1276 radio, so it is not RF evidence. Physical ESP32 + LoRa nodes remain post-hackathon work. |

---

## 4. The one thing you must do before writing feature code: freeze the contract

This is the single most important step for a 3-person team working in parallel without merge conflicts. On **hour 0**, before anyone writes application logic, agree on and commit two files. After that, nobody touches them without a team conversation.

### 4.1 The message schema (`/contracts/message-schema.json`)

This is the shape of every piece of information moving through your system — mesh, SMS, cloud, dashboard, all of it uses this same shape.

```json
{
  "message_id": "uuid-v4",
  "type": "SOS | MEDICAL_NEED | RESOURCE_NEED | SAFETY_STATUS | SHELTER_INFO | HAZARD_UPDATE | SAFE_ROUTE | INSTRUCTION",
  "sender_pubkey_hash": "string (pseudonymous, not a phone number or name)",
  "created_at": "ISO 8601, set on the device",
  "language": "bn | en",
  "location": {
    "lat": "float | null",
    "lng": "float | null",
    "accuracy_m": "float | null",
    "source": "gps | manual | none"
  },
  "payload": {
    "text": "string, free text (what the AI/NLP service classifies)",
    "people_count": "int | null",
    "needs": ["water", "medical", "shelter", "..."],
    "attachment_ref": "string | null (photo hash, optional)"
  },
  "priority": "critical | high | medium | low | null (null until AI-scored)",
  "ttl_hops": "int, decremented on each relay, dropped at 0",
  "signature": "ed25519 signature over the canonical payload",
  "relay_path": ["device-hash-1", "device-hash-2"],
  "sync_status": "local | relayed | synced",
  "verification": {
    "status": "unverified | corroborated | verified | disputed",
    "corroboration_count": "int"
  }
}
```

Why this matters: Person B's app writes this shape to local storage and over the mesh. Person A's backend accepts this exact shape and stores it. Person C's AI service reads this shape and only *adds* fields (`priority`, `verification`) — it never needs to change what's already there. Nobody needs to ask anybody else "what does your data look like" mid-sprint, because it's written down on hour 0.

### 4.2 The API contract (`/contracts/openapi.yaml`)

Minimum endpoints Person A's backend must expose, written as an OpenAPI spec **before** implementation:

- `POST /reports` — client or gateway submits one or more messages (batch, since sync happens in bursts)
- `GET /reports?since=<timestamp>&bbox=<geo box>` — dashboard pulls reports
- `PATCH /reports/{id}` — responder marks a report verified/disputed, or updates its status
- `POST /instructions` — responder pushes an outbound message (safe route, shelter update) that flows back down to the mesh/SMS paths
- `POST /ai/classify` — internal endpoint the AI service calls into, or that the backend calls out to (decide direction once, write it down)

Person B and Person C can now build against a **mock server** generated straight from this OpenAPI file (tools like Prism or FastAPI's own auto-docs give you this for free) — they don't have to wait for Person A's real server to exist.

---

## 5. Domain-by-domain breakdown

### 5.1 Network / Mesh (owned by Person B)
- Device discovery and connection using Nearby Connections' `P2P_CLUSTER` strategy (many-to-many, mesh-like, as opposed to `P2P_STAR` which assumes one hub device).
- A **store-and-forward queue**: every message a device has seen (sent by itself or relayed) sits in local storage with a hop counter (`ttl_hops`). When a new peer connects, the device offers everything in its queue that the peer hasn't seen yet.
- **Deduplication at the mesh layer**: track `message_id`s you've already relayed so the same SOS doesn't bounce around the mesh forever. This is separate from the *content* deduplication the AI service does later (two different people reporting the same flooded road) — mesh dedup is about not re-sending the identical packet.
- **Internet-gateway detection**: any device that regains connectivity (Wi‑Fi or mobile data) automatically POSTs its whole local queue to the backend, then keeps relaying over the mesh as normal. Any single phone can be the bridge; there's no dedicated "server phone."
- Known real-world reference: **Meshtastic** solves the same hop-and-relay problem over LoRa hardware with a managed flooding algorithm and a hop-count-based TTL — study its approach for inspiration even though you're using BLE/Wi‑Fi Direct rather than LoRa for the phone-to-phone layer.

### 5.2 Backend / Cloud (owned by Person A)
- REST API implementing the contract in §4.2.
- PostgreSQL + PostGIS schema: a `reports` table matching the message schema, with a geography column for `location`, indexed for bounding-box queries.
- Idempotent ingestion: because the same report may arrive from multiple relay paths (mesh dedup isn't perfect across independent device chains), `POST /reports` must upsert on `message_id`, not blindly insert.
- Deployment: Docker Compose for local dev (Postgres + API + AI service as three containers), one-command deploy to Render/Fly.io/Railway for the live demo link the submission requires.
- Rate limiting and basic abuse protection (see Security below) on every public endpoint.

### 5.3 Frontend / Client (owned by Person B)
- The smartphone app: structured forms for each `type` in the schema (SOS, medical need, etc.) — not a free-text-only chat app; structure is what lets the AI layer and responders act on it instead of just reading it.
- Fully functional with the phone in airplane mode. Test this explicitly — pull the SIM, turn off Wi‑Fi, and confirm the whole create → queue → mesh-send path works.
- A local "my reports" view showing sync status (local / relayed / synced) so a user isn't left wondering if their SOS actually went anywhere.
- Low-end-device and low-bandwidth design: no heavy images by default, text-first UI, works on a 3-year-old budget Android phone.

### 5.4 AI / ML / DL / NLP (owned by Person C)
This is a separate microservice, called by the backend, never imported directly into it (see §6 for why that boundary matters for merge conflicts).

- **Text classification (NLP)**: given `payload.text`, confirm/refine the `type` field and extract structured `needs`. Use **BanglaBERT** or **BanglishBERT** (from BUET's CSE NLP group — pretrained specifically for Bangla, state-of-the-art on Bangla benchmarks, free on Hugging Face) fine-tuned on a small labelled set you create yourselves (a few hundred example crisis messages is enough for a hackathon demo; augment with synthetic examples if needed). If fine-tuning time runs out, fall back to a simpler TF-IDF + logistic regression classifier trained on the same small dataset — it will be less accurate but it will work and it will be honest about what it is.
- **Urgency/priority scoring (ML)**: a rules-plus-model hybrid is fine and arguably more explainable to judges than a black box — e.g. keyword signals ("drowning," "bleeding," "trapped") combined with a trained classifier, producing `critical / high / medium / low`.
- **Deduplication and clustering**: group reports that are about the same real-world incident (same location cluster + similar text) so a responder sees "14 reports of flooding on this road" instead of 14 separate cards. Sentence embeddings (`sentence-transformers`, multilingual model) plus a simple clustering step (DBSCAN over embedding + geo distance) does this well.
- **Translation**: Bangla ↔ English so international or non-Bangla-speaking responders/judges can read every report. BanglaT5 (also from BUET) or any hosted translation API works; disclose whichever you use.
- **Verification/trust scoring**: not full identity verification (that defeats the point of a low-friction crisis tool) but a **corroboration score** — how many independent reports/devices support this claim — modelled directly on how Ushahidi's report lifecycle (unverified → corroborated → verified) works. This is what lets a responder triage 1,000 incoming reports without reading all 1,000.
- **DL, if you have time**: if photos are attached (damage assessment), a small pretrained image classifier (e.g. a fine-tuned MobileNet) can flag "structural damage visible / water visible / no visual signal" as a soft hint to responders — clearly labelled as a hint, not a verdict.

### 5.5 Security (owned by Person A, with input from Person B on-device)
Real lesson from real prior art: a widely used mesh-messaging app (**Bridgefy**) was shown by researchers to be breakable in serious ways — attackers could impersonate any user, read messages, build social graphs of who talked to whom, and even crash the whole mesh with one crafted message — largely because it derived a person's identity from the Bluetooth link itself rather than from a real cryptographic identity. Concretely, that means:
- Every device generates its own **Ed25519 keypair** on first launch. The `sender_pubkey_hash` in every message is derived from this key, never from a Bluetooth MAC address or phone number.
- Every message is **signed** by the sender's private key before being broadcast. Any relaying device (and the backend) can verify the signature without trusting the device that relayed it to them — this is what stops a malicious relay node from forging or altering messages in transit.
- **Don't build in more anonymity than the mission needs.** Full unlinkable anonymity makes verification and abuse-prevention much harder (and, per Section 12, you must not build surveillance tooling but you also must state what data you collect and why) — pseudonymous-but-signed identities are the right middle ground for this use case.
- **Rate limiting / basic Sybil resistance**: cap how many reports one device identity can push per minute, both device-side and backend-side, so a single bad actor can't flood the mesh or the dashboard.
- **Data minimisation**: never collect a phone's contact list, real name, or precise home address unless the user explicitly puts it in a report; state this plainly in your README (Section 12 requires you to state what you collect and why).
- **Encrypt data at rest** in Postgres for anything sensitive (medical needs, exact locations of vulnerable people) and use TLS for every network hop that touches the internet.

### 5.6 Zero-cost LoRa simulation and hardware-readiness evidence (shared, with split ownership in §7)
- Use the official [Meshtasticator](https://github.com/meshtastic/Meshtasticator) interactive simulator to run multiple Linux-native Meshtastic instances in Docker. It simulates the hardware interfaces, including the LoRa chip, while exercising the device application and routing code; use it to test application framing, relay hops, duplicates, loss, and node outages without buying radios.
- Use the official [Meshtastic Site Planner](https://site.meshtastic.org/) for a separate propagation study. Save the transmitter/receiver locations, antenna-height assumptions, radio preset, terrain result, line-of-sight/Fresnel result, and link margin. Label every value as a simulation assumption, not a field measurement.
- The existing signed Protidhoni report contract remains unchanged. A versioned, bounded **transport frame** may split its serialized bytes across Meshtastic application packets, but reassembly must reproduce the original signed report and the existing backend must accept and verify it. This is a transport encoding, not a new public API contract.
- Wokwi may optionally demonstrate ESP32 controller logic, GPIO, a display, or a wiring diagram. Its supported-hardware catalogue does not include an SX1276 LoRa radio, so a Wokwi demo must never be described as a Meshtastic RF or range test.
- Simulation can demonstrate software/protocol compatibility and make the later hardware build reproducible. It cannot validate an actual antenna, RF interference, receiver sensitivity, electrical wiring, battery life, thermal behaviour, enclosure/weatherproofing, or local radio compliance. Those stay explicitly unverified until real hardware is tested.

### 5.7 Data / Mapping (owned by Person C)
- The responder dashboard's map view (Leaflet + OpenStreetMap) — pins colour-coded by `priority`, clickable to see the full report, filterable by `type` and `verification.status`.
- A simple state machine for report lifecycle mirrors Ushahidi's proven model: `unverified → corroborated → verified` (or `→ disputed`), with the dashboard showing counts at each stage — this single idea address the "does it belong in its track" and "technical execution" judging criteria at once, because it's the part that turns raw crowd noise into something a real responder could act on.

---

## 6. Team split and repo structure — zero merge conflicts by design

The trick isn't "be careful," it's **structural separation**: nobody can conflict with code they never open.

```
/protidhoni
  /contracts/              <- frozen after hour 0 (§4). Everyone reads, nobody edits without a team call.
      message-schema.json
      openapi.yaml
  /mobile-client/           <- Person B only
      app/
      README.md
  /backend/                 <- Person A only
      api/
      db/
      docker-compose.yml
      README.md
  /ai-service/              <- Person C only
      classify/
      dedupe/
      translate/
      README.md
  /dashboard/               <- Person C only
      src/
      README.md
  /hardware/                <- Phase 5 only; subdirectories have exclusive owners
      /protocol/             <- Person B only: frame specification, codec, and golden vectors
      /gateway/              <- Person A only: simulated-radio-to-existing-API bridge
      /simulation/           <- Person C only: Meshtasticator/Site Planner scenarios and scripts
      /evidence/             <- Person C only: generated reports, metrics, and limitations
      README.md              <- Person C only, after the protocol interface is frozen
  /docs/
      architecture.md
      demo-script.md
  README.md                 <- top-level, everyone contributes, but in short, timed turns
```

Rules that make this work:
1. **Person A** = Backend + Cloud + Security. Normally touches `/backend`; in Phase 5 also exclusively owns `/hardware/gateway`.
2. **Person B** = Client + Mesh Network. Normally touches `/mobile-client`; in Phase 5 also exclusively owns `/hardware/protocol`.
3. **Person C** = AI/ML/NLP + Dashboard + Data. Normally touches `/ai-service` and `/dashboard`; in Phase 5 also exclusively owns `/hardware/simulation`, `/hardware/evidence`, and `/hardware/README.md`.
4. Each person works on their **own branch** (`feature/backend`, `feature/client`, `feature/ai`) and commits small, frequent, descriptive commits — Section 06 Rule 05 explicitly checks your commit history, so don't squash three days of work into one commit at the deadline.
5. Merge to `main` at the end of each phase (see §7), not continuously — this avoids the awkward mid-feature half-working states colliding.
6. The **only** shared file anyone edits together is the top-level `README.md`, and only in short scheduled turns (e.g. each person adds their section, 15 minutes, done) — never simultaneously.
7. If `/contracts` genuinely needs to change mid-sprint (it might — real requirements shift), that's a synchronous team decision, not a solo edit, precisely because all three of you depend on it.

---

## 7. Sequential roadmap

Each phase lists what "done" looks like and who owns what. Tags: **MUST** = needed for a valid submission, **SHOULD** = do if ahead of schedule, **LATER** = real but post-hackathon.

### Phase 0 — Contract and setup (first few hours) — **MUST**
- All three: agree on the message schema and API contract (§4), create the repo structure (§6), pick the tech stack (§3) and don't revisit it.
- Person A: scaffold the backend project, get a "hello world" endpoint deployed to your chosen host so the deployment pipeline is proven on day one, not day three.
- Person B: scaffold the React Native project and its Android Nearby bridge, then get Nearby Connections advertising/discovery working between two physical Android devices (no app logic yet — just prove two phones can see each other with no internet).
- Person C: pull BanglaBERT/BanglishBERT and confirm it runs locally; scaffold the AI microservice and dashboard projects.

### Phase 1 — Core paths working end to end, ugly is fine — **MUST**
- Person A: implement `POST /reports`, `GET /reports`, database schema, basic auth/rate limiting.
- Person B: structured report forms (start with just SOS), local queue, actual message relay between two devices, sync-when-online.
- Person C: a basic classifier (even the TF-IDF fallback) and a bare-bones map dashboard that lists reports as pins.
- **Definition of done**: a person can fill in an SOS on phone A with no internet, phone A hands it to phone B over Bluetooth, phone B goes online and it appears on the dashboard.

### Phase 2 — Fill out the report types and the AI layer — **SHOULD**
- Person A: `PATCH /reports/{id}` for verification status, `POST /instructions` for responder pushback.
- Person B: the remaining report types (medical, resource, shelter, hazard, safe route), sync status UI, low-bandwidth/low-end-device polish.
- Person C: real BanglaBERT fine-tuning if time allows, deduplication/clustering, translation, corroboration scoring, dashboard filters and verification workflow.

### Phase 3 — Security hardening — **SHOULD**
- Person A + Person B together (this is the one place a short sync conversation matters): device keypair generation and message signing, backend-side signature verification, data-minimisation pass over what's actually being stored.

### Phase 4 — SMS/USSD gateway — **SHOULD**
- Person A: Twilio (or local aggregator) integration that maps an incoming SMS/USSD session to the same message schema and calls the same `POST /reports` endpoint the app uses. This is intentionally late in the plan — it reuses the contract and backend that already exist rather than being built in parallel with them.

### Phase 5 — Zero-cost LoRa simulation and hardware-readiness evidence — **SHOULD; physical hardware is LATER**

**Phase 5A — freeze the internal transport interface before parallel work**
- All three: agree on the frame version, byte budget measured against the pinned Meshtastic build/configuration, message identifier/digest, fragment numbering, maximum fragment count and reassembly size, timeout, and duplicate rules. Do not guess an Internet value for the packet budget; record the value produced by the chosen simulator/build.
- Person B: commit the short frame specification and golden encode/decode vectors under `/hardware/protocol` first. Merge that small interface-only commit to `main`, then update all three feature branches from `main`. After this checkpoint, only Person B edits `/hardware/protocol`; Persons A and C consume it read-only.
- This internal framing must decode to the frozen report schema byte-for-byte (or to its defined canonical serialization) so the original Ed25519 signature still verifies. No `/contracts` or public endpoint change is authorized by this phase.

**Person A / `feature/backend` — simulated LoRa uplink gateway**
- Work only in `/hardware/gateway` unless a demonstrated backend defect requires a separately reviewed backend fix.
- Implement a local bridge that receives application frames from a Meshtasticator node through Meshtastic's supported TCP/Python interface, performs bounded reassembly and digest validation, and submits the reconstructed report through the existing `POST /reports` path. Do not create a simulator-only public backend endpoint.
- Preserve backend idempotency and signature verification. Reject malformed, conflicting, expired, incomplete, or oversized frame sets, and do not log report text, exact coordinates, tokens, or keys.
- Test valid multi-fragment ingestion, duplicate and reordered fragments, corrupt digests, conflicting fragment metadata, timeout cleanup, bounded memory, repeated report submission, backend rejection, and temporary backend unavailability.

**Person B / `feature/client` — transport framing and sender**
- Work only in `/hardware/protocol` for the Phase 5 transport package; change `/mobile-client` only if a simulator-only export adapter is separately justified and kept behind a development flag.
- Implement the versioned codec and a CLI/test sender that accepts an existing signed Protidhoni report, serializes it deterministically, creates bounded Meshtastic application frames, and sends them through the simulator's supported interface. Never re-sign at a relay or put a private key in simulator configuration.
- Test exact encode/reassemble round trips for every report type, boundary sizes, Unicode/Bangla text, duplicate/reordered/missing/corrupt fragments, unsupported versions, invalid counts, and deterministic golden vectors shared with Person A.
- Do not claim that this validates the phone-to-radio BLE/USB link. That link remains a real-device acceptance test in the LATER phase.

**Person C / `feature/ai` — mesh scenarios, propagation study, and evidence**
- Work only in `/hardware/simulation`, `/hardware/evidence`, and `/hardware/README.md`; no AI-model or dashboard contract change is needed.
- Pin the Meshtasticator/Meshtastic versions and provide reproducible Docker/PowerShell commands for at least three simulated nodes, including a topology where sender and gateway require an intermediate relay.
- Automate and record a scenario matrix: direct delivery, required multi-hop delivery, duplicate reception, packet loss/retry, intermediate-node outage or partition, TTL/hop-limit exhaustion, and recovery. Report delivery result, route/hops where available, duplicate count, latency, and reassembly/backend outcome without sensitive report content.
- Save one representative Site Planner study with coordinates and radio/antenna assumptions, coverage or point-to-point exports, and the planner's limitations. Do not present predicted coverage as measured coverage and do not assert that a simulated radio setting is legally deployable without a current local regulatory check.
- Maintain `/hardware/README.md` with one-command setup where practical, exact version pins, expected output, troubleshooting, evidence provenance, and an honest hardware acceptance checklist/BOM for a future build. The BOM is documentation only; nobody is asked to purchase it.

**Definition of done**
- A signed report fixture traverses at least three simulated Meshtastic nodes with one required relay, is reconstructed unchanged, is accepted by the existing backend, and still passes the existing signature verification.
- Automated tests show safe behaviour for corruption, duplicates, reordering, missing fragments, limits, timeout, hop exhaustion, and backend failure. Existing backend, mobile, AI, dashboard, and contract test suites still pass.
- A clean-machine runbook reproduces the simulation, and `/hardware/evidence` records versioned commands, non-sensitive logs/metrics, topology, Site Planner exports, and limitations. Generated evidence is clearly separated from source and no result is fabricated or manually rewritten.
- The demo language says **"software/protocol simulation and hardware-readiness evidence"**, not **"hardware proven"**. Physical RF, electrical, power, antenna, enclosure, regulatory, and phone-to-radio tests remain LATER.

### Phase 6 — Integration testing, demo, and submission packaging — **MUST**
- All three: run the full path together (phone mesh + SMS + backend + AI + dashboard) at least twice before recording anything. If Phase 5 is included in the demo, also run the separate signed-report → simulated Meshtastic multi-hop → gateway → existing backend path twice.
- Record the 3-minute demo video, build the 6–10 slide deck, write the README (setup/run instructions — judges will actually try to run this), fill in every field Section 07 requires.
- Publish the Facebook post per Section 08's exact required content, submit the repo/post URLs through the site, and make sure the repository is public with an OSI-approved licence (you already have MIT — keep it) before the deadline. Don't squash your commit history right before submitting.

### LATER — the genuinely complete, post-hackathon version
If you keep building after 2 August, this is what "done" looks like at production scale, roughly in order:
- Build and validate the documented LoRa design on real, locally permitted hardware: phone-to-radio BLE/USB, ESP32/LoRa wiring, antennas, RF range/interference, power/solar runtime, thermals, and weatherproofed community relay nodes.
- iOS React Native bridge and device-validation pass. Nearby Connections supports iOS as well as Android, but this hackathon plan implements and validates its bridge on Android first.
- A properly fine-tuned, larger BanglaBERT model trained on a real, larger, ethically sourced dataset of crisis messages rather than a hackathon-sized sample.
- Formal partnership with a telco or the Bangladesh Fire Service/Red Crescent for real SMS short-code and IVR access rather than a Twilio trial number.
- A real, audited key-management and abuse-prevention system, reviewed by a security professional — the Bridgefy history (§9) is exactly the kind of thing that needs expert review before anyone relies on this in a real emergency.
- Formal accessibility and low-literacy testing (icon-based/voice-based UI for the IVR path).

---

## 8. Known pitfalls (grounded in what's already been tried)

- **Don't derive identity from the transport layer.** The Bridgefy research (independent security researchers broke it in 2021) found its core flaw was tying user identity to the Bluetooth connection itself — leading to impersonation and traceable social graphs. Your `sender_pubkey_hash` must come from a cryptographic key generated on the device, never from a MAC address, phone number, or Bluetooth session ID.
- **Don't skip deduplication and expect responders to cope.** Ushahidi's real deployments (Haiti earthquake: 30,000+ SMS reports in one month) showed that raw, unfiltered crowd reports overwhelm responders fast — clustering and corroboration aren't a "nice to have," they're the difference between a usable tool and a pile of noise.
- **Don't build in unnecessary anonymity.** Full anonymity sounds safer but makes verification, abuse-prevention, and the Code of Conduct's "no surveillance tooling but state what you collect" requirement harder to satisfy at once. Pseudonymous-but-signed is the right balance for this brief.
- **Don't wait until the end to test airplane mode.** The single most common way a "resilient offline" project fails its own judging criterion (Section 09: "does it degrade gracefully with no internet") is that it was only ever tested with Wi‑Fi on in a dev environment. Test with radios physically off, early and often.
- **Don't let AI/ML work block the rest of the team.** Model training can run in the background while Person A and B build; the AI service should have a trivial rule-based fallback (a few keyword checks) wired in from day one so the rest of the pipeline never sits idle waiting on a model.

---

## 9. Known limitations, said out loud (better for judges to hear it from you)

- The hackathon client is Android-first. Nearby Connections itself supports Android and iOS, but the Phase 0 React Native bridge and device testing cover Android only; an iOS bridge and device-validation pass remain post-hackathon work. State this plainly rather than letting a judge discover it.
- BLE/Wi‑Fi Direct range varies substantially by device and environment; true wide-area resilience needs another transport such as the proposed LoRa layer. Phase 5 validates its software path and models propagation only—no real RF range, antenna, power, electrical, regulatory, or phone-to-radio claim is made.
- A hackathon-scale fine-tuning dataset for BanglaBERT will be small; be upfront in your submission that classification accuracy is a proof of concept, not production-grade.
- The SMS/USSD gateway will most likely run on a trial/sandbox telco account rather than a real Bangladeshi short code — disclose this as a simulation of the intended integration.

---

## 10. Submission checklist, mapped to Section 07

- [ ] Title + one-line pitch (≤25 words)
- [ ] Track: Crisis Tech
- [ ] Problem statement (≤200 words)
- [ ] Solution description (≤400 words)
- [ ] Public repo link, README with setup/run instructions
- [ ] 3-minute demo video (unlisted YouTube/Drive)
- [ ] Live link or installable build (deployed dashboard URL + APK)
- [ ] Slide deck, 6–10 slides, PDF
- [ ] Tech stack and third-party components, including every AI tool used (BanglaBERT/BanglishBERT, any translation API, Twilio, Claude/other AI coding assistance if used — disclose all of it per Section 05)
- [ ] Public Facebook post URL, exact required content, hashtag `#JulyHackathon2026`
- [ ] Team member list with roles
- [ ] Repo public, OSI licence present (MIT already there), commit history shows real incremental work, not one final squash

---

*This document is long on purpose — you asked for the complete picture. Use the MUST/SHOULD/LATER tags to decide, hour by hour, how much of it you actually build before 30 July 23:59.*
