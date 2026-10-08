import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchProjects } from "@/lib/api";
import { UnauthorizedError, login, fetchCurrentUser } from "@/lib/auth";

const json = (status: number, body: unknown = {}) => new Response(JSON.stringify(body), { status });

afterEach(() => vi.restoreAllMocks());

describe("credentialed API access", () => {
  it("sends the session cookie with every API request and never an Authorization header or token", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, []));
    await fetchProjects();
    const init = spy.mock.calls[0][1] as RequestInit;
    expect(init.credentials).toBe("include");
    expect(JSON.stringify(init.headers ?? {})).not.toMatch(/authorization|bearer/i);
  });

  it("an expired session (401) signs the user out to the login page", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(401, { detail: "Not authenticated" }));
    const assign = vi.fn();
    vi.stubGlobal("window", { location: { pathname: "/runs", assign } });
    await expect(fetchProjects()).rejects.toBeInstanceOf(UnauthorizedError);
    expect(assign).toHaveBeenCalledWith("/login");
    vi.unstubAllGlobals();
  });

  it("login errors are generic and never echo server details or the password", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(401, { detail: "Invalid email or password", password: "hunter2" }));
    const err = await login("a@b.co", "hunter2-hunter2").catch((e: Error) => e);
    expect((err as Error).message).toBe("Invalid email or password.");
    expect((err as Error).message).not.toContain("hunter2");
  });

  it("rate limiting is explained to the user", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(429));
    await expect(login("a@b.co", "x")).rejects.toThrow(/Too many attempts/);
  });

  it("fetchCurrentUser is null when signed out and posts nothing", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(401));
    expect(await fetchCurrentUser()).toBeNull();
    expect((spy.mock.calls[0][1] as RequestInit).method).toBe("GET");
  });
});
