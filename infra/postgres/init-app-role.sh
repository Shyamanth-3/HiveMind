#!/bin/sh
# Runs ONCE, when the database volume is first created (docker-entrypoint-initdb.d).
# Creates the unprivileged role the API and Scheduler connect as: it can read and write rows, but cannot create,
# alter or drop tables, cannot create roles or extensions, and is not a superuser. Schema changes are made only by
# the one-shot `migrate` job, which connects as the owner role (POSTGRES_USER).
set -eu
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD must be set}"
psql -v ON_ERROR_STOP=1 -v app_password="$APP_DB_PASSWORD" --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE ROLE hivemind_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'app_password';
REVOKE ALL ON DATABASE :"DBNAME" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"DBNAME" TO hivemind_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO hivemind_app;
-- tables created later by the migration job (as the owner role) become read/write for the application role
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO hivemind_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO hivemind_app;
SQL
