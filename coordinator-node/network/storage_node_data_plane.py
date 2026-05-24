"""Thin data-plane client for Storage Node upload and download workflows."""

from __future__ import annotations

import hashlib
import json
import socket
import struct
from pathlib import Path
from typing import Any, Callable, Optional


class DataPlaneError(RuntimeError):
    """Raised when the Storage Node data plane rejects a request."""


def _parse_storage_address(storage_address: str) -> tuple[str, int]:
    host, _, port_text = storage_address.partition(":")
    if not host or not port_text:
        raise DataPlaneError(f"Invalid storage node address: {storage_address!r}")
    return host.strip(), int(port_text)


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        data = sock.recv(size - len(chunks))
        if not data:
            raise DataPlaneError("Storage node closed the connection unexpectedly.")
        chunks.extend(data)
    return bytes(chunks)


def _send_frame(sock: socket.socket, header: dict[str, Any], data: bytes = b"") -> None:
    encoded_header = json.dumps(header, separators=(",", ":")).encode("utf-8")
    sock.sendall(
        struct.pack(">I", len(encoded_header))
        + encoded_header
        + struct.pack(">I", len(data))
        + data
    )


def _recv_frame(sock: socket.socket) -> tuple[dict[str, Any], bytes]:
    header_len = struct.unpack(">I", _recv_exact(sock, 4))[0]
    header = json.loads(_recv_exact(sock, header_len).decode("utf-8"))
    data_len = struct.unpack(">I", _recv_exact(sock, 4))[0]
    payload = _recv_exact(sock, data_len) if data_len > 0 else b""
    return header, payload


class StorageNodeDataPlaneClient:
    """Implements supported upload/download flows over the Storage Node socket protocol."""

    def __init__(self, storage_address: str, timeout: float = 15.0) -> None:
        self._storage_address = storage_address
        self._timeout = timeout

    def upload_file(
        self,
        *,
        plan: dict[str, Any],
        file_path: str,
        uploader_id: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> dict[str, Any]:
        host, port = _parse_storage_address(plan.get("storageAddress") or self._storage_address)
        source_path = Path(file_path)
        file_bytes = source_path.read_bytes()
        whole_hash = hashlib.sha256(file_bytes).hexdigest()
        total_chunks = int(plan.get("totalChunks") or 1)
        chunk_size = int(plan.get("chunkSize") or 524288)
        expected_total_chunks = max(1, (len(file_bytes) + chunk_size - 1) // chunk_size)
        if total_chunks != expected_total_chunks:
            total_chunks = expected_total_chunks

        open_payload = {
            "type": "OPEN_UPLOAD",
            "sessionId": plan.get("sessionId"),
            "fileId": plan.get("fileId"),
            "fileName": source_path.name,
            "sha256Whole": whole_hash,
            "fileSize": len(file_bytes),
            "totalChunks": total_chunks,
            "uploaderId": uploader_id,
            "ticketNodeId": plan.get("ticketNodeId"),
            "ticketExpiry": plan.get("ticketExpiry"),
            "ticketSignature": plan.get("ticketSignature"),
        }

        with socket.create_connection((host, port), timeout=self._timeout) as sock:
            sock.settimeout(self._timeout)
            _send_frame(sock, open_payload)
            open_response, _ = _recv_frame(sock)
            if open_response.get("type") == "ERROR":
                raise DataPlaneError(open_response.get("message") or "OPEN_UPLOAD failed.")
            if open_response.get("dedup"):
                return open_response

            resumed_missing = open_response.get("missingChunks")
            if isinstance(resumed_missing, list) and resumed_missing:
                chunk_indexes = [int(index) for index in resumed_missing]
            else:
                chunk_indexes = list(range(total_chunks))

            for uploaded_count, chunk_index in enumerate(chunk_indexes, start=1):
                offset = chunk_index * chunk_size
                chunk = file_bytes[offset: offset + chunk_size]
                chunk_header = {
                    "type": "UPLOAD_CHUNK",
                    "sessionId": plan.get("sessionId"),
                    "chunkIndex": chunk_index,
                    "chunkHash": hashlib.sha256(chunk).hexdigest(),
                }
                _send_frame(sock, chunk_header, chunk)
                ack, _ = _recv_frame(sock)
                if ack.get("type") != "ACK_CHUNK" or ack.get("status") not in {"OK", None}:
                    raise DataPlaneError(
                        ack.get("message")
                        or ack.get("status")
                        or "Storage node rejected a chunk upload."
                    )
                if progress_callback is not None:
                    progress_callback(uploaded_count, len(chunk_indexes))

            _send_frame(sock, {"type": "FINALIZE_UPLOAD", "sessionId": plan.get("sessionId")})
            finalize_response, _ = _recv_frame(sock)
            if finalize_response.get("status") != "COMPLETED":
                raise DataPlaneError(
                    finalize_response.get("message")
                    or finalize_response.get("status")
                    or "Upload finalize failed."
                )
            return finalize_response

    def download_file(
        self,
        *,
        plan: dict[str, Any],
        save_path: str,
        downloader_id: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> dict[str, Any]:
        host, port = _parse_storage_address(plan.get("storageAddress") or self._storage_address)
        total_chunks = int(plan.get("totalChunks") or 0)
        expected_hash = str(plan.get("sha256Whole") or "")
        file_buffer = bytearray()
        download_complete = False

        with socket.create_connection((host, port), timeout=self._timeout) as sock:
            sock.settimeout(self._timeout)
            _send_frame(
                sock,
                {
                    "type": "OPEN_DOWNLOAD",
                    "sessionId": plan.get("sessionId"),
                    "fileId": plan.get("fileId"),
                    "sha256Whole": expected_hash,
                    "downloaderId": downloader_id,
                    "ticketNodeId": plan.get("ticketNodeId"),
                    "ticketExpiry": plan.get("ticketExpiry"),
                    "ticketSignature": plan.get("ticketSignature"),
                },
            )
            open_response, _ = _recv_frame(sock)
            if open_response.get("type") == "ERROR":
                raise DataPlaneError(open_response.get("message") or "OPEN_DOWNLOAD failed.")
            total_chunks = int(open_response.get("totalChunks") or total_chunks or 0)

            for index in range(total_chunks):
                _send_frame(sock, {"type": "REQUEST_CHUNK", "sessionId": plan.get("sessionId"), "chunkIndex": index})
                chunk_response, chunk_data = _recv_frame(sock)
                if chunk_response.get("type") != "DOWNLOAD_CHUNK":
                    raise DataPlaneError(chunk_response.get("message") or "Storage node returned invalid chunk data.")
                actual_hash = hashlib.sha256(chunk_data).hexdigest()
                if actual_hash != str(chunk_response.get("chunkHash") or ""):
                    raise DataPlaneError("Downloaded chunk hash mismatch.")
                file_buffer.extend(chunk_data)
                if progress_callback is not None:
                    progress_callback(index + 1, total_chunks)

                if index == total_chunks - 1:
                    complete_header, _ = _recv_frame(sock)
                    if complete_header.get("type") == "DOWNLOAD_COMPLETE":
                        download_complete = True

        if expected_hash and hashlib.sha256(file_buffer).hexdigest() != expected_hash:
            raise DataPlaneError("Downloaded file hash mismatch.")

        Path(save_path).write_bytes(bytes(file_buffer))
        return {"downloaded": True, "complete": download_complete, "size": len(file_buffer)}


__all__ = ["DataPlaneError", "StorageNodeDataPlaneClient"]
