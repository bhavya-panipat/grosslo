"""
Admin CLI for provisioning a tenant — the ONLY way tenants get created.

MULTI_TENANT_DESIGN.md section 6 resolved this: admin-created only, no
self-serve signup in 1.1. There is deliberately no HTTP route that reaches
review_queue.create_tenant(), so 1.1 does not have to design authz, rate
limiting, or slug-collision handling for a public creation endpoint before the
pilot-customer stage needs one.

    python3 scripts/create_tenant.py --slug acme --name "Acme Corp"
    python3 scripts/create_tenant.py --list

The slug is the subdomain from section 3.3 ({slug}.grosslo.app). This does NOT
create the tenant_settings row holding that tenant's HR/Finance access-code
hashes — wiring login up to per-tenant codes is step 5's job, not step 3's.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg

import review_queue


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", help="subdomain slug, e.g. 'acme'")
    ap.add_argument("--name", help="display name, e.g. 'Acme Corp'")
    ap.add_argument("--schema", default="public")
    ap.add_argument("--list", action="store_true", help="list existing tenants and exit")
    args = ap.parse_args()

    review_queue.DB_SCHEMA = args.schema

    if args.list:
        tenants = review_queue.list_tenants()
        if not tenants:
            print("no tenants")
        for t in tenants:
            print(f"  {t['id']:>4}  {t['slug']:<20} {t['display_name']}")
        return 0

    if not args.slug or not args.name:
        ap.error("--slug and --name are both required (or use --list)")

    try:
        tenant = review_queue.create_tenant(args.slug, args.name)
    except psycopg.errors.UniqueViolation:
        print(f"error: slug '{args.slug}' is already taken", file=sys.stderr)
        return 1
    print(f"created tenant {tenant['id']}: {tenant['slug']} ({tenant['display_name']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
