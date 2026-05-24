"""End-to-end smoke test for STORAGE_AUTH manifest + reconciliation.

Drives the real coordinator socket on port 8081 with a fake storage node
(using the Python wire format) and verifies against the real Postgres DB
that a file the node does not report ends up with status='MISSING'.

Run from inside the coordinator container (it has all deps + DB access):
    docker compose exec coordinator python scripts/e2e_manifest_test.py
"""
import os
import socket
import sys
import time
import uuid

# Allow imports relative to the coordinator-server module root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # type: ignore
import psycopg2.extras  # type: ignore

from protocol.frame_codec import FrameCodec, FrameBuffer
from protocol.message import Message
from protocol.message_types import MessageType


COORDINATOR_HOST = os.environ.get("COORDINATOR_HOST", "coordinator")
COORDINATOR_STORAGE_PORT = int(os.environ.get("SERVER_STORAGE_PORT", "8081"))
SHARED_SECRET = os.environ.get("STORAGE_NODE_SECRET", "test-secret-12345")
NODE_ID = "fake-node-e2e"

PRESENT_SHA = "a" * 64        # node will report it
MISSING_SHA = "b" * 64        # DB row points here; node will NOT report it


def db_conn():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "postgres"),
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("DB_NAME", "coordinator"),
        user=os.environ.get("DB_USER", "coordinator_user"),
        password=os.environ.get("DB_PASSWORD", "secure_password"),
    )


def send_storage_auth(sock: socket.socket, manifest):
    msg = Message.create_request(
        MessageType.STORAGE_AUTH,
        {
            "secret": SHARED_SECRET,
            "nodeId": NODE_ID,
            "dataHost": "fake-node-e2e",
            "dataPort": 9999,
            "storageAddress": "fake-node-e2e:9999",
            "manifest": manifest,
        },
    )
    sock.sendall(FrameCodec.encode(msg.to_bytes()))


def read_one_message(sock: socket.socket, buf: FrameBuffer, timeout: float = 5.0) -> Message:
    sock.settimeout(timeout)
    deadline = time.time() + timeout
    while True:
        frame = buf.extract_frame()
        if frame is not None:
            return Message.from_bytes(frame)
        if time.time() >= deadline:
            raise TimeoutError("No frame within timeout")
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("Socket closed")
        buf.append(chunk)


def auth_and_check(manifest, expect_count_in_log):
    sock = socket.create_connection((COORDINATOR_HOST, COORDINATOR_STORAGE_PORT))
    buf = FrameBuffer()
    try:
        send_storage_auth(sock, manifest)
        resp = read_one_message(sock, buf)
        assert resp.type == MessageType.STORAGE_AUTH_RESPONSE, f"unexpected: {resp.type}"
        assert resp.payload.get("status") == "authenticated", resp.payload
        print(f"  ✓ STORAGE_AUTH ok (manifest size={len(manifest)})  node_id={resp.payload.get('nodeId')}")
        # Give the coordinator a moment to run reconciliation (it's synchronous
        # in the handler but our DB query races with it on a separate connection).
        time.sleep(0.5)
    finally:
        sock.close()


def insert_test_files(conn, owner_id, room_id):
    """Insert two file rows: one whose sha will be in the manifest, one whose won't."""
    with conn, conn.cursor() as cur:
        present_id = str(uuid.uuid4())
        missing_id = str(uuid.uuid4())
        for fid, sha, name in [
            (present_id, PRESENT_SHA, "present.bin"),
            (missing_id, MISSING_SHA, "lost.bin"),
        ]:
            cur.execute(
                """
                INSERT INTO files (
                    id, room_id, original_name, stored_name, version,
                    uploader_id, size_bytes, mime_type, sha256_whole,
                    total_chunks, chunk_size, status, storage_node_id, created_at
                ) VALUES (%s, %s, %s, %s, 1, %s, 100, 'application/octet-stream', %s,
                          1, 524288, 'READY', %s, NOW())
                """,
                (fid, room_id, name, f"{room_id}/{fid}", owner_id, sha, NODE_ID),
            )
        return present_id, missing_id


def ensure_fixtures(conn):
    """Create a throwaway user + room so file FKs are satisfied."""
    with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
        # User
        user_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO users (id, username, email, password_hash, global_role)
            VALUES (%s, %s, %s, %s, 'USER')
            """,
            (user_id, f"e2e-{user_id[:8]}", f"e2e-{user_id[:8]}@local", "x"),
        )
        # Room
        room_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO rooms (id, name, created_by) VALUES (%s, %s, %s)",
            (room_id, f"e2e-room-{room_id[:8]}", user_id),
        )
        return user_id, room_id


def get_status(conn, file_id):
    with conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM files WHERE id = %s", (file_id,))
        row = cur.fetchone()
        return row[0] if row else None


def cleanup(conn, file_ids, user_id, room_id):
    with conn, conn.cursor() as cur:
        for fid in file_ids:
            cur.execute("DELETE FROM files WHERE id = %s", (fid,))
        cur.execute("DELETE FROM rooms WHERE id = %s", (room_id,))
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))


def main():
    print(f"[1/5] Connect to Postgres + insert fixtures")
    conn = db_conn()
    user_id, room_id = ensure_fixtures(conn)
    present_id, missing_id = insert_test_files(conn, user_id, room_id)
    print(f"      present file={present_id}  sha={PRESENT_SHA[:8]}…")
    print(f"      missing file={missing_id}  sha={MISSING_SHA[:8]}…")

    try:
        print(f"[2/5] STORAGE_AUTH #1 — manifest contains BOTH shas, expect no MISSING")
        auth_and_check([PRESENT_SHA, MISSING_SHA], expect_count_in_log=2)
        assert get_status(conn, present_id) == "READY"
        assert get_status(conn, missing_id) == "READY"
        print("      ✓ both files still READY")

        print(f"[3/5] STORAGE_AUTH #2 — manifest only contains PRESENT, expect 1 MISSING")
        auth_and_check([PRESENT_SHA], expect_count_in_log=1)
        s_present = get_status(conn, present_id)
        s_missing = get_status(conn, missing_id)
        print(f"      present.status={s_present}  missing.status={s_missing}")
        assert s_present == "READY", f"expected READY, got {s_present}"
        assert s_missing == "MISSING", f"expected MISSING, got {s_missing}"
        print("      ✓ reconciliation flipped the unreported file to MISSING")

        print(f"[4/5] STORAGE_AUTH #3 — empty manifest, expect both MISSING (re-marking is idempotent)")
        # Reset the previously-flipped row back to READY to demonstrate this path.
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE files SET status='READY' WHERE id IN (%s, %s)", (present_id, missing_id))
        auth_and_check([], expect_count_in_log=2)
        assert get_status(conn, present_id) == "MISSING"
        assert get_status(conn, missing_id) == "MISSING"
        print("      ✓ empty manifest -> both flipped to MISSING")

        print(f"[5/5] All checks passed.")
    finally:
        cleanup(conn, [present_id, missing_id], user_id, room_id)
        conn.close()


if __name__ == "__main__":
    main()
