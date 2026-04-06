package storagenode.protocol;

import java.io.*;

/**
 * Binary frame codec for the data-plane protocol.
 *
 * Frame layout (all lengths are big-endian 4-byte int):
 *
 *   ┌──────────────────┬─────────────────┬──────────────────┬──────────────┐
 *   │ headerLen (4 B)  │ headerJson (N)  │ dataLen (4 B)    │ data (M)     │
 *   └──────────────────┴─────────────────┴──────────────────┴──────────────┘
 *
 *   headerLen : length of the JSON header in bytes
 *   headerJson: UTF-8 JSON containing "type" + metadata fields
 *   dataLen   : length of binary payload (0 if no payload)
 *   data      : raw binary payload (chunk bytes, encrypted key, etc.)
 *
 * This framing avoids packet-sticking issues on TCP streams.
 */
public class FrameCodec {

    private static final int MAX_HEADER_SIZE = 16 * 1024;       // 16 KB
    private static final int MAX_DATA_SIZE   = 2 * 1024 * 1024; // 2 MB (> chunk size 512 KB)

    // ────────── Write ──────────

    /**
     * Write a Message as a frame to the output stream.
     * Thread-safe per stream if callers synchronize on the stream.
     */
    public static void writeFrame(OutputStream out, Message msg) throws IOException {
        byte[] headerBytes = msg.headerToJson();
        byte[] data = msg.getData();
        int dataLen = (data == null) ? 0 : data.length;

        DataOutputStream dos = new DataOutputStream(out);
        dos.writeInt(headerBytes.length);
        dos.write(headerBytes);
        dos.writeInt(dataLen);
        if (dataLen > 0) {
            dos.write(data);
        }
        dos.flush();
    }

    // ────────── Read ──────────

    /**
     * Read one frame from the input stream. Blocks until a complete frame arrives.
     * Returns null if the stream is closed cleanly.
     *
     * @throws IOException on I/O error or protocol violation
     */
    public static Message readFrame(InputStream in) throws IOException {
        DataInputStream dis = new DataInputStream(in);

        // 1. Header length
        int headerLen;
        try {
            headerLen = dis.readInt();
        } catch (EOFException e) {
            return null; // stream closed
        }

        if (headerLen <= 0 || headerLen > MAX_HEADER_SIZE) {
            throw new IOException("Invalid header length: " + headerLen);
        }

        // 2. Header JSON
        byte[] headerBytes = new byte[headerLen];
        dis.readFully(headerBytes);

        // 3. Data length
        int dataLen = dis.readInt();
        if (dataLen < 0 || dataLen > MAX_DATA_SIZE) {
            throw new IOException("Invalid data length: " + dataLen);
        }

        // 4. Data
        byte[] data = null;
        if (dataLen > 0) {
            data = new byte[dataLen];
            dis.readFully(data);
        }

        // 5. Build Message
        Message msg = Message.fromHeaderJson(headerBytes);
        if (data != null) {
            msg.setData(data);
        }
        return msg;
    }
}
