"""Regression tests cho tính năng resume (data-plane client) và các ca biên đã vá.

Mỗi kịch bản dưới đây FAIL trên bản trước khi vá và PASS sau khi vá:
  A. Rớt mạng ngay sau khi node finalize (trước khi client đọc COMPLETED) ->
     OPEN_UPLOAD lại trả dedup -> phải coi là THÀNH CÔNG, không raise.
  B. Resume khi node đã nhận đủ 100% khối (missingChunks=[]) -> client KHÔNG
     gửi lại khối nào, đi thẳng tới FINALIZE.
  C. ".part" sót lại lớn hơn file thật -> phải reset (truncate + băm lại) rồi
     tải lại đúng, thay vì hash mismatch.
  D. Download bị rớt giữa chừng -> nối lại qua ".part" và tải tiếp ĐÚNG phần
     đuôi còn thiếu (không tải lại từ khối 0), ghép ra file khớp bản gốc.

Dùng socket giả trong bộ nhớ, không cần Storage Node thật.
Chạy:  python coordinator-node/test_resume_fixes.py
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


class FakeUL:
    """Storage Node giả cho UPLOAD. open_resp = dict trả khi OPEN_UPLOAD.
    finalize: 'completed' | 'drop'. Đếm số khung UPLOAD_CHUNK nhận được."""

    def __init__(self, open_resp, finalize="completed"):
        self.open_resp = open_resp
        self.finalize = finalize
        self._out = bytearray()
        self._in = bytearray()
        self._dropped = False
        self.chunk_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def settimeout(self, *_):
        pass

    def close(self):
        pass

    def sendall(self, data):
        if self._dropped:
            return
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

    def _respond(self, h):
        t = h.get("type")
        if t == "OPEN_UPLOAD":
            self._out.extend(_frame(self.open_resp))
        elif t == "UPLOAD_CHUNK":
            self.chunk_count += 1
            self._out.extend(_frame({"type": "ACK_CHUNK", "status": "OK"}))
        elif t == "FINALIZE_UPLOAD":
            if self.finalize == "drop":
                self._dropped = True  # node đã commit nhưng rớt trước khi gửi COMPLETED
                return
            self._out.extend(_frame({"status": "COMPLETED", "fileId": "f1"}))

    def recv(self, n):
        if not self._out:
            return b""
        take = self._out[:n]
        del self._out[:n]
        return bytes(take)


class FakeDL:
    """Storage Node giả cho DOWNLOAD.

    serve=None  -> phục vụ mọi khối.
    serve={..}  -> chỉ phục vụ các chỉ số trong tập; gặp khối ngoài tập sẽ "rớt"
                   (recv trả b"" -> _ConnectionLost) để mô phỏng mất kết nối.
    """

    def __init__(self, file_bytes, chunk_size, serve=None):
        self._file = file_bytes
        self._chunk = chunk_size
        self._total = max(1, (len(file_bytes) + chunk_size - 1) // chunk_size)
        self._serve = set(range(self._total)) if serve is None else set(serve)
        self._out = bytearray()
        self._in = bytearray()
        self._dropped = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def settimeout(self, *_):
        pass

    def close(self):
        pass

    def sendall(self, data):
        if self._dropped:
            return
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

    def _respond(self, h):
        t = h.get("type")
        if t == "OPEN_DOWNLOAD":
            self._out.extend(_frame({"type": "OPEN_DOWNLOAD_OK",
                                     "totalChunks": self._total, "fileSize": len(self._file)}))
        elif t == "REQUEST_CHUNK":
            i = int(h["chunkIndex"])
            if i not in self._serve:
                self._dropped = True  # mô phỏng rớt kết nối giữa chừng
                return
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


def _src(name, data):
    p = os.path.join(tempfile.gettempdir(), name)
    with open(p, "wb") as f:
        f.write(data)
    return p


def _rm(*paths):
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass


def test_finalize_race_dedup_is_success():
    dp._negotiate_crypto = lambda sock: FakeCrypto()
    data = os.urandom(250)
    src = _src("fixA_src.bin", data)
    try:
        fakes = iter([FakeUL({"type": "OPEN_UPLOAD_OK"}, finalize="drop"),
                      FakeUL({"dedup": True, "fileId": "f1"})])
        dp.socket.create_connection = lambda *a, **k: next(fakes)
        client = dp.StorageNodeDataPlaneClient("127.0.0.1:9001", retry_backoff=0)
        res = client.upload_file(plan={"sessionId": "s1", "fileId": "f1", "chunkSize": 100, "totalChunks": 3},
                                 file_path=src, uploader_id="u1")
        assert res.get("status") == "COMPLETED", res
    finally:
        _rm(src)


def test_empty_missing_skips_resend():
    dp._negotiate_crypto = lambda sock: FakeCrypto()
    data = os.urandom(250)
    src = _src("fixB_src.bin", data)
    try:
        a2 = FakeUL({"resumed": True, "missingChunks": []}, finalize="completed")
        fakes = iter([FakeUL({"type": "OPEN_UPLOAD_OK"}, finalize="drop"), a2])
        dp.socket.create_connection = lambda *a, **k: next(fakes)
        client = dp.StorageNodeDataPlaneClient("127.0.0.1:9001", retry_backoff=0)
        res = client.upload_file(plan={"sessionId": "s1", "fileId": "f1", "chunkSize": 100, "totalChunks": 3},
                                 file_path=src, uploader_id="u1")
        assert res.get("status") == "COMPLETED", res
        assert a2.chunk_count == 0, f"phải gửi lại 0 khối, đã gửi {a2.chunk_count}"
    finally:
        _rm(src)


def test_oversized_part_resets_and_downloads():
    dp._negotiate_crypto = lambda sock: FakeCrypto()
    chunk = 100
    data = os.urandom(250)  # 3 khối: 100,100,50
    whole = hashlib.sha256(data).hexdigest()
    dst = os.path.join(tempfile.gettempdir(), "fixC_dst.bin")
    part, meta = dst + ".part", dst + ".part.json"
    _rm(dst, part, meta)
    try:
        with open(part, "wb") as f:
            f.write(os.urandom(350))  # .part lớn hơn file thật (250)
        with open(meta, "w", encoding="utf-8") as f:
            json.dump({"sha256Whole": whole, "chunkSize": chunk}, f)
        fake = FakeDL(data, chunk)
        dp.socket.create_connection = lambda *a, **k: fake
        client = dp.StorageNodeDataPlaneClient("127.0.0.1:9001", retry_backoff=0)
        res = client.download_file(plan={"sessionId": "s1", "fileId": "f1", "sha256Whole": whole,
                                         "totalChunks": 3, "chunkSize": chunk},
                                   save_path=dst, downloader_id="u1")
        got = open(dst, "rb").read() if os.path.exists(dst) else b""
        assert got == data, f"file sai: len={len(got)} (mong đợi 250)"
        assert res.get("downloaded"), res
    finally:
        _rm(dst, part, meta)


def test_partial_resume_download():
    """Rớt sau khối 1 -> attempt 2 nối lại từ khối 2 (KHÔNG tải lại từ 0) -> file đúng."""
    dp._negotiate_crypto = lambda sock: FakeCrypto()
    chunk = 100
    data = os.urandom(450)  # 5 khối
    whole = hashlib.sha256(data).hexdigest()
    dst = os.path.join(tempfile.gettempdir(), "fixD_dst.bin")
    part, meta = dst + ".part", dst + ".part.json"
    _rm(dst, part, meta)
    try:
        fakes = iter([FakeDL(data, chunk, serve={0, 1}),   # phục vụ {0,1} rồi rớt
                      FakeDL(data, chunk, serve={2, 3, 4})])  # nối lại phần đuôi
        dp.socket.create_connection = lambda *a, **k: next(fakes)
        client = dp.StorageNodeDataPlaneClient("127.0.0.1:9001", retry_backoff=0)
        res = client.download_file(plan={"sessionId": "s1", "fileId": "f1", "sha256Whole": whole,
                                         "totalChunks": 5, "chunkSize": chunk},
                                   save_path=dst, downloader_id="u1")
        got = open(dst, "rb").read() if os.path.exists(dst) else b""
        assert got == data, f"file sai: len={len(got)} (mong đợi 450)"
        assert res.get("downloaded"), res
    finally:
        _rm(dst, part, meta)


def _run_standalone():
    tests = [
        ("finalize-race dedup -> success", test_finalize_race_dedup_is_success),
        ("empty missingChunks -> no re-send", test_empty_missing_skips_resend),
        ("oversized .part -> reset + correct", test_oversized_part_resets_and_downloads),
        ("partial-resume download -> correct tail", test_partial_resume_download),
    ]
    ok = True
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except AssertionError as e:
            ok = False
            print(f"FAIL {name}: {e}")
    print("=>", "ALL RESUME-FIX TESTS PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_run_standalone())
