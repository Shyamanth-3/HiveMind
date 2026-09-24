// =============================================================================
// HiveMind — TelemetryClient: a reconnecting WebSocket client (framework-free, testable)
//
//  - states: connecting | connected | reconnecting | disconnected | error   (transport only)
//  - bounded exponential backoff with jitter (1s, 2s, 4s ... capped), never a tight loop
//  - every reconnect asks the server to resume after the last event we applied (?last_event_id=)
//  - watchdog: no message (events / heartbeats) for STALE_AFTER_MS => dead link => reconnect
//  - non-retryable closes (bad origin / bad id / unknown run) => "error", no retry
// =============================================================================

import type { ConnectionState, ServerMessage } from "./types";

/** close codes the server uses to say "do not retry": origin rejected, malformed id, run not found */
export const NON_RETRYABLE_CLOSE_CODES = new Set([1008, 4400, 4404]);

export interface ConnectionInfo {
  error?: string;
  attempt?: number;
  nextRetryMs?: number;
}

export interface ClientOptions {
  url: (lastEventId: string | null) => string;
  getLastEventId: () => string | null;
  onMessage: (message: ServerMessage) => void;
  onConnectionState: (state: ConnectionState, info?: ConnectionInfo) => void;
  /** return false to stop retrying (e.g. the run is finished) */
  shouldReconnect?: () => boolean;
  WebSocketImpl?: typeof WebSocket;
  baseDelayMs?: number;
  maxDelayMs?: number;
  /** +/- fraction of randomisation applied to each delay */
  jitter?: number;
  /** server heartbeats every 20s; silence for this long means the link is dead */
  staleAfterMs?: number;
  random?: () => number;
}

export class TelemetryClient {
  private opts: Required<Omit<ClientOptions, "shouldReconnect" | "WebSocketImpl">> &
    Pick<ClientOptions, "shouldReconnect" | "WebSocketImpl">;
  private socket: WebSocket | null = null;
  private attempt = 0;
  private started = false;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private watchdog: ReturnType<typeof setTimeout> | null = null;

  constructor(options: ClientOptions) {
    this.opts = {
      baseDelayMs: 1000,
      maxDelayMs: 30_000,
      jitter: 0.25,
      staleAfterMs: 50_000,
      random: Math.random,
      ...options,
    };
  }

  /** Backoff delay for the n-th consecutive failed attempt (n >= 1), before/after jitter. */
  static delayFor(attempt: number, base: number, max: number, jitter: number, random: () => number): number {
    const raw = Math.min(max, base * 2 ** (attempt - 1));
    const factor = 1 - jitter + random() * 2 * jitter; // [1-j, 1+j]
    return Math.max(0, Math.round(raw * factor));
  }

  start(): void {
    if (this.started) return;
    this.started = true;
    this.attempt = 0;
    this.open();
  }

  /** Stop for good (unmount / run changed / user closed). Closes the socket and cancels retries. */
  stop(): void {
    this.started = false;
    this.clearTimers();
    this.detach();
    this.opts.onConnectionState("disconnected");
  }

  /** Manual reconnect: skip any pending backoff and try right now. */
  reconnect(): void {
    this.clearTimers();
    this.detach();
    this.started = true;
    this.attempt = 0;
    this.open();
  }

  // ── internals ────────────────────────────────────────────────────────

  private open(): void {
    const Impl = this.opts.WebSocketImpl ?? (globalThis.WebSocket as typeof WebSocket);
    this.opts.onConnectionState(this.attempt === 0 ? "connecting" : "reconnecting", { attempt: this.attempt });
    let socket: WebSocket;
    try {
      socket = new Impl(this.opts.url(this.opts.getLastEventId()));
    } catch (e) {
      this.scheduleRetry(e instanceof Error ? e.message : "could not open socket");
      return;
    }
    this.socket = socket;
    socket.onopen = () => {
      if (this.socket !== socket) return;
      this.opts.onConnectionState("connected", { attempt: this.attempt });
      this.armWatchdog();
    };
    socket.onmessage = (ev: MessageEvent) => {
      if (this.socket !== socket) return;
      this.armWatchdog();
      let msg: ServerMessage;
      try {
        msg = JSON.parse(String(ev.data)) as ServerMessage;
      } catch {
        return; // ignore malformed frames
      }
      if (msg.type === "workflow.snapshot") this.attempt = 0; // a full round trip worked: reset the backoff
      this.opts.onMessage(msg);
    };
    let closed = false; // each socket is handled as closed exactly once
    const handleClose = (code: number, reason: string) => {
      if (closed || this.socket !== socket) return; // already handled, or a stale socket we replaced
      closed = true;
      this.socket = null;
      this.clearWatchdog();
      if (!this.started) return;
      if (NON_RETRYABLE_CLOSE_CODES.has(code)) {
        this.started = false;
        this.opts.onConnectionState("error", { error: closeReason(code, reason) });
        return;
      }
      if (this.opts.shouldReconnect && !this.opts.shouldReconnect()) {
        this.started = false;
        this.opts.onConnectionState("disconnected");
        return;
      }
      this.scheduleRetry(closeReason(code, reason));
    };
    socket.onerror = () => {
      // Browsers follow an error with a close event. Some runtimes (e.g. Node's built-in WebSocket) do not when a
      // connection is refused, which would leave us waiting forever: treat an error without a close as a failure.
      setTimeout(() => {
        if (!closed && this.socket === socket && socket.readyState !== 1) {
          try {
            socket.close();
          } catch {
            /* already closed */
          }
          handleClose(1006, "connection failed");
        }
      }, 50);
    };
    socket.onclose = (ev: CloseEvent) => handleClose(ev.code, ev.reason);
  }

  private scheduleRetry(reason: string): void {
    this.attempt += 1;
    const delay = TelemetryClient.delayFor(
      this.attempt, this.opts.baseDelayMs, this.opts.maxDelayMs, this.opts.jitter, this.opts.random,
    );
    this.opts.onConnectionState("reconnecting", { attempt: this.attempt, nextRetryMs: delay, error: reason });
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      if (this.started) this.open();
    }, delay);
  }

  private armWatchdog(): void {
    this.clearWatchdog();
    this.watchdog = setTimeout(() => {
      // Silence: the OS has not told us the link died, but it has. Close it; onclose schedules the retry.
      try {
        this.socket?.close(4000, "stale");
      } catch {
        /* already closed */
      }
    }, this.opts.staleAfterMs);
  }

  private clearWatchdog(): void {
    if (this.watchdog) clearTimeout(this.watchdog);
    this.watchdog = null;
  }

  private clearTimers(): void {
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = null;
    this.clearWatchdog();
  }

  private detach(): void {
    const s = this.socket;
    this.socket = null;
    if (s) {
      s.onopen = s.onmessage = s.onerror = s.onclose = null;
      try {
        s.close(1000);
      } catch {
        /* already closed */
      }
    }
  }
}

function closeReason(code: number, reason: string): string {
  if (code === 4404) return "run not found";
  if (code === 4400) return "invalid run id";
  if (code === 1008) return "connection rejected (origin not allowed)";
  if (code === 1013) return "server asked the client to retry (too slow)";
  return reason || `connection closed (${code})`;
}
