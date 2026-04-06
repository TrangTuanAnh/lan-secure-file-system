package storagenode.crypto;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.security.SecureRandom;

/**
 * AES-256-CBC encryption/decryption for securing data in transit.
 *
 * Each encrypted payload is prefixed with a 16-byte IV:
 *   [16 bytes IV][encrypted data]
 */
public class AESCrypto {

    private static final String ALGORITHM = "AES";
    private static final String TRANSFORMATION = "AES/CBC/PKCS5Padding";
    private static final int IV_SIZE = 16;

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
     * Encrypt data with AES-256-CBC.
     * Returns: [16-byte IV][ciphertext]
     */
    public static byte[] encrypt(SecretKey key, byte[] plaintext) throws Exception {
        Cipher cipher = Cipher.getInstance(TRANSFORMATION);

        byte[] iv = new byte[IV_SIZE];
        new SecureRandom().nextBytes(iv);
        IvParameterSpec ivSpec = new IvParameterSpec(iv);

        cipher.init(Cipher.ENCRYPT_MODE, key, ivSpec);
        byte[] ciphertext = cipher.doFinal(plaintext);

        // Prepend IV
        byte[] result = new byte[IV_SIZE + ciphertext.length];
        System.arraycopy(iv, 0, result, 0, IV_SIZE);
        System.arraycopy(ciphertext, 0, result, IV_SIZE, ciphertext.length);
        return result;
    }

    /**
     * Decrypt data encrypted with AES-256-CBC.
     * Input format: [16-byte IV][ciphertext]
     */
    public static byte[] decrypt(SecretKey key, byte[] encryptedWithIv) throws Exception {
        if (encryptedWithIv.length < IV_SIZE) {
            throw new IllegalArgumentException("Encrypted data too short");
        }

        byte[] iv = new byte[IV_SIZE];
        System.arraycopy(encryptedWithIv, 0, iv, 0, IV_SIZE);

        byte[] ciphertext = new byte[encryptedWithIv.length - IV_SIZE];
        System.arraycopy(encryptedWithIv, IV_SIZE, ciphertext, 0, ciphertext.length);

        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(iv));
        return cipher.doFinal(ciphertext);
    }
}
