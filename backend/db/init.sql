CREATE EXTENSION IF NOT EXISTS postgis;

-- Phase 0 storage foundation. Phase 1 applies ingestion logic and indexes only
-- after the contracts have been exercised by every client.
CREATE TABLE IF NOT EXISTS reports (
    message_id UUID PRIMARY KEY,
    sender_pubkey_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    report_type TEXT NOT NULL,
    language TEXT NOT NULL,
    payload JSONB NOT NULL,
    location GEOGRAPHY(POINT, 4326),
    raw_message JSONB NOT NULL,
    priority TEXT,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    corroboration_count INTEGER NOT NULL DEFAULT 0 CHECK (corroboration_count >= 0),
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (report_type IN ('SOS', 'MEDICAL_NEED', 'RESOURCE_NEED', 'SAFETY_STATUS', 'SHELTER_INFO', 'HAZARD_UPDATE', 'SAFE_ROUTE', 'INSTRUCTION')),
    CHECK (language IN ('bn', 'en')),
    CHECK (priority IS NULL OR priority IN ('critical', 'high', 'medium', 'low')),
    CHECK (verification_status IN ('unverified', 'corroborated', 'verified', 'disputed'))
);

CREATE INDEX IF NOT EXISTS reports_created_at_idx ON reports (created_at DESC);
CREATE INDEX IF NOT EXISTS reports_location_idx ON reports USING GIST (location);

-- Phase 2 responder-owned audit fields. IF NOT EXISTS makes this safe both for
-- fresh databases and for the existing Phase 1 development volume.
ALTER TABLE reports ADD COLUMN IF NOT EXISTS verification_note TEXT;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS verification_updated_at TIMESTAMPTZ;

ALTER TABLE reports DROP CONSTRAINT IF EXISTS reports_verification_note_length;
ALTER TABLE reports ADD CONSTRAINT reports_verification_note_length
    CHECK (verification_note IS NULL OR char_length(verification_note) <= 1000);

CREATE TABLE IF NOT EXISTS outbound_instructions (
    message_id UUID PRIMARY KEY REFERENCES reports(message_id) ON DELETE CASCADE,
    delivery_status TEXT NOT NULL DEFAULT 'queued' CHECK (delivery_status IN ('queued', 'delivered')),
    queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS outbound_instructions_delivery_idx
    ON outbound_instructions (delivery_status, queued_at);
