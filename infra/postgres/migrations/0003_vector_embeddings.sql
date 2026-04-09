CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS semantic_embeddings (
    embedding_id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    content_type    TEXT         NOT NULL,
    object_ref      TEXT         NOT NULL,
    label           TEXT         NOT NULL,
    content_text    TEXT         NOT NULL,
    content_hash    TEXT         NOT NULL,
    embedding       vector(1024) NOT NULL,
    metadata        JSONB        NOT NULL DEFAULT '{}',
    indexed_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS semantic_embeddings_type_ref_idx
    ON semantic_embeddings (content_type, object_ref);

CREATE INDEX IF NOT EXISTS semantic_embeddings_embedding_idx
    ON semantic_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS semantic_embeddings_hash_idx
    ON semantic_embeddings (content_type, object_ref, content_hash);
