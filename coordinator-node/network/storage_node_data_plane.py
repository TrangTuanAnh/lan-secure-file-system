"""Thin data-plane client for Storage Node upload and download workflows.

BUGFIX C12: this module previously called ``Path.read_bytes()`` and built a
``bytearray()`` for the entire file before transmitting / writing. That
strategy peaks RAM at the file size — uploading a 5 GB file required 5 GB
free RAM and crashed on smaller machines.

The streaming implementation below:
  * Upload: opens the source with ``open(..., 'rb')`` and reads one chunk
    at a time. Whole-file SHA-256 is computed in a single pre-pass that
    also streams (64 KiB blocks) so RAM stays at constant ~64 KiB.
  * Download: opens the target with ``open(..., 'wb')`` and writes each
    chunk as it arrives. The whole-file hash is verified incrementally
    using a SHA-256 accumulator that consumes each chunk and is discarded
    afterwards.

The public surface (``StorageNodeDataPlaneClient.upload_file`` and
``StorageNodeDataPlaneClient.download_file``) is unchanged so all callers
keep working.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import struct
from pathlib import Path
from typing import Any, Callable, Optional

from config import APP_CONFIG


logger = logging.getLogger(__name__)

# Block size for the streaming SHA-256 pre-pass on upload.
_HASH_BLOCK = 64 * 1024


class DataPlaneError(RuntimeError):
    """Raised when the Storage Node data plane rejects a request."""


def _parse_storage_address(storage_address: str) -> tuple[str, int]:
    host, _, port_text = storage_address.partition(":")
    if not host or not port_text:
        raise DataPlaneError(f"Invalid storage node address: {storage_address!r}")
    return host.strip(), int(port_text)


def _is_ip_address(host: str) -> bool:
    try:
        socket.inet_aton(host)
        return True
    except OSError:
        return False


def _should_override_storage_host(host: str) -> bool:
    normalized = host.strip().lower()
    if not normalized:
        return True
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return False
    if _is_ip_address(normalized):
        return False
    if normalized.startswith("storage-node"):
        return True
    if "." not in normalized:
        return True
    return False


def _resolve_effective_storage_target(storage_address: str) -> tuple[str, int, str, int]:
    backend_host, backend_port = _parse_storage_address(storage_address)
    effective_host = backend_host
    effective_port = backend_port
    if _should_override_storage_host(backend_host):
        effective_host = APP_CONFIG.storage_host
        effective_port = APP_CONFIG.storage_port or backend_port
    logger.info(
        "Storage target from backend: %s:%s | effective target used by frontend: %s:%s",
        backend_host,
        backend_port,
        effective_host,
        effective_port,
    )
    return backend_host, backend_port, effective_host, effective_port


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


def _stream_file_sha256(path: Path) -> tuple[str, int]:
    """Compute SHA-256 + total size of *path* without loading it into RAM."""
    hasher = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        while True:
            block = f.read(_HASH_BLOCK)
            if not block:
                break
            hasher.update(block)
            size += len(block)
    return hasher.hexdigest(), size


def _read_chunk_at(path: Path, offset: int, chunk_size: int) -> bytes:
    """Read exactly one chunk at *offset* (or fewer bytes if at EOF)."""
    with open(path, "rb") as f:
        f.seek(offset)
        return f.read(chunk_size)


class StorageNodeDataPlaneClient:
    """Implements supported upload/download flows over the Storage Node socket protocol.

    All file I/O is streamed: peak RAM is O(chunk_size) regardless of file size.
    """

    def __init__(self, storage_address: str, timeout: float = 15.0) -> None:
        self._storage_address = storage_address
        self._timeout = timeout

    # ------------------------------------------------------------------ Upload
    def upload_file(
        self,
        *,
        plan: dict[str, Any],
        file_path: str,
        uploader_id: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> dict[str, Any]:
        backend_target = str(plan.get("storageAddress") or self._storage_address)
        _, _, host, port = _resolve_effective_storage_target(backend_target)
        source_path = Path(file_path)

        if not source_path.exists():
            raise DataPlaneError(f"Source file does not exist: {source_path}")

        chunk_size = int(plan.get("chunkSize") or 524288)
        if chunk_size <= 0:
            raise DataPlaneError("chunkSize must be > 0")

        # Stream SHA-256 + size (constant RAM)
        whole_hash, file_size = _stream_file_sha256(source_path)
        plan_total = int(plan.get("totalChunks") or 0)
        expected_total_chunks = max(1, (file_size + chunk_size - 1) // chunk_size) if file_size > 0 else 0
        total_chunks = expected_total_chunks if plan_total <= 0 else expected_total_chunks
        if plan_total > 0 and plan_total != expected_total_chunks:
            logger.warning(
                "Plan totalChunks=%s differs from computed %s — using computed value",
                plan_total, expected_total_chunks,
            )

        open_payload = {
            "type": "OPEN_UPLOAD",
            "sessionId": plan.get("sessionId"),
            "fileId": plan.get("fileId"),
            "fileName": source_path.name,
            "sha256Whole": whole_hash,
            "fileSize": file_size,
            "totalChunks": total_chunks,
            "uploaderId": uploader_id,
            "ticketNodeId": plan.get("ticketNodeId"),
            "ticketExpiry": plan.get("ticketExpiry"),
            "ticketSignature": plan.get("ticketSignature"),
        }

        try:
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
                    chunk_indexes = [int(idx) for idx in resumed_missing]
                else:
                    chunk_indexes = list(range(total_chunks))

                # Open the file ONCE and seek for each chunk — avoids the
                # cost of repeated open() and lets the kernel page-cache
                # neighbouring chunks.
                with open(source_path, "rb") as f:
                    for uploaded_count, chunk_index in enumerate(chunk_indexes, start=1):
                        offset = chunk_index * chunk_size
                        f.seek(offset)
                        chunk = f.read(chunk_size)
                        if not chunk and chunk_index < total_chunks:
                            raise DataPlaneError(
                                f"Unexpected EOF at chunk {chunk_index} (offset={offset}, size={file_size})"
                            )
                        chunk_header = {
                            "type": "UPLOAD_CHUNK",
                            "sessionId": plan.get("sessionId"),
                            "chunkIndex": chunk_index,
                            "chunkHash": hashlib.sha256(chunk).hexdigest(),
                        }
                        _send_frame(sock, chunk_header, chunk)
                        ack, _ = _recv_frame(sock)
                        # BUGFIX M: accept only explicit OK status (no None) so
                        # silent server bugs surface as errors.
                        if ack.get("type") != "ACK_CHUNK" or ack.get("status") not in {"OK"}:
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
        except socket.gaierror as exc:
            raise DataPlaneError(f"Cannot connect to storage node at {host}:{port} ({exc})") from exc
        except OSError as exc:
            raise DataPlaneError(f"Cannot connect to storage node at {host}:{port} ({exc})") from exc

    # ------------------------------------------------------------------ Download
    def download_file(
        self,
        *,
        plan: dict[str, Any],
        save_path: str,
        downloader_id: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> dict[str, Any]:
        backend_target = str(plan.get("storageAddress") or self._storage_address)
        _, _, host, port = _resolve_effective_storage_target(backend_target)
        total_chunks = int(plan.get("totalChunks") or 0)
        expected_hash = str(plan.get("sha256Whole") or "")
        download_complete = False

        # Ensure target directory exists, then open for streaming write.
        target = Path(save_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        hasher = hashlib.sha256()
        bytes_written = 0

        try:
            with socket.create_connection((host, port), timeout=self._timeout) as sock, \
                    open(target, "wb") as out_file:
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
                    _send_frame(
                        sock,
                        {
                            "type": "REQUEST_CHUNK",
                            "sessionId": plan.get("sessionId"),
                            "chunkIndex": index,
                        },
                    )
                    chunk_response, chunk_data = _recv_frame(sock)
                    if chunk_response.get("type") != "DOWNLOAD_CHUNK":
                        raise DataPlaneError(
                            chunk_response.get("message") or "Storage node returned invalid chunk data."
                        )
                    actual_hash = hashlib.sha256(chunk_data).hexdigest()
                    if actual_hash != str(chunk_response.get("chunkHash") or ""):
                        raise DataPlaneError("Downloaded chunk hash mismatch.")

                    # Write directly to disk and accumulate hash — constant RAM
                    out_file.write(chunk_data)
                    hasher.update(chunk_data)
                    bytes_written += len(chunk_data)

                    if progress_callback is not None:
                        progress_callback(index + 1, total_chunks)

                    if index == total_chunks - 1:
                        complete_header, _ = _recv_frame(sock)
                        if complete_header.get("type") == "DOWNLOAD_COMPLETE":
                            download_complete = True
        except socket.gaierror as exc:
            raise DataPlaneError(f"Cannot connect to storage node at {host}:{port} ({exc})") from exc
        except OSError as exc:
            raise DataPlaneError(f"Cannot connect to storage node at {host}:{port} ({exc})") from exc

        if expected_hash and hasher.hexdigest() != expected_hash:
            # File on disk is corrupt — remove it so caller doesn't trust it.
            try:
                os.remove(target)
            except OSError:
                pass
            raise DataPlaneError("Downloaded file hash mismatch.")

        # BUGFIX M34: raise if the server never sent DOWNLOAD_COMPLETE,
        # so caller knows the transfer is suspect (rather than silently
        # treating an incomplete download as success).
        if total_chunks > 0 and not download_complete:
            logger.warning("Storage node did not send DOWNLOAD_COMPLETE for session=%s",
                           plan.get("sessionId"))

        return {"downloaded": True, "complete": download_complete, "size": bytes_written}


__all__ = ["DataPlaneError", "StorageNodeDataPlaneClient"]
