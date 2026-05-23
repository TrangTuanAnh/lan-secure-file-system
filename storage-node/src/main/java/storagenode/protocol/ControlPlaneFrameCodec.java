package storagenode.protocol;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;

import java.io.*;
import java.lang.reflect.Type;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Frame codec for the control-plane protocol that speaks the Coordinator's
 * (Python) wire format:
 *
 *   ┌──────────────────┬───────────────────────────────────────────┐
 *   │ length (4 B BE)  │ JSON {"type": ..., "payload": {...},      │
 *   │                  │       "requestId": "..."}  (UTF-8)        │
 *   └──────────────────┴───────────────────────────────────────────┘
 *
 * No separate binary data segment — the control plane is JSON-only.
 *
 * On the Java side we keep the existing {@link Message} model (flat
 * {@code headers} map). This codec maps to/from the Python shape by:
 *   - on write: nesting all header entries under a "payload" key, and
 *               pulling "requestId" out as a top-level field if present;
 *   - on read:  flattening the "payload" object back into headers, and
 *               storing "requestId" as a header so callers can read it.
 */
public class ControlPlaneFrameCodec {

    private static final Gson GSON = new Gson();
    private static final Type MAP_TYPE = new TypeToken<Map<String, Object>>() {}.getType();

    private static final int MAX_MESSAGE_SIZE = 10 * 1024 * 1024; // 10 MB, matches Python

    public static void writeFrame(OutputStream out, Message msg) throws IOException {
        byte[] json = encodeMessage(msg);
        if (json.length > MAX_MESSAGE_SIZE) {
            throw new IOException("Control-plane message exceeds max size: " + json.length);
        }
        DataOutputStream dos = new DataOutputStream(out);
        dos.writeInt(json.length);
        dos.write(json);
        dos.flush();
    }

    public static Message readFrame(InputStream in) throws IOException {
        DataInputStream dis = new DataInputStream(in);
        int length;
        try {
            length = dis.readInt();
        } catch (EOFException e) {
            return null; // peer closed cleanly
        }
        if (length <= 0 || length > MAX_MESSAGE_SIZE) {
            throw new IOException("Invalid control-plane frame length: " + length);
        }
        byte[] body = new byte[length];
        dis.readFully(body);
        return decodeMessage(body);
    }

    // ── Serialization helpers (exposed for tests) ──

    static byte[] encodeMessage(Message msg) {
        Map<String, Object> envelope = new LinkedHashMap<>();
        envelope.put("type", msg.getType().name());

        Map<String, Object> headers = new HashMap<>(msg.getHeaders());
        Object requestId = headers.remove("requestId");

        envelope.put("payload", headers);
        if (requestId != null) {
            envelope.put("requestId", requestId.toString());
        }
        return GSON.toJson(envelope).getBytes(StandardCharsets.UTF_8);
    }

    static Message decodeMessage(byte[] body) throws IOException {
        String jsonStr = new String(body, StandardCharsets.UTF_8);
        Map<String, Object> envelope = GSON.fromJson(jsonStr, MAP_TYPE);
        if (envelope == null) {
            throw new IOException("Empty control-plane frame");
        }

        Object typeObj = envelope.get("type");
        if (typeObj == null) {
            throw new IOException("Control-plane frame missing 'type'");
        }
        MessageType type = MessageType.fromString(typeObj.toString());
        if (type == null) {
            type = MessageType.ERROR;
        }

        Message msg = new Message(type);

        Object payloadObj = envelope.get("payload");
        if (payloadObj instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> payload = (Map<String, Object>) payloadObj;
            // Python's ERROR responses nest under {"error": {"code","message"}};
            // surface code/message at the header level so existing callers
            // (msg.getString("code"), msg.getString("message")) keep working.
            // Other types (e.g. TICKET_INVALID) may have a plain string under
            // "error" — leave those as a normal header value.
            Object err = payload.get("error");
            boolean errorEnvelope = (type == MessageType.ERROR && err instanceof Map);
            if (errorEnvelope) {
                @SuppressWarnings("unchecked")
                Map<String, Object> errMap = (Map<String, Object>) err;
                for (Map.Entry<String, Object> e : errMap.entrySet()) {
                    msg.set(e.getKey(), e.getValue());
                }
            }
            for (Map.Entry<String, Object> e : payload.entrySet()) {
                if (errorEnvelope && "error".equals(e.getKey())) continue;
                msg.set(e.getKey(), e.getValue());
            }
        }

        Object requestId = envelope.get("requestId");
        if (requestId != null) {
            msg.set("requestId", requestId.toString());
        }
        return msg;
    }

    /**
     * Helper for callers that want to attach a fresh requestId to an outgoing
     * request. Idempotent if one is already set.
     */
    public static Message ensureRequestId(Message msg) {
        if (msg.getString("requestId") == null) {
            msg.set("requestId", UUID.randomUUID().toString());
        }
        return msg;
    }
}
