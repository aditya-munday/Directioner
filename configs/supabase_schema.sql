-- Ultra-optimized Supabase schema for Directioner
-- Run this in your Supabase SQL Editor

-- ============================================================================
-- Enable required extensions
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- Conversation Memory Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS conversation_memory (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id VARCHAR(256) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    user_id VARCHAR(128),
    timestamp DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for conversation_memory
CREATE INDEX IF NOT EXISTS idx_conversation_memory_conv_id 
    ON conversation_memory(conversation_id);

CREATE INDEX IF NOT EXISTS idx_conversation_memory_conv_timestamp 
    ON conversation_memory(conversation_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_conversation_memory_user_id 
    ON conversation_memory(user_id);

-- Partial index for recent conversations (performance optimization)
CREATE INDEX IF NOT EXISTS idx_conversation_memory_recent 
    ON conversation_memory(conversation_id, timestamp DESC)
    WHERE timestamp > EXTRACT(EPOCH FROM NOW()) - 86400; -- Last 24 hours

-- ============================================================================
-- Semantic Memory Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS semantic_memory (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id VARCHAR(256) NOT NULL,
    text TEXT NOT NULL,
    timestamp DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for semantic_memory
CREATE INDEX IF NOT EXISTS idx_semantic_memory_conv_id 
    ON semantic_memory(conversation_id);

CREATE INDEX IF NOT EXISTS idx_semantic_memory_timestamp 
    ON semantic_memory(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_semantic_memory_conv_timestamp 
    ON semantic_memory(conversation_id, timestamp DESC);

-- ============================================================================
-- User Preferences Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(128) NOT NULL,
    key VARCHAR(256) NOT NULL,
    value TEXT NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT user_preferences_pkey PRIMARY KEY (user_id, key)
);

-- Index for user preferences
CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id 
    ON user_preferences(user_id);

-- ============================================================================
-- Performance Functions
-- ============================================================================

-- Function to auto-cleanup old conversation memory
CREATE OR REPLACE FUNCTION cleanup_old_conversation_memory(max_age_days INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM conversation_memory 
    WHERE timestamp < EXTRACT(EPOCH FROM NOW()) - (max_age_days * 86400);
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Function to auto-cleanup old semantic memory
CREATE OR REPLACE FUNCTION cleanup_old_semantic_memory(max_age_days INTEGER DEFAULT 7)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM semantic_memory 
    WHERE timestamp < EXTRACT(EPOCH FROM NOW()) - (max_age_days * 86400);
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Row Level Security (RLS)
-- ============================================================================

ALTER TABLE conversation_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE semantic_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

-- Policy for conversation memory (allow all for now, restrict per conversation_id in production)
CREATE POLICY "Allow all for conversation_memory" ON conversation_memory
    FOR ALL USING (true);

-- Policy for semantic memory
CREATE POLICY "Allow all for semantic_memory" ON semantic_memory
    FOR ALL USING (true);

-- Policy for user preferences
CREATE POLICY "Allow all for user_preferences" ON user_preferences
    FOR ALL USING (true);

-- ============================================================================
-- Row Count Limits (Prevent runaway tables)
-- ============================================================================

-- Add comment for table limits
COMMENT ON TABLE conversation_memory IS 'Max recommended rows: 1,000,000. Auto-cleanup via cleanup_old_conversation_memory()';
COMMENT ON TABLE semantic_memory IS 'Max recommended rows: 500,000. Auto-cleanup via cleanup_old_semantic_memory()';
COMMENT ON TABLE user_preferences IS 'Max recommended rows: 100,000';

-- ============================================================================
-- Statistics
-- ============================================================================

-- Grant usage to stats role
-- GRANT USAGE ON SCHEMA public TO anon, authenticated;
-- GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated;
-- GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;
