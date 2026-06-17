import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../..");
const envPath = join(repoRoot, ".env");

if (existsSync(envPath)) {
  const contents = readFileSync(envPath, "utf8");
  for (const line of contents.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const separator = trimmed.indexOf("=");
    if (separator === -1) {
      continue;
    }

    const key = trimmed.slice(0, separator).trim();
    const value = trimmed.slice(separator + 1).trim().replace(/^["']|["']$/g, "");
    process.env[key] ??= value;
  }
} else {
  console.warn(`Root .env not found at ${envPath}`);
}

const argv = process.argv.slice(2);
if (argv[0] === "--") {
  argv.shift();
}

const [command, ...rawArgs] = argv;
if (!command) {
  console.error("Usage: node ../../scripts/with-root-env.mjs <command> [...args]");
  process.exit(1);
}

process.env.ROOT_ENV_FILE = envPath;

// Rewrites test-script placeholders to the discovered root .env path.
// Used by npm scripts that cannot know the absolute workspace path up front.
const args = rawArgs.map((arg) => (arg === "__ROOT_ENV_FILE__" ? envPath : arg));

const child = spawn(command, args, {
  env: process.env,
  shell: process.platform === "win32",
  stdio: "inherit",
});

// Mirrors the child process result back to the wrapper process.
// Used by npm so wrapped commands preserve their original exit status.
child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
  }
  process.exit(code ?? 1);
});
