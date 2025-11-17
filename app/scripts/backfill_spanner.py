from __future__ import annotations

import warnings

from .backfill_supabase import main as _supabase_main


def main(argv: list[str] | None = None) -> int:
    warnings.warn(
        "backfill_spanner.py is deprecated. Use app.scripts.backfill_supabase instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _supabase_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
