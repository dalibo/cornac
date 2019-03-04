CREATE TYPE "db_instance_status" AS ENUM (
  'creating',
  'running',
  'stopped',
  'failed'
);

CREATE TABLE db_instances (
  id BIGSERIAL PRIMARY KEY,
  identifier TEXT UNIQUE,
  status db_instance_status NOT NULL,
  status_message TEXT,
  create_command JSONb,
  attributes JSONb
);
