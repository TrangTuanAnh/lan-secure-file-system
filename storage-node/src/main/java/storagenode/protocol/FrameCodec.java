package storagenode.protocol;

import java.io.*;

/**
 * Bộ mã hóa/giải mã khung nhị phân cho kênh truyền dữ liệu.
 *
 * TCP chỉ là một luồng byte liên tục, nên hệ thống tự chia dữ liệu thành khung:
 *
 *   ┌──────────────────┬─────────────────┬──────────────────┬──────────────┐
 *   │ headerLen (4 B)  │ headerJson (N)  │ dataLen (4 B)    │ data (M)     │
 *   └──────────────────┴─────────────────┴──────────────────┴──────────────┘
 *
 *   headerLen : độ dài phần đầu JSON
 *   headerJson: JSON UTF-8 chứa type và siêu dữ liệu
 *   dataLen   : độ dài dữ liệu nhị phân đi kèm
 *   data      : dữ liệu nhị phân thật, ví dụ khối file hoặc khóa mã hóa
 *
 * Cách đóng khung này giúp bên nhận biết chính xác một message bắt đầu/kết thúc ở đâu.
 */
public class FrameCodec {

    // Giới hạn phần đầu để tránh máy khách gửi siêu dữ liệu quá lớn.
    private static final int MAX_HEADER_SIZE = 16 * 1024;
    // Giới hạn phần dữ liệu; lớn hơn khối mặc định 512KB để đủ chứa dữ liệu mã hóa.
    private static final int MAX_DATA_SIZE   = 2 * 1024 * 1024;

    // ────────── GHI KHUNG RA SOCKET ──────────

    /**
     * Ghi một Message thành khung xuống OutputStream của TCP socket.
     * Thứ tự ghi: độ dài phần đầu, phần đầu JSON, độ dài dữ liệu, rồi dữ liệu nhị phân.
     */
    public static void writeFrame(OutputStream out, Message msg) throws IOException {
        // Phần đầu chứa type và các trường siêu dữ liệu như sessionId, chunkIndex, chunkHash.
        byte[] headerBytes = msg.headerToJson();
        // Data là phần nhị phân thật: khối file, khóa công khai, bản mã...
        byte[] data = msg.getData();
        int dataLen = (data == null) ? 0 : data.length;

        DataOutputStream dos = new DataOutputStream(out);
        // Ghi độ dài phần đầu trước để bên nhận biết cần đọc bao nhiêu byte phần đầu.
        dos.writeInt(headerBytes.length);
        dos.write(headerBytes);
        // Ghi độ dài dữ liệu trước khi ghi dữ liệu thật.
        dos.writeInt(dataLen);
        if (dataLen > 0) {
            dos.write(data);
        }
        // Đẩy dữ liệu xuống socket ngay.
        dos.flush();
    }

    // ────────── ĐỌC KHUNG TỪ SOCKET ──────────

    /**
     * Đọc một khung hoàn chỉnh từ InputStream của TCP socket.
     * Hàm này sẽ chờ đến khi đọc đủ phần đầu và dữ liệu.
     * Nếu socket đóng sạch thì trả về null.
     */
    public static Message readFrame(InputStream in) throws IOException {
        DataInputStream dis = new DataInputStream(in);

        // 1. Đọc độ dài phần đầu.
        int headerLen;
        try {
            headerLen = dis.readInt();
        } catch (EOFException e) {
            return null; // Socket đã đóng.
        }

        if (headerLen <= 0 || headerLen > MAX_HEADER_SIZE) {
            throw new IOException("Invalid header length: " + headerLen);
        }

        // 2. Đọc đúng số byte của phần đầu JSON.
        byte[] headerBytes = new byte[headerLen];
        dis.readFully(headerBytes);

        // 3. Đọc độ dài dữ liệu nhị phân đi kèm.
        int dataLen = dis.readInt();
        if (dataLen < 0 || dataLen > MAX_DATA_SIZE) {
            throw new IOException("Invalid data length: " + dataLen);
        }

        // 4. Nếu có dữ liệu thì đọc đủ số byte dữ liệu.
        byte[] data = null;
        if (dataLen > 0) {
            data = new byte[dataLen];
            dis.readFully(data);
        }

        // 5. Ghép phần đầu và dữ liệu thành Message để ClientHandler xử lý tiếp.
        Message msg = Message.fromHeaderJson(headerBytes);
        if (data != null) {
            msg.setData(data);
        }
        return msg;
    }
}
