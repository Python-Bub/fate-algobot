/**
 * Asynchronous post-trade logger. Writes to a daily JSONL file in
 * `hft/logs/`. All writes go through `process.nextTick` so the wire-path
 * thread never blocks on disk I/O.
 */
import { createWriteStream, mkdirSync, type WriteStream } from "node:fs";
import { resolve } from "node:path";

function logDir(): string {
  const root = process.env.FATE_ROOT || process.cwd().replace(/[/\\]hft$/, "");
  return resolve(root, "logs");
}

class AsyncJsonlLogger {
  private stream: WriteStream | null = null;
  private day = "";

  private ensureStream(): WriteStream {
    const today = new Date().toISOString().slice(0, 10);
    if (this.stream && today === this.day) return this.stream;
    if (this.stream) this.stream.end();
    const dir = logDir();
    try {
      mkdirSync(dir, { recursive: true });
    } catch {
      /* no-op: directory may already exist */
    }
    this.stream = createWriteStream(resolve(dir, `hft-${today}.jsonl`), { flags: "a" });
    this.day = today;
    return this.stream;
  }

  emit(event: string, payload: Record<string, unknown>): void {
    const line = JSON.stringify({ ts: Date.now(), event, ...payload }) + "\n";
    process.nextTick(() => {
      try {
        this.ensureStream().write(line);
      } catch {
        /* no-op: logging must never crash the algo */
      }
    });
  }
}

export const fileLogger = new AsyncJsonlLogger();

/** Tagged stdout helper that never throws. */
export const stdoutTag =
  (tag: string) =>
  (...args: unknown[]): void => {
    try {
      const stamp = new Date().toISOString();
      console.log(stamp, tag, ...args);
    } catch {
      /* no-op */
    }
  };
