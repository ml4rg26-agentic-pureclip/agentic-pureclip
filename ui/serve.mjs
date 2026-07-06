// Production server for the Agentic PureCLIP dashboard.
//
// Serves the built SPA (build/client) and reverse-proxies /api/* to the Python
// JSON backend (scripts/monitor.py). Dependency-free — plain Node built-ins —
// so the runner needs no `npm install`, just `node serve.mjs`.
//
//   PORT=8888 API_TARGET=http://localhost:8890 node serve.mjs
//
import http from "node:http";
import { createReadStream, existsSync, statSync } from "node:fs";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env.PORT ?? 8888);
const API_TARGET = new URL(process.env.API_TARGET ?? "http://localhost:8890");
const DIST = process.env.DIST
  ? normalize(process.env.DIST)
  : join(fileURLToPath(new URL(".", import.meta.url)), "build", "client");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".woff2": "font/woff2",
  ".map": "application/json; charset=utf-8",
};

function proxyApi(req, res) {
  const opts = {
    protocol: API_TARGET.protocol,
    hostname: API_TARGET.hostname,
    port: API_TARGET.port,
    method: req.method,
    path: req.url,
    headers: { ...req.headers, host: API_TARGET.host },
  };
  const upstream = http.request(opts, (up) => {
    res.writeHead(up.statusCode ?? 502, up.headers);
    up.pipe(res);
  });
  upstream.on("error", (err) => {
    res.writeHead(502, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: `API backend unreachable: ${err.message}` }));
  });
  req.pipe(upstream);
}

function sendFile(res, path, status = 200) {
  res.writeHead(status, {
    "content-type": MIME[extname(path)] ?? "application/octet-stream",
    "cache-control": extname(path) === ".html" ? "no-cache" : "public, max-age=3600",
  });
  createReadStream(path).pipe(res);
}

const server = http.createServer((req, res) => {
  const url = (req.url ?? "/").split("?")[0];

  if (url === "/api" || url.startsWith("/api/")) return proxyApi(req, res);

  // Static asset, guarded against path traversal.
  const rel = normalize(decodeURIComponent(url)).replace(/^(\.\.[/\\])+/, "");
  const candidate = join(DIST, rel);
  if (candidate.startsWith(DIST) && existsSync(candidate) && statSync(candidate).isFile()) {
    return sendFile(res, candidate);
  }

  // SPA fallback — client-side routing owns everything else.
  const index = join(DIST, "index.html");
  if (existsSync(index)) return sendFile(res, index);

  res.writeHead(500, { "content-type": "text/plain" });
  res.end(`No build at ${DIST}. Run: npm run build`);
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`Dashboard UI on http://0.0.0.0:${PORT}  (api → ${API_TARGET.origin})`);
});
