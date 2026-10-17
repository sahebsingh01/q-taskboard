import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { getToken, setSession, clearSession, getStoredUser } from "@/lib/api-client";
import { STATUS_ORDER, STATUS_LABELS } from "@/types";

describe("session management", () => {
  beforeEach(() => clearSession());
  afterEach(() => clearSession());

  it("returns null when no token is stored", () => {
    expect(getToken()).toBeNull();
  });

  it("returns the token after setSession", () => {
    setSession("test-token", { id: "u1", email: "a@b.com", name: "Alice" });
    expect(getToken()).toBe("test-token");
  });

  it("returns the stored user after setSession", () => {
    const user = { id: "u1", email: "a@b.com", name: "Alice" };
    setSession("tok", user);
    expect(getStoredUser()).toEqual(user);
  });

  it("clears token and user on clearSession", () => {
    setSession("tok", { id: "u1", email: "a@b.com", name: "Alice" });
    clearSession();
    expect(getToken()).toBeNull();
    expect(getStoredUser()).toBeNull();
  });
});

describe("task status constants", () => {
  it("STATUS_ORDER contains the four expected statuses in order", () => {
    expect(STATUS_ORDER).toEqual(["todo", "in_progress", "review", "done"]);
  });

  it("STATUS_LABELS has a label for every status", () => {
    for (const s of STATUS_ORDER) {
      expect(STATUS_LABELS[s]).toBeTruthy();
    }
  });
});
