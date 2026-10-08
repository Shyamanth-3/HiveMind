// =============================================================================
// HiveMind — authentication client
//
// The session lives in an httpOnly cookie set by the API: JavaScript can neither read nor steal it, and there is no
// token in localStorage or in any URL. Every request is sent with `credentials: "include"`; the WebSocket handshake
// carries the same cookie automatically. The frontend holds no secret of any kind.
// =============================================================================

import { API_BASE } from "@/lib/config";

export interface AuthUser {
  id: string;
  email: string;
  is_admin: boolean;
}

/** The session is missing or expired (HTTP 401). */
export class UnauthorizedError extends Error {
  constructor() {
    super("Not authenticated");
    this.name = "UnauthorizedError";
  }
}

export const LOGIN_PATH = "/login";

/** Send the user to the login page (once), remembering nothing sensitive. */
export function redirectToLogin(): void {
  if (typeof window !== "undefined" && window.location.pathname !== LOGIN_PATH) {
    window.location.assign(LOGIN_PATH);
  }
}

async function authRequest(path: string, body?: unknown): Promise<Response> {
  return fetch(`${API_BASE}/auth${path}`, {
    method: body === undefined ? "GET" : "POST",
    credentials: "include",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/** Human-readable failure without echoing anything the server should not reveal. */
async function failure(res: Response): Promise<Error> {
  if (res.status === 429) return new Error("Too many attempts. Please wait a moment and try again.");
  if (res.status === 401) return new Error("Invalid email or password.");
  if (res.status === 409) return new Error("Could not register with these details.");
  if (res.status === 403) return new Error("Registration is currently disabled.");
  if (res.status === 422) return new Error("Please enter a valid email and a password of at least 12 characters.");
  return new Error("Something went wrong. Please try again.");
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const res = await authRequest("/login", { email, password });
  if (!res.ok) throw await failure(res);
  return res.json();
}

export async function register(email: string, password: string): Promise<AuthUser> {
  const res = await authRequest("/register", { email, password });
  if (!res.ok) throw await failure(res);
  return res.json();
}

export async function logout(): Promise<void> {
  await authRequest("/logout", {});
}

export async function fetchCurrentUser(): Promise<AuthUser | null> {
  const res = await authRequest("/me");
  if (res.status === 401) return null;
  if (!res.ok) throw await failure(res);
  return res.json();
}
