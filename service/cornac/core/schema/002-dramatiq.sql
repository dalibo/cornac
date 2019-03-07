-- Based on dramatiq-pg 0.3.0.
-- cf. https://gitlab.com/dalibo/dramatiq-pg/blob/2cd607ba53605ca2bbb09be361a1665da30cc3db/dramatiq_pg/schema.sql

CREATE SCHEMA dramatiq;

CREATE TYPE dramatiq."state" AS ENUM (
  'queued',
  'consumed',
  'rejected',
  'done'
);

CREATE TABLE dramatiq.queue(
  id BIGSERIAL PRIMARY KEY,
  queue_name TEXT NOT NULL DEFAULT 'default',
  message_id uuid UNIQUE,
  "state" dramatiq."state",
  mtime TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC'),
  -- message as encoded by dramatiq.
  message JSONB,
  "result" JSONB
);

-- Index state and mtime together to speed up deletion. This can also speed up
-- statistics when VACUUM ANALYZE is recent enough.
CREATE INDEX ON dramatiq.queue("state", mtime);
