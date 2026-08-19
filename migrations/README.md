# Catalog migrations

This is the single linear Alembic history for the PostgreSQL catalog. Applied
migrations are immutable. Tests run the history in isolated PostgreSQL schemas.

Set `LEO_DATABASE_URL` to override the local `leo_tracker` database URL.
