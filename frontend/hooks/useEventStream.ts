"use client";
// =============================================================================
// HiveMind — WebSocket Event Stream Simulation
// Shaped so replacing with a real WebSocket is a drop-in change.
// Returns { events, isConnected, lastEvent }.
// =============================================================================

import { useState, useEffect, useRef, useCallback } from "react";
import type { Event } from "@/types";
import { mockEvents } from "@/lib/mockData";

interface UseEventStreamReturn {
  events: Event[];
  isConnected: boolean;
  lastEvent: Event | null;
}

/**
 * Simulates a WebSocket event stream by drip-feeding mock events.
 * In production, replace the internals with a real WebSocket connection
 * while keeping the same return shape.
 */
export function useEventStream(maxEvents = 50): UseEventStreamReturn {
  const [events, setEvents] = useState<Event[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<Event | null>(null);
  const indexRef = useRef(0);
  const sortedEvents = useRef(
    [...mockEvents].sort(
      (a, b) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    )
  );

  const addEvent = useCallback(() => {
    const allEvents = sortedEvents.current;
    if (indexRef.current >= allEvents.length) {
      // Loop back to beginning for continuous simulation
      indexRef.current = 0;
    }

    const event = allEvents[indexRef.current];
    indexRef.current += 1;

    // Create a new event with a fresh timestamp to simulate "live"
    const liveEvent: Event = {
      ...event,
      id: `${event.id}_${Date.now()}`,
      created_at: new Date().toISOString(),
    };

    setLastEvent(liveEvent);
    setEvents((prev) => [liveEvent, ...prev].slice(0, maxEvents));
  }, [maxEvents]);

  useEffect(() => {
    // Simulate connection delay
    const connectTimeout = setTimeout(() => {
      setIsConnected(true);

      // Load initial batch (first 5 events)
      const initial = sortedEvents.current.slice(0, 5);
      setEvents(initial.reverse());
      setLastEvent(initial[0]);
      indexRef.current = 5;
    }, 800);

    return () => clearTimeout(connectTimeout);
  }, []);

  useEffect(() => {
    if (!isConnected) return;

    // Drip-feed new events every 3-6 seconds
    const interval = setInterval(() => {
      addEvent();
    }, 3000 + Math.random() * 3000);

    return () => clearInterval(interval);
  }, [isConnected, addEvent]);

  return { events, isConnected, lastEvent };
}
