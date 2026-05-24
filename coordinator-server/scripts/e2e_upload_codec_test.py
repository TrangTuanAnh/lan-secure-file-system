"""End-to-end test that exercises the Java→Python control-plane codec for
UPLOAD_COMPLETE + MANIFEST_DELTA by driving a real upload through the
Java storage node's data plane.

Run from inside the coordinator container:

    docker compose exec coordinator python scripts/e2e_upload_codec_test.py

Pre-conditions:
  - storage-node-1 is connected and authenticated (the long-lived
    control-plane connection is what we're trying to verify).
  - Shared secret matches docker-compose env (STORAGE_NODE_SECRET).
"""
import hashlib
import hmac
import json
import os
import socket
import struct
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # type: ignore


COORDINATOR_HOST = os.environ.get("COORDINATOR_HOST", "coordinator")
STORAGE_HOST = "storage-node-1"
STORAGE_PORT = 9001
SHARED_SECRET = os.environ.get("STORAGE_NODE_SECRET", "test-secret-12345")
NODE_ID = "storage-node-1"
TICKET_TTL = 600  # seconds


def db_conn():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "postgres"),
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("DB_NAME", "coordinator"),
        user=os.environ.get("DB_USER", "coordinator_user"),
        password=os.environ.get("DB_PASSWORD", "secure_password"),
    )


def hmac_sig(session_id, file_id, node_id, expiry):
    payload = f"{session_id}|{file_id}|{node_id}|{expiry}".encode()
    return hmac.new(SHARED_SECRET.encode(), payload, hashlib.sha256).hexdigest()


# ── Java FrameCodec wire format: [4B headerLen][headerJSON][4B dataLen][data] ──

def send_dp_frame(sock, header_obj, data=b""):
    header = json.dumps(header_obj, separators=(",", ":")).encode()
    sock.sendall(struct.pack(">I", len(header)) + header +
                 struct.pack(">I", len(data)) + data)


def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("short read (peer closed)")
        buf.extend(chunk)
    return bytes(buf)


def recv_dp_frame(sock):
    hlen = struct.unpack(">I", recv_exact(sock, 4))[0]
    header = json.loads(recv_exact(sock, hlen).decode())
    dlen = struct.unpack(">I", recv_exact(sock, 4))[0]
    data = recv_exact(sock, dlen) if dlen > 0 else b""
    return header, data


def ensure_fixtures(conn):
    with conn, conn.cursor() as cur:
        user_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO users (id, username, email, password_hash, global_role)
            VALUES (%s, %s, %s, %s, 'USER')
            """,
            (user_id, f"e2e-up-{user_id[:8]}", f"e2e-up-{user_id[:8]}@local", "x"),
        )
        room_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO rooms (id, name, created_by) VALUES (%s, %s, %s)",
            (room_id, f"e2e-up-room-{room_id[:8]}", user_id),
        )
        return user_id, room_id


def insert_uploading_file(conn, owner_id, room_id, file_id, sha, size, total_chunks, chunk_size):
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO files (
                id, room_id, original_name, stored_name, version,
                uploader_id, size_bytes, mime_type, sha256_whole,
                total_chunks, chunk_size, status, storage_node_id, created_at
            ) VALUES (%s, %s, %s, %s, 1, %s, %s, 'application/octet-stream', %s,
                      %s, %s, 'UPLOADING', %s, NOW())
            """,
            (file_id, room_id, "e2e_upload.bin", f"{room_id}/{file_id}",
             owner_id, size, sha, total_chunks, chunk_size, NODE_ID),
        )


def get_file_row(conn, file_id):
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT status, size_bytes, sha256_whole FROM files WHERE id = %s",
            (file_id,))
        return cur.fetchone()


def cleanup(conn, file_id, user_id, room_id):
    with conn, conn.cursor() as cur:
        cur.execute("DELETE FROM files WHERE id = %s", (file_id,))
        cur.execute("DELETE FROM rooms WHERE id = %s", (room_id,))
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))


def main():
    print("[1/6] Connect to Postgres and create user/room")
    conn = db_conn()
    user_id, room_id = ensure_fixtures(conn)

    # Build the payload: ~12 KB so we get a couple of chunks of 512 KB? No, 12 KB → 1 chunk
    payload = (b"E2E-CODEC-TEST-" * 1000)[:12_345]
    sha_hex = hashlib.sha256(payload).hexdigest()
    chunk_size = 524288   # coordinator default (512 KB)
    total_chunks = 1

    session_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    expiry = int(time.time()) + TICKET_TTL
    sig = hmac_sig(session_id, file_id, NODE_ID, expiry)

    print(f"      file_id   = {file_id}")
    print(f"      session   = {session_id}")
    print(f"      sha256    = {sha_hex[:16]}…  size={len(payload)}B")

    print("[2/6] Insert UPLOADING file row")
    insert_uploading_file(conn, user_id, room_id, file_id, sha_hex,
                          len(payload), total_chunks, chunk_size)
    assert get_file_row(conn, file_id)[0] == "UPLOADING"

    print(f"[3/6] Connect to Java storage node {STORAGE_HOST}:{STORAGE_PORT}")
    sock = socket.create_connection((STORAGE_HOST, STORAGE_PORT))
    sock.settimeout(10.0)

    try:
        print("[4/6] OPEN_UPLOAD + UPLOAD_CHUNK + FINALIZE_UPLOAD")
        send_dp_frame(sock, {
            "type": "OPEN_UPLOAD",
            "sessionId": session_id,
            "fileId": file_id,
            "fileName": "e2e_upload.bin",
            "sha256Whole": sha_hex,
            "fileSize": len(payload),
            "totalChunks": total_chunks,
            "uploaderId": user_id,
            "ticketNodeId": NODE_ID,
            "ticketExpiry": expiry,
            "ticketSignature": sig,
        })
        header, _ = recv_dp_frame(sock)
        print(f"      OPEN_UPLOAD_RESP: {header}")
        assert header.get("type") == "OPEN_UPLOAD_RESP", f"unexpected: {header}"
        # If dedup, we'd skip chunk upload — but the test uses a unique sha each run

        if not header.get("dedup"):
            chunk_hash = hashlib.sha256(payload).hexdigest()
            send_dp_frame(sock, {
                "type": "UPLOAD_CHUNK",
                "sessionId": session_id,
                "chunkIndex": 0,
                "chunkHash": chunk_hash,
            }, payload)
            ack, _ = recv_dp_frame(sock)
            print(f"      ACK_CHUNK: status={ack.get('status')} received={ack.get('received')}/{ack.get('total')}")
            assert ack.get("type") == "ACK_CHUNK" and ack.get("status") == "OK", ack

            send_dp_frame(sock, {"type": "FINALIZE_UPLOAD", "sessionId": session_id})
            fin, _ = recv_dp_frame(sock)
            print(f"      FINALIZE_RESP: status={fin.get('status')} scanStatus={fin.get('scanStatus')}")
            assert fin.get("status") == "COMPLETED", fin
        else:
            print("      (dedup hit — Java will still send UPLOAD_COMPLETE)")
    finally:
        sock.close()

    print("[5/6] Wait for coordinator to process UPLOAD_COMPLETE + MANIFEST_DELTA")
    # The Java node sends UPLOAD_COMPLETE then MANIFEST_DELTA on the long-lived
    # control plane connection. Give the coordinator a moment to apply both.
    deadline = time.time() + 10
    final_status = None
    while time.time() < deadline:
        row = get_file_row(conn, file_id)
        if row and row[0] == "READY":
            final_status = "READY"
            break
        time.sleep(0.3)

    print(f"      file.status = {final_status or get_file_row(conn, file_id)[0]}")
    assert final_status == "READY", \
        f"file did not transition to READY (still {get_file_row(conn, file_id)[0]}) — UPLOAD_COMPLETE may not have arrived"

    print("[6/6] PASS — UPLOAD_COMPLETE flowed through the new control-plane codec")
    cleanup(conn, file_id, user_id, room_id)
    conn.close()


if __name__ == "__main__":
    main()
