"""Database integration module for Directioner."""

from directioner.database.supabase_client import (
    # Exceptions
    SupabaseError,
    SupabaseConnectionError,
    SupabaseQueryError,
    SupabaseRateLimitError,
    SupabaseCircuitOpenError,
    # Core classes
    SupabaseCircuitBreaker,
    SupabasePool,
    BatchProcessor,
    QueryOptimizer,
    # Functions
    get_supabase_pool,
    get_batch_processor,
    get_query_optimizer,
    initialize_supabase,
    close_supabase,
    get_supabase_stats,
)

__all__ = [
    # Exceptions
    "SupabaseError",
    "SupabaseConnectionError",
    "SupabaseQueryError",
    "SupabaseRateLimitError",
    "SupabaseCircuitOpenError",
    # Core classes
    "SupabaseCircuitBreaker",
    "SupabasePool",
    "BatchProcessor",
    "QueryOptimizer",
    # Functions
    "get_supabase_pool",
    "get_batch_processor",
    "get_query_optimizer",
    "initialize_supabase",
    "close_supabase",
    "get_supabase_stats",
]
