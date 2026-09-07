-- MULTI_TENANT_DESIGN.md section 7 step 3 — prerequisite for the RLS layer.
--
-- Run ONCE as a superuser:
--     psql -d grosslo -f scripts/setup_app_role.sql
--
-- WHY THIS EXISTS. Row-level security is silently inert for superusers and for
-- any role with BYPASSRLS — they are exempt from every policy, FORCE or not.
-- The Homebrew default connection role (the developer's own OS user) is a
-- superuser, so leaving the application on it would mean the section 3.1
-- "belt and suspenders" second layer existed in the schema and enforced
-- nothing. Worse, the section 7 step 6 RLS test would still pass, because
-- zero cross-tenant rows come back either way when there is only one tenant's
-- data in front of you. A defence that cannot fail its own test is not a
-- defence. So the application connects as this deliberately unprivileged role.
--
-- FORCE ROW LEVEL SECURITY (set in review_queue._ensure_schema, not here) is
-- the matching half: a table's OWNER is exempt from its own policies unless
-- FORCE is set, and this role owns the tables it creates for each test schema.

CREATE ROLE grosslo_app LOGIN;

-- NOT a superuser, and explicitly NOBYPASSRLS. Stated rather than left to the
-- default, because the whole point of the role is what it cannot do.
ALTER ROLE grosslo_app NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB;

GRANT CONNECT ON DATABASE grosslo TO grosslo_app;

-- CREATE on the database: the test suite gives each module its own schema and
-- drops it between tests (review_queue._drop_schema), so the role must be able
-- to create and drop schemas it owns.
GRANT CREATE ON DATABASE grosslo TO grosslo_app;
GRANT USAGE, CREATE ON SCHEMA public TO grosslo_app;

-- Hand over the tables that already exist in public from steps 1-2. The role
-- owning them (rather than merely being granted on them) is what lets it run
-- _ensure_schema's ALTER TABLE ... FORCE ROW LEVEL SECURITY.
ALTER TABLE IF EXISTS public.tenants          OWNER TO grosslo_app;
ALTER TABLE IF EXISTS public.tenant_settings  OWNER TO grosslo_app;
ALTER TABLE IF EXISTS public.submissions      OWNER TO grosslo_app;
ALTER TABLE IF EXISTS public.submission_rows  OWNER TO grosslo_app;

-- Revoke PostgreSQL's default grants to PUBLIC. Every role in the cluster gets
-- CONNECT and TEMP on a new database, and USAGE on the public schema, without
-- anyone granting them — the same class of default-permissive assumption as
-- the superuser/BYPASSRLS problem above, found by sweeping for it rather than
-- by hitting it. Nothing here needs them.
REVOKE ALL ON DATABASE grosslo FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE grosslo TO grosslo_app;
GRANT USAGE  ON SCHEMA public     TO grosslo_app;

-- PRODUCTION: revoke this one. CREATE on the database exists ONLY so the test
-- suite can give each module its own schema and drop it between tests. A
-- production application process has no reason to create or drop schemas, and
-- leaving it is exactly the kind of privilege that gets inherited by accident
-- and never questioned:
--     REVOKE CREATE ON DATABASE grosslo FROM grosslo_app;
--     REVOKE CREATE ON SCHEMA public FROM grosslo_app;

-- NOT FIXED HERE, and worth knowing: this cluster's pg_hba.conf uses `trust`
-- for local and host connections (initdb's own default, and it warns about it
-- on creation). That means any local OS user can connect as ANY role,
-- including the superuser, with no password — so the unprivileged role above
-- is a guard against accident, not against a local attacker. Acceptable for a
-- development cluster on a laptop; a real deployment must use scram-sha-256
-- and give grosslo_app a password (ALTER ROLE grosslo_app PASSWORD '...') in
-- DATABASE_URL. Section 6's hosting decision is still open, so the production
-- pg_hba is not scripted here.
--
-- The application refuses to start if its connection role can bypass RLS
-- (review_queue.assert_rls_enforceable), so misconfiguring DATABASE_URL back
-- to a superuser fails loudly instead of silently disabling tenant isolation.
