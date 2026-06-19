import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dataRoot = path.resolve(__dirname, "data", "mineru_api_output");
const processedRoot = path.resolve(__dirname, "data", "processed");

function sendJson(res, payload, status = 200) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(payload));
}

function sendText(res, text, contentType = "text/plain; charset=utf-8") {
  res.statusCode = 200;
  res.setHeader("Content-Type", contentType);
  res.end(text);
}

function safeChunkDir(chunkId) {
  if (!/^[A-Za-z0-9_.-]+$/.test(chunkId)) {
    return null;
  }
  const chunkDir = path.resolve(dataRoot, chunkId);
  if (!chunkDir.startsWith(dataRoot)) {
    return null;
  }
  return chunkDir;
}

function safeProcessedChunkDir(chunkId) {
  if (!/^[A-Za-z0-9_.-]+$/.test(chunkId)) {
    return null;
  }
  const chunkDir = path.resolve(processedRoot, chunkId);
  if (!chunkDir.startsWith(processedRoot)) {
    return null;
  }
  return chunkDir;
}

function contentTypeFor(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".png") return "image/png";
  if (ext === ".gif") return "image/gif";
  if (ext === ".webp") return "image/webp";
  if (ext === ".svg") return "image/svg+xml";
  if (ext === ".json") return "application/json; charset=utf-8";
  if (ext === ".md") return "text/markdown; charset=utf-8";
  return "application/octet-stream";
}

function localDataApiPlugin() {
  return {
    name: "local-data-api",
    configureServer(server) {
      server.middlewares.use("/processed", (req, res, next) => {
        const url = new URL(req.url || "/", "http://local");
        const parts = url.pathname.split("/").filter(Boolean);
        if (parts.length === 1) {
          const filePath = path.resolve(processedRoot, decodeURIComponent(parts[0]));
          if (filePath.startsWith(processedRoot) && fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
            res.statusCode = 200;
            res.setHeader("Content-Type", contentTypeFor(filePath));
            return fs.createReadStream(filePath).pipe(res);
          }
        }
        const [chunkId, ...rest] = parts;
        const chunkDir = chunkId ? safeProcessedChunkDir(chunkId) : null;
        if (!chunkDir || !rest.length) {
          return next();
        }
        const assetPath = path.resolve(chunkDir, ...rest.map(decodeURIComponent));
        if (!assetPath.startsWith(chunkDir) || !fs.existsSync(assetPath) || !fs.statSync(assetPath).isFile()) {
          return next();
        }
        res.statusCode = 200;
        res.setHeader("Content-Type", contentTypeFor(assetPath));
        return fs.createReadStream(assetPath).pipe(res);
      });

      server.middlewares.use("/api/chunks", (req, res, next) => {
        const url = new URL(req.url || "/", "http://local");
        const parts = url.pathname.split("/").filter(Boolean);

        if (parts.length === 0) {
          if (!fs.existsSync(dataRoot)) {
            return sendJson(res, { chunks: [] });
          }
          const chunks = fs
            .readdirSync(dataRoot, { withFileTypes: true })
            .filter((entry) => entry.isDirectory())
            .map((entry) => {
              const chunkDir = path.join(dataRoot, entry.name);
              const files = fs.readdirSync(chunkDir);
              const contentList = files.find((file) => file.endsWith("_content_list_v2.json")) || files.find((file) => file.endsWith("_content_list.json")) || null;
              return {
                chunk_id: entry.name,
                has_full_md: fs.existsSync(path.join(chunkDir, "full.md")),
                has_render_json: fs.existsSync(path.join(processedRoot, entry.name, "render.json")),
                content_list: contentList,
                image_count: fs.existsSync(path.join(chunkDir, "images"))
                  ? fs.readdirSync(path.join(chunkDir, "images")).length
                  : 0,
              };
            })
            .filter((chunk) => chunk.has_full_md || chunk.has_render_json);
          return sendJson(res, { chunks });
        }

        const [chunkId, resource, ...rest] = parts;
        const chunkDir = safeChunkDir(chunkId);
        if (!chunkDir || !fs.existsSync(chunkDir)) {
          return sendJson(res, { error: "chunk not found" }, 404);
        }

        if (resource === "full.md") {
          const markdownPath = path.join(chunkDir, "full.md");
          if (!fs.existsSync(markdownPath)) {
            return sendJson(res, { error: "full.md not found" }, 404);
          }
          return sendText(res, fs.readFileSync(markdownPath, "utf8"), "text/markdown; charset=utf-8");
        }

        if (resource === "render.json") {
          const processedChunkDir = safeProcessedChunkDir(chunkId);
          const renderPath = processedChunkDir ? path.join(processedChunkDir, "render.json") : null;
          if (!renderPath || !fs.existsSync(renderPath)) {
            return sendJson(res, { error: "render.json not found" }, 404);
          }
          return sendText(res, fs.readFileSync(renderPath, "utf8"), "application/json; charset=utf-8");
        }

        if (resource === "asset") {
          const assetPath = path.resolve(chunkDir, ...rest.map(decodeURIComponent));
          if (!assetPath.startsWith(chunkDir) || !fs.existsSync(assetPath)) {
            return sendJson(res, { error: "asset not found" }, 404);
          }
          res.statusCode = 200;
          res.setHeader("Content-Type", contentTypeFor(assetPath));
          return fs.createReadStream(assetPath).pipe(res);
        }

        return next();
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), localDataApiPlugin()],
  server: {
    watch: {
      ignored: [
        "**/.venv/**",
        "**/.git/**",
        "**/.cache/**",
        "**/data/**",
        "**/node_modules/**",
      ],
    },
  },
});
