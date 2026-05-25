package storagenode.crypto;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.security.SecureRandom;
import java.util.Arrays;

/**
 * AES helpers for securing data in transit.
 *
 * Modern sessions use AES-256-GCM and prefix payloads as:
 *   ["GCM1"][12-byte nonce][ciphertext + 16-byte tag]
 *
 * Legacy RSA sessions can still use AES-256-CBC for backward compatibility:
 *   [16-byte IV][ciphertext]
 */
public class AESCrypto {

    private static final String ALGORITHM = "AES";
    private static final String CBC_TRANSFORMATION = "AES/CBC/PKCS5Padding";
    private static final String GCM_TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int CBC_IV_SIZE = 16;
    private static final int GCM_NONCE_SIZE = 12;
    private static final int GCM_TAG_BITS = 128;
    private static final byte[] GCM_MAGIC = new byte[] { 'G', 'C', 'M', '1' };

    /** Generate a random AES-256 key. */
    public static SecretKey generateKey() throws Exception {
        KeyGenerator kg = KeyGenerator.getInstance(ALGORITHM);
        kg.init(256, new SecureRandom());
        return kg.generateKey();
    }

    /** Reconstruct an AES key from raw bytes. */
    public static SecretKey keyFromBytes(byte[] keyBytes) {
        return new SecretKeySpec(keyBytes, ALGORITHM);
    }

    /** Get the raw bytes of a SecretKey. */
    public static byte[] keyToBytes(SecretKey key) {
        return key.getEncoded();
    }

    /**
     * Encrypt data with AES-256-GCM (modern default).
     * Returns: ["GCM1"][12-byte nonce][ciphertext + 16-byte tag]
     */
    public static byte[] encrypt(SecretKey key, byte[] plaintext) throws Exception {
        return encryptGcm(key, plaintext);
    }

    /**
     * Decrypt data. GCM payloads are detected by their "GCM1" prefix; otherwise
     * the method falls back to the legacy CBC payload format.
     */
    public static byte[] decrypt(SecretKey key, byte[] encrypted) throws Exception {
        if (isGcmPayload(encrypted)) {
            return decryptGcm(key, encrypted);
        }
        return decryptCbc(key, encrypted);
    }

    public static byte[] encryptGcm(SecretKey key, byte[] plaintext) throws Exception {
        Cipher cipher = Cipher.getInstance(GCM_TRANSFORMATION);

        byte[] nonce = new byte[GCM_NONCE_SIZE];
        new SecureRandom().nextBytes(nonce);
        GCMParameterSpec spec = new GCMParameterSpec(GCM_TAG_BITS, nonce);

        cipher.init(Cipher.ENCRYPT_MODE, key, spec);
        byte[] ciphertext = cipher.doFinal(plaintext);

        byte[] result = new byte[GCM_MAGIC.length + GCM_NONCE_SIZE + ciphertext.length];
        System.arraycopy(GCM_MAGIC, 0, result, 0, GCM_MAGIC.length);
        System.arraycopy(nonce, 0, result, GCM_MAGIC.length, GCM_NONCE_SIZE);
        System.arraycopy(ciphertext, 0, result, GCM_MAGIC.length + GCM_NONCE_SIZE, ciphertext.length);
        return result;
    }

    public static byte[] decryptGcm(SecretKey key, byte[] encrypted) throws Exception {
        if (!isGcmPayload(encrypted)) {
            throw new IllegalArgumentException("Invalid AES-GCM payload");
        }

        byte[] nonce = Arrays.copyOfRange(encrypted, GCM_MAGIC.length, GCM_MAGIC.length + GCM_NONCE_SIZE);
        byte[] ciphertext = Arrays.copyOfRange(encrypted, GCM_MAGIC.length + GCM_NONCE_SIZE, encrypted.length);

        Cipher cipher = Cipher.getInstance(GCM_TRANSFORMATION);
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(GCM_TAG_BITS, nonce));
        return cipher.doFinal(ciphertext);
    }

    public static byte[] encryptCbc(SecretKey key, byte[] plaintext) throws Exception {
        Cipher cipher = Cipher.getInstance(CBC_TRANSFORMATION);

        byte[] iv = new byte[CBC_IV_SIZE];
        new SecureRandom().nextBytes(iv);
        IvParameterSpec ivSpec = new IvParameterSpec(iv);

        cipher.init(Cipher.ENCRYPT_MODE, key, ivSpec);
        byte[] ciphertext = cipher.doFinal(plaintext);

        byte[] result = new byte[CBC_IV_SIZE + ciphertext.length];
        System.arraycopy(iv, 0, result, 0, CBC_IV_SIZE);
        System.arraycopy(ciphertext, 0, result, CBC_IV_SIZE, ciphertext.length);
        return result;
    }

    public static byte[] decryptCbc(SecretKey key, byte[] encryptedWithIv) throws Exception {
        if (encryptedWithIv.length < CBC_IV_SIZE) {
            throw new IllegalArgumentException("Encrypted data too short");
        }

        byte[] iv = new byte[CBC_IV_SIZE];
        System.arraycopy(encryptedWithIv, 0, iv, 0, CBC_IV_SIZE);

        byte[] ciphertext = new byte[encryptedWithIv.length - CBC_IV_SIZE];
        System.arraycopy(encryptedWithIv, CBC_IV_SIZE, ciphertext, 0, ciphertext.length);

        Cipher cipher = Cipher.getInstance(CBC_TRANSFORMATION);
        cipher.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(iv));
        return cipher.doFinal(ciphertext);
    }

    public static boolean isGcmPayload(byte[] payload) {
        if (payload == null || payload.length < GCM_MAGIC.length + GCM_NONCE_SIZE + 1) {
            return false;
        }
        for (int i = 0; i < GCM_MAGIC.length; i++) {
            if (payload[i] != GCM_MAGIC[i]) {
                return false;
            }
        }
        return true;
    }
}
