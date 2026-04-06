package storagenode.protocol;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;

import java.lang.reflect.Type;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Represents a single protocol message (frame).
 *
 * A message has:
 *   - type       (MessageType)
 *   - headers    (JSON key-value pairs for metadata)
 *   - data       (optional binary payload, e.g. chunk bytes)
 */
public class Message {

    private static final Gson GSON = new Gson();
    private static final Type MAP_TYPE = new TypeToken<Map<String, Object>>() {}.getType();

    private MessageType type;
    private final Map<String, Object> headers;
    private byte[] data;

    public Message(MessageType type) {
        this.type = type;
        this.headers = new HashMap<>();
        this.data = null;
    }

    // ── Builder-style setters ──

    public Message set(String key, Object value) {
        headers.put(key, value);
        return this;
    }

    public Message setData(byte[] data) {
        this.data = data;
        return this;
    }

    public Message setType(MessageType type) {
        this.type = type;
        return this;
    }

    // ── Getters ──

    public MessageType getType() {
        return type;
    }

    public Map<String, Object> getHeaders() {
        return headers;
    }

    public byte[] getData() {
        return data;
    }

    public boolean hasData() {
        return data != null && data.length > 0;
    }

    // ── Typed header accessors ──

    public String getString(String key) {
        Object v = headers.get(key);
        return v == null ? null : v.toString();
    }

    public int getInt(String key) {
        Object v = headers.get(key);
        if (v instanceof Number) return ((Number) v).intValue();
        return Integer.parseInt(v.toString());
    }

    public long getLong(String key) {
        Object v = headers.get(key);
        if (v instanceof Number) return ((Number) v).longValue();
        return Long.parseLong(v.toString());
    }

    public boolean getBool(String key) {
        Object v = headers.get(key);
        if (v == null) return false;
        if (v instanceof Boolean) return (Boolean) v;
        return Boolean.parseBoolean(v.toString());
    }

    @SuppressWarnings("unchecked")
    public List<Double> getNumberList(String key) {
        Object v = headers.get(key);
        if (v instanceof List) return (List<Double>) v;
        return null;
    }

    // ── Serialization helpers ──

    /** Serialize the header portion (type + headers) to JSON bytes. */
    public byte[] headerToJson() {
        Map<String, Object> full = new HashMap<>(headers);
        full.put("type", type.name());
        return GSON.toJson(full).getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }

    /** Deserialize a header JSON into a Message (data is set separately). */
    public static Message fromHeaderJson(byte[] json) {
        String jsonStr = new String(json, java.nio.charset.StandardCharsets.UTF_8);
        Map<String, Object> map = GSON.fromJson(jsonStr, MAP_TYPE);

        String typeName = (String) map.remove("type");
        MessageType type = MessageType.fromString(typeName);
        if (type == null) {
            type = MessageType.ERROR;
        }

        Message msg = new Message(type);
        msg.headers.putAll(map);
        return msg;
    }

    // ── Convenience factory methods ──

    public static Message error(String code, String message) {
        return new Message(MessageType.ERROR)
                .set("code", code)
                .set("message", message);
    }

    public static Message ok(MessageType type) {
        return new Message(type).set("status", "OK");
    }

    @Override
    public String toString() {
        return "Message{type=" + type + ", headers=" + headers.keySet() +
               ", dataLen=" + (data == null ? 0 : data.length) + "}";
    }
}
