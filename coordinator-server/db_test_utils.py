"""Shared helpers for database integration tests."""


TEST_TABLES = (
    "audit_logs",
    "share_tokens",
    "scan_reports",
    "files",
    "room_members",
    "rooms",
    "users",
)


def cleanup_database(database):
    """Remove integration-test data while respecting foreign-key relations."""
    table_list = ", ".join(TEST_TABLES)
    database.execute_update(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE")
