BEGIN;

ALTER TABLE reports ADD COLUMN IF NOT EXISTS verification_note TEXT;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS verification_updated_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'reports_verification_note_length'
          AND conrelid = 'reports'::regclass
    ) THEN
        ALTER TABLE reports ADD CONSTRAINT reports_verification_note_length
            CHECK (verification_note IS NULL OR char_length(verification_note) <= 1000);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS outbound_instructions (
    message_id UUID PRIMARY KEY REFERENCES reports(message_id) ON DELETE CASCADE,
    delivery_status TEXT NOT NULL DEFAULT 'queued' CHECK (delivery_status IN ('queued', 'delivered')),
    queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS outbound_instructions_delivery_idx
    ON outbound_instructions (delivery_status, queued_at);

COMMIT;
