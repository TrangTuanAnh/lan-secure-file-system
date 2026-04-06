package storagenode.storage;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;

import java.io.*;
import java.lang.reflect.Type;
import java.nio.file.*;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Logger;

/**
 * Content-addressable dedup registry.
 *
 * Maintains a mapping: sha256Whole -> stored file path.
 * Persisted to disk as JSON for crash recovery.
 *
 * When the Coordinator signals that a file with a given hash already exists,
 * the storage node can skip receiving data and just reference the existing object.
 */
public class DedupStore {

    private static final Logger LOG = Logger.getLogger(DedupStore.class.getName());
    private static final Gson GSON = new Gson();
    private static final Type MAP_TYPE = new TypeToken<Map<String, String>>() {}.getType();

    private final Path registryFile;
    private final ConcurrentHashMap<String, String> registry; // sha256 -> path

    public DedupStore(Path metaDir) throws IOException {
        Files.createDirectories(metaDir);
        this.registryFile = metaDir.resolve("dedup_registry.json");
        this.registry = new ConcurrentHashMap<>();
        load();
    }

    /** Check if a file with the given hash is already stored. */
    public boolean exists(String sha256) {
        String path = registry.get(sha256.toLowerCase());
        if (path == null) return false;
        // Verify the file still exists on disk
        if (!Files.exists(Paths.get(path))) {
            registry.remove(sha256.toLowerCase());
            return false;
        }
        return true;
    }

    /** Register a file in the dedup store. */
    public void register(String sha256, Path filePath) {
        registry.put(sha256.toLowerCase(), filePath.toString());
        save();
        LOG.info("Dedup registered: " + sha256 + " -> " + filePath);
    }

    /** Get the stored path for a hash. */
    public String getPath(String sha256) {
        return registry.get(sha256.toLowerCase());
    }

    /** Remove a hash from the registry. */
    public void remove(String sha256) {
        registry.remove(sha256.toLowerCase());
        save();
    }

    /** Number of entries in the registry. */
    public int size() {
        return registry.size();
    }

    // ── Persistence ──

    private void load() {
        if (!Files.exists(registryFile)) return;
        try (Reader r = Files.newBufferedReader(registryFile)) {
            Map<String, String> loaded = GSON.fromJson(r, MAP_TYPE);
            if (loaded != null) {
                registry.putAll(loaded);
                LOG.info("Loaded dedup registry: " + registry.size() + " entries");
            }
        } catch (IOException e) {
            LOG.warning("Failed to load dedup registry: " + e.getMessage());
        }
    }

    private synchronized void save() {
        try (Writer w = Files.newBufferedWriter(registryFile)) {
            GSON.toJson(registry, w);
        } catch (IOException e) {
            LOG.warning("Failed to save dedup registry: " + e.getMessage());
        }
    }
}
