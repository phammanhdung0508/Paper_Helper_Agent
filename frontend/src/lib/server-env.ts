import fs from "fs";
import path from "path";

const backendEnvCache = new Map<string, string>();
let backendEnvLoaded = false;

function loadBackendEnv() {
  if (backendEnvLoaded) return;
  backendEnvLoaded = true;

  const candidates = [
    path.resolve(process.cwd(), "../backend/.env"),
    path.resolve(process.cwd(), "backend/.env"),
  ];

  const envPath = candidates.find((candidate) => fs.existsSync(candidate));
  if (!envPath) return;

  try {
    const text = fs.readFileSync(envPath, "utf8");
    for (const rawLine of text.split(/\r?\n/)) {
      const line = rawLine.trim();
      if (!line || line.startsWith("#")) continue;
      const eq = line.indexOf("=");
      if (eq === -1) continue;
      const key = line.slice(0, eq).trim();
      let value = line.slice(eq + 1).trim();
      if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1);
      }
      backendEnvCache.set(key, value);
    }
  } catch {
    // Best-effort fallback for local dev only.
  }
}

export function serverEnv(name: string): string | undefined {
  if (process.env[name]) return process.env[name];
  loadBackendEnv();
  return backendEnvCache.get(name);
}

export function serverEnvFlag(name: string, defaultValue = false): boolean {
  const value = serverEnv(name);
  if (value == null || value === "") return defaultValue;
  return ["true", "1", "yes"].includes(value.toLowerCase());
}
