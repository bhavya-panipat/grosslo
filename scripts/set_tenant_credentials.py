"""
Admin CLI for attaching RazorpayX credentials to a tenant (step 4, section 3.5).

    python3 scripts/set_tenant_credentials.py --slug acme \\
        --key-id rzp_test_XXXX --key-secret YYYY --account-number 2323230000000000

Credentials go through secret_store, which REFUSES anything that is not a
RazorpayX test-mode key until a real KMS backend exists. That is not a
limitation to work around — section 3.5 requires "encrypted at rest" to name a
real mechanism, and the only backend available today does not encrypt. Storing
a live banking credential in it would make the claim false, so it is blocked
rather than warned about.

Like scripts/create_tenant.py, there is no HTTP route that reaches this
(section 6: admin-created only).
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import review_queue
import secret_store


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--key-id", required=True)
    ap.add_argument("--key-secret", required=True)
    ap.add_argument("--account-number")
    ap.add_argument("--schema", default="public")
    args = ap.parse_args()

    review_queue.DB_SCHEMA = args.schema
    tenant = review_queue.get_tenant_by_slug(args.slug)
    if tenant is None:
        print(f"error: no tenant with slug '{args.slug}' — create it first with "
              f"scripts/create_tenant.py", file=sys.stderr)
        return 1

    try:
        review_queue.set_tenant_razorpayx_credentials(
            tenant["id"], args.key_id, args.key_secret, args.account_number,
        )
    except secret_store.LiveCredentialRefused as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    where = "a real KMS" if secret_store.is_real_encryption() else (
        "the dev-plaintext backend, which does NOT encrypt — test-mode keys only")
    print(f"attached RazorpayX credentials to tenant {tenant['id']} ({tenant['slug']}), stored via {where}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
