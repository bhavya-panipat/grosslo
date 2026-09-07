"""
Admin CLI for provisioning a tenant — the ONLY way tenants get created.

MULTI_TENANT_DESIGN.md section 6 resolved this: admin-created only, no
self-serve signup in 1.1. There is deliberately no HTTP route that reaches
review_queue.create_tenant(), so 1.1 does not have to design authz, rate
limiting, or slug-collision handling for a public creation endpoint before the
pilot-customer stage needs one.

    python3 scripts/create_tenant.py --slug acme --name "Acme Corp"
    python3 scripts/create_tenant.py --list

The slug is the subdomain from section 3.3 ({slug}.grosslo.app) — that is how
requests resolve to this tenant, so it is not cosmetic. The HR/Finance access
codes are stored HASHED (3.3), and are required: there is no global fallback
pair any more, so a tenant without them cannot be logged into at all.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg

import review_queue
from auth import hash_access_code, TENANT_DOMAIN_SUFFIX


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", help="subdomain slug, e.g. 'acme'")
    ap.add_argument("--name", help="display name, e.g. 'Acme Corp'")
    ap.add_argument("--hr-code", help="this tenant's HR access code")
    ap.add_argument("--finance-code", help="this tenant's Finance access code")
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
    if not args.hr_code or not args.finance_code:
        ap.error("--hr-code and --finance-code are required: a tenant with no settings row "
                 "cannot be logged into at all, by design (there is no global fallback pair)")

    try:
        tenant = review_queue.create_tenant(args.slug, args.name)
    except psycopg.errors.UniqueViolation:
        print(f"error: slug '{args.slug}' is already taken", file=sys.stderr)
        return 1
    review_queue.create_tenant_settings(
        tenant["id"], hash_access_code(args.hr_code), hash_access_code(args.finance_code))
    print(f"created tenant {tenant['id']}: {tenant['slug']} ({tenant['display_name']})")
    print(f"  sign in at https://{tenant['slug']}.{TENANT_DOMAIN_SUFFIX}")
    print(f"  access codes stored as hashes, not plaintext (3.3)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
