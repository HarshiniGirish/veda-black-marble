from __future__ import annotations

import os
import sys


def _emit_token(token: str) -> int:
    token = token.strip()
    if not token:
        print("ERROR: Earthdata token is empty", file=sys.stderr)
        return 1
    # Token only on stdout — do not print elsewhere.
    sys.stdout.write(token)
    return 0


def main() -> int:
    secret_name = (os.environ.get("EARTHDATA_SECRET_NAME") or "EARTHDATA_TOKEN").strip()
    if not secret_name:
        secret_name = "EARTHDATA_TOKEN"

    existing = (os.environ.get("EARTHDATA_TOKEN") or "").strip()
    if existing:
        print(f"Using EARTHDATA_TOKEN from environment (secret name unused)", file=sys.stderr)
        return _emit_token(existing)

    try:
        from maap.maap import MAAP
    except ImportError:
        print(
            "ERROR: maap-py is not installed, so MAAP secrets cannot be read. "
            "For local testing export EARTHDATA_TOKEN; for DPS install maap-py "
            "and create a secret with maap.secrets.add_secret("
            f"'{secret_name}', '<token>').",
            file=sys.stderr,
        )
        return 1

    try:
        maap = MAAP()
        value = maap.secrets.get_secret(secret_name)
    except Exception as exc:  # noqa: BLE001 — surface any maap-py/network failure
        print(
            f"ERROR: failed to read MAAP secret '{secret_name}': {exc}",
            file=sys.stderr,
        )
        return 1

    if isinstance(value, dict) and value.get("code") == 404:
        print(
            f"ERROR: MAAP secret '{secret_name}' not found. "
            f"Create it in ADE with:\n"
            f"  from maap.maap import MAAP\n"
            f"  MAAP().secrets.add_secret('{secret_name}', '<your-earthdata-token>')",
            file=sys.stderr,
        )
        return 1

    if isinstance(value, dict) and ("message" in value or "code" in value):
        print(
            f"ERROR: unexpected response reading MAAP secret '{secret_name}': "
            f"code={value.get('code')} message={value.get('message')}",
            file=sys.stderr,
        )
        return 1

    print(f"Loaded Earthdata token from MAAP secret '{secret_name}'", file=sys.stderr)
    return _emit_token(str(value))


if __name__ == "__main__":
    raise SystemExit(main())
