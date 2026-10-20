#!/bin/sh
# Runs once on first boot of the postgres volume.
# Creates the NON-OWNER runtime role. Everything the app does goes through
# this role, so Postgres RLS always applies (see docs/ARCHITECTURE.md §RLS).
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${APP_DB_USER}') THEN
            CREATE ROLE ${APP_DB_USER} LOGIN PASSWORD '${APP_DB_PASSWORD}'
                NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
        END IF;
    END
    \$\$;
    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${APP_DB_USER};
    GRANT USAGE ON SCHEMA public TO ${APP_DB_USER};
    -- Table/sequence privileges are granted by the Alembic migration
    -- (it also sets default privileges for future tables).
EOSQL
