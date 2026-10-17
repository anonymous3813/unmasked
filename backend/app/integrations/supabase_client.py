"""Supabase client for pipeline persistence."""


class SupabaseClient:
    """Minimal Supabase wrapper for later finding and citation storage.

    Both pipelines will connect with the ``SUPABASE_URL`` and
    ``SUPABASE_KEY`` environment variables. This scaffold does not read
    secrets, query the database, or create schema.
    """

    url_env = "SUPABASE_URL"
    key_env = "SUPABASE_KEY"
