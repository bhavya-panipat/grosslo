"""
Creates a tenant's first `owner` user directly (Phase 1.2 step 3).

Two reasons this exists rather than everything going through the HTTP routes:

  1. manage_users is held only by `owner`, so the first owner of a tenant
     cannot be created through /api/users — there is nobody to authorise it.
     Every bootstrap path needs exactly one door that does not require an
     existing session, and this is it.
  2. A tenant provisioned after the shared access codes are gone (§3.3's
     bootstrap only fires for tenants that HAVE codes) has no other way in.

Deliberately an admin CLI and not a public endpoint, consistent with 1.1's
resolved decision that tenant provisioning is admin-created only — a public
"create the first owner" route is a tenant-takeover primitive if it is ever
reachable a moment too long.

Usage:
    python3 scripts/create_owner.py --slug acme \\
        --email ceo@acme.test --name "Ada Lovelace" --password '...'

Omit --password to create the account without one; the user then cannot log in
locally until an owner sets it, which is the right state for an account
provisioned ahead of its person.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import review_queue


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True, help="tenant slug, e.g. acme")
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", required=True, help="display name")
    ap.add_argument("--password", help="omit to be prompted; pass '' for no password")
    ap.add_argument("--role", action="append", default=None,
                    help="repeatable; defaults to owner")
    ap.add_argument("--schema", default="public")
    args = ap.parse_args()

    review_queue.DB_SCHEMA = args.schema
    review_queue.init_db()

    tenant = review_queue.get_tenant_by_slug(args.slug)
    if tenant is None:
        print(f"error: no tenant with slug {args.slug!r}. Create it first with "
              f"scripts/create_tenant.py", file=sys.stderr)
        return 1

    password = args.password
    if password is None:
        password = getpass.getpass("Password (blank for none): ")

    roles = args.role or ["owner"]
    try:
        user = review_queue.create_user(
            tenant["id"], args.email, args.name, roles,
            password=password or None,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"created user {user['id']} <{user['email']}> in tenant "
          f"{tenant['slug']} (id {tenant['id']})")
    print(f"  roles        : {', '.join(user['roles'])}")
    print(f"  can log in   : {user['has_password']}"
          + ("" if user["has_password"] else "  (no password set — an owner must set one)"))
    total = review_queue.count_users(tenant["id"])
    if total > 1:
        # §3.3's bootstrap only fires at zero users, so this is worth saying out
        # loud rather than leaving the operator to infer it.
        print(f"  note         : tenant now has {total} users; the shared access-code "
              f"bootstrap no longer applies to it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
