"use client";
// =============================================================================
// HiveMind — useEventStream: real-time run telemetry over WebSocket
//
//   const { events, state, connectionState, error, reconnect, isTerminal } =
//     useEventStream({ runId, enabled });
//
// Replaces the former replay/simulation hook. The REST API + PostgreSQL stay the source of truth: the
// server sends a snapshot on every (re)connection, this hook applies events idempotently (dedup by
// event_id) and resumes after the last applied event when the socket drops.
// =============================================================================

import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import { runSocketUrl } from "@/lib/config";
import { TelemetryClient } from "@/lib/telemetry/client";
import {
  initialStreamState,
  isTerminal as terminal,
  reduce as reduceStream,
  type StreamState,
} from "@/lib/telemetry/reducer";
import type { ConnectionState, ServerMessage, TelemetryEvent, WorkflowState } from "@/lib/telemetry/types";

export interface UseEventStreamOptions {
  runId: string | null | undefined;
  enabled?: boolean;
  /** test seam: inject a WebSocket implementation */
  WebSocketImpl?: typeof WebSocket;
}

export interface UseEventStreamReturn {
  /** persisted workflow events for this run, oldest first, deduplicated by event_id */
  events: TelemetryEvent[];
  /** authoritative run + per-agent state from the backend */
  state: WorkflowState | null;
  connectionState: ConnectionState;
  /** transport problem description (never a workflow failure) */
  error: string | null;
  /** ms until the next automatic reconnect attempt, if reconnecting */
  nextRetryMs: number | null;
  reconnect: () => void;
  lastEvent: TelemetryEvent | null;
  /** the workflow (not the socket) has completed or failed */
  isTerminal: boolean;
}

// One reducer holds stream data AND transport state, so every change goes through dispatch.
interface View {
  stream: StreamState;
  connection: ConnectionState;
  error: string | null;
  nextRetryMs: number | null;
}

type ViewAction =
  | { type: "message"; message: ServerMessage }
  | { type: "reset"; connection: ConnectionState }
  | { type: "connection"; connection: ConnectionState; error: string | null; nextRetryMs: number | null };

const initialView: View = { stream: initialStreamState, connection: "disconnected", error: null, nextRetryMs: null };

function reduceView(v: View, a: ViewAction): View {
  switch (a.type) {
    case "reset":
      return { stream: initialStreamState, connection: a.connection, error: null, nextRetryMs: null };
    case "connection":
      return { ...v, connection: a.connection, error: a.error, nextRetryMs: a.nextRetryMs };
    case "message":
      return { ...v, stream: reduceStream(v.stream, a) };
  }
}

export function useEventStream({ runId, enabled = true, WebSocketImpl }: UseEventStreamOptions): UseEventStreamReturn {
  const [view, dispatch] = useReducer(reduceView, initialView);
  const clientRef = useRef<TelemetryClient | null>(null);
  const streamRef = useRef<StreamState>(view.stream);

  useEffect(() => {
    streamRef.current = view.stream; // the client reads the latest applied state when it reconnects
  }, [view.stream]);

  useEffect(() => {
    const active = enabled && !!runId;
    dispatch({ type: "reset", connection: active ? "connecting" : "disconnected" });
    streamRef.current = initialStreamState;
    if (!active) return;

    const client = new TelemetryClient({
      url: (last) => runSocketUrl(runId as string, last),
      getLastEventId: () => streamRef.current.lastEventId,
      shouldReconnect: () => !terminal(streamRef.current),
      WebSocketImpl,
      onMessage: (message) => dispatch({ type: "message", message }),
      onConnectionState: (connection, info) =>
        dispatch({
          type: "connection",
          connection,
          error: connection === "error" || connection === "reconnecting" ? (info?.error ?? null) : null,
          nextRetryMs: connection === "reconnecting" ? (info?.nextRetryMs ?? null) : null,
        }),
    });
    clientRef.current = client;
    client.start();
    const onOnline = () => client.reconnect(); // network came back: don't wait for the backoff timer
    window.addEventListener("online", onOnline);
    return () => {
      window.removeEventListener("online", onOnline);
      client.stop();
      clientRef.current = null;
    };
  }, [runId, enabled, WebSocketImpl]);

  const reconnect = useCallback(() => clientRef.current?.reconnect(), []);
  const { stream } = view;
  const lastEvent = stream.events.length ? stream.events[stream.events.length - 1] : null;
  const isTerminal = useMemo(() => terminal(stream), [stream]);

  return {
    events: stream.events,
    state: stream.state,
    connectionState: view.connection,
    error: view.error,
    nextRetryMs: view.nextRetryMs,
    reconnect,
    lastEvent,
    isTerminal,
  };
}
