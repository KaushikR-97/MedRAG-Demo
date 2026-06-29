import compression from "compression";
import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const distDir = path.join(__dirname, "dist");
const port = Number(process.env.PORT || 5173);

const app = express();

app.disable("x-powered-by");
app.use(compression());
app.use((_req, res, next) => {
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader("Referrer-Policy", "no-referrer");
  next();
});

app.get("/health", (_req, res) => {
  res.json({ status: "ok", app: "medrag-india-web" });
});

app.use(
  express.static(distDir, {
    index: false,
    maxAge: "1h",
  }),
);

app.get("*", (_req, res) => {
  res.sendFile(path.join(distDir, "index.html"));
});

app.listen(port, "0.0.0.0", () => {
  console.log(`MedRAG India React UI listening on 0.0.0.0:${port}`);
});
