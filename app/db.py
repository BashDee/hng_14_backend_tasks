from __future__ import annotations
from functools import lru_cache
from supabase import create_client, Client
from dotenv import load_dotenv

import os

load_dotenv()

def _get_supabase_url() -> str:
    supabase_url = os.getenv("SUPABASE_URL")
    if supabase_url:
        return supabase_url
    raise RuntimeError("SUPABASE_URL is required")


def _get_supabase_key() -> str:
    # Prefer explicit key name but keep service role compatibility.
    supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if supabase_key:
        return supabase_key
    raise RuntimeError("SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY) is required")


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    return create_client(_get_supabase_url(), _get_supabase_key())


def init_db() -> None:
    try:
        # Startup check: verify table access using the official client.
        get_supabase_client().table("profiles").select("id").limit(1).execute()
    except Exception as exc:
        raise RuntimeError(
            "Unable to access Supabase table 'profiles'. Ensure the table exists and credentials are valid."
        ) from exc
