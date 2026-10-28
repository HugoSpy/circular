#!/bin/sh
set -eu
export CIRCULAR_APP_PASSWORD="$(cat /run/secrets/database_password)"
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set ON_ERROR_STOP=1 <<'SQL'
\getenv app_password CIRCULAR_APP_PASSWORD
CREATE ROLE circular_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';
ALTER DATABASE circular OWNER TO circular_app;
ALTER SCHEMA public OWNER TO circular_app;
REVOKE ALL ON DATABASE circular FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE circular TO circular_app;
SQL
unset CIRCULAR_APP_PASSWORD
