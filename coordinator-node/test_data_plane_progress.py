"""Test thanh tiến độ ở tầng data-plane mà KHÔNG cần Storage Node thật.

Dùng một storage-node giả lập trong bộ nhớ (bỏ qua mạng + mã hóa) để chạy
upload_file() và download_file(), rồi kiểm tra mọi lần gọi progress_callback.

Chạy:  python coordinator-node/test_data_plane_progress.py
(chạy từ thư mục gốc repo, hoặc python test_data_plane_progress.py trong coordinator-node)
"""
import hashlib
import json
import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import network.storage_node_data_plane as dp


def _frame(header, data=b""):
    h = json.dumps(header).encode("utf-8")
    return struct.pack(">I", len(h)) + h + struct.pack(">I", len(data)) + data


class FakeSock:
    """Giả lập giao thức khung của Storage Node theo kiểu request -> response."""

    def __init__(self, file_bytes, chunk_size):
        self._out = bytearray()
        self._in = bytearray()
        self._file = file_bytes
        self._chunk = chunk_size
        self._total = max(1, (len(file_bytes) + chunk_size - 1) // chunk_size)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def settimeout(self, *_):
        pass

    def close(self):
        pass

    def sendall(self, data):
        self._in.extend(data)
        while True:
            if len(self._in) < 4:
                return
            hlen = struct.unpack(">I", self._in[:4])[0]
            if len(self._in) < 8 + hlen:
                return
            header = json.loads(self._in[4:4 + hlen].decode("utf-8"))
            dlen = struct.unpack(">I", self._in[4 + hlen:8 + hlen])[0]
            if len(self._in) < 8 + hlen + dlen:
                return
            del self._in[:8 + hlen + dlen]
            self._respond(header)

    def _respond(self, header):
        t = header.get("type")
        if t == "OPEN_UPLOAD":
            self._out.extend(_frame({"type": "OPEN_UPLOAD_OK"}))
        elif t == "UPLOAD_CHUNK":
            self._out.extend(_frame({"type": "ACK_CHUNK", "status": "OK"}))
        elif t == "FINALIZE_UPLOAD":
            self._out.extend(_frame({"status": "COMPLETED", "fileId": "f1"}))
        elif t == "OPEN_DOWNLOAD":
            self._out.extend(_frame({"type": "OPEN_DOWNLOAD_OK",
                                     "totalChunks": self._total,
                                     "fileSize": len(self._file)}))
        elif t == "REQUEST_CHUNK":
            i = int(header["chunkIndex"])
            chunk = self._file[i * self._chunk:(i + 1) * self._chunk]
            self._out.extend(_frame({"type": "DOWNLOAD_CHUNK",
                                     "chunkHash": hashlib.sha256(chunk).hexdigest()}, chunk))
            if i == self._total - 1:
                self._out.extend(_frame({"type": "DOWNLOAD_COMPLETE"}))

    def recv(self, n):
        if not self._out:
            return b""
        take = self._out[:n]
        del self._out[:n]
        return bytes(take)


class FakeCrypto:
    def encrypt(self, b):
        return b

    def decrypt(self, b):
        return b


def run():
    chunk_size = 262144
    data = os.urandom(700_000)
    whole = hashlib.sha256(data).hexdigest()
    total = max(1, (len(data) + chunk_size - 1) // chunk_size)
    dp._negotiate_crypto = lambda sock: FakeCrypto()
    ok = True

    fake_up = FakeSock(data, chunk_size)
    dp.socket.create_connection = lambda *a, **k: fake_up
    src = os.path.join(tempfile.gettempdir(), "prog_src.bin")
    open(src, "wb").write(data)
    up = []
    client = dp.StorageNodeDataPlaneClient("127.0.0.1:9001")
    client.upload_file(plan={"sessionId": "s1", "fileId": "f1", "chunkSize": chunk_size, "totalChunks": total},
                       file_path=src, uploader_id="u1",
                       progress_callback=lambda c, t, b, tb: up.append((c, t, b, tb)))

    fake_dn = FakeSock(data, chunk_size)
    dp.socket.create_connection = lambda *a, **k: fake_dn
    dst = os.path.join(tempfile.gettempdir(), "prog_dst.bin")
    dn = []
    client.download_file(plan={"sessionId": "s1", "fileId": "f1", "sha256Whole": whole, "totalChunks": total},
                         save_path=dst, downloader_id="u1",
                         progress_callback=lambda c, t, b, tb: dn.append((c, t, b, tb)))

    print("file size:", len(data), " chunk:", chunk_size, " total chunks:", total)
    print("UPLOAD progress calls:")
    [print("  ", c) for c in up]
    print("DOWNLOAD progress calls:")
    [print("  ", c) for c in dn]

    if len(up) != total:
        ok = False; print("FAIL up count", len(up))
    if up[-1] != (total, total, len(data), len(data)):
        ok = False; print("FAIL up final", up[-1])
    pct = [round(c / t * 100) for c, t, *_ in up]
    if pct != sorted(pct):
        ok = False; print("FAIL up % not monotonic", pct)
    if len(dn) != total:
        ok = False; print("FAIL dn count", len(dn))
    if dn[-1] != (total, total, len(data), len(data)):
        ok = False; print("FAIL dn final", dn[-1])
    got = open(dst, "rb").read()
    if hashlib.sha256(got).hexdigest() != whole:
        ok = False; print("FAIL dn integrity")
    else:
        print("downloaded integrity: OK")
    print("=>", "ALL PROGRESS ASSERTIONS PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())
