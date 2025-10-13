CREATE SCHEMA IF NOT EXISTS rah_schema;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS rah_schema.physiology_program (
  program_code INT PRIMARY KEY,
  name TEXT NOT NULL,
  sex TEXT DEFAULT 'unisex' CHECK (sex IN ('male','female','unisex'))
);

CREATE TABLE IF NOT EXISTS rah_schema.rah_item (
  rah_id NUMERIC(5,2) PRIMARY KEY,
  details TEXT,
  category TEXT,
  description TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rah_schema.rah_item_program (
  rah_id NUMERIC(5,2) REFERENCES rah_schema.rah_item(rah_id) ON DELETE CASCADE,
  program_code INT REFERENCES rah_schema.physiology_program(program_code) ON DELETE CASCADE,
  PRIMARY KEY (rah_id, program_code)
);

CREATE TABLE IF NOT EXISTS rah_schema.corpus_doc (
  doc_id BIGSERIAL PRIMARY KEY,
  source TEXT,
  source_id TEXT,
  title TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rah_schema.corpus_chunk (
  chunk_id BIGSERIAL PRIMARY KEY,
  doc_id BIGINT REFERENCES rah_schema.corpus_doc(doc_id) ON DELETE CASCADE,
  chunk_index INT NOT NULL,
  content TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rah_schema.user_account (
  user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  username TEXT NOT NULL UNIQUE,
  email TEXT NOT NULL UNIQUE,
  branch TEXT,
  location TEXT,
  password_argon2 TEXT NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  deleted_at TIMESTAMPTZ
);