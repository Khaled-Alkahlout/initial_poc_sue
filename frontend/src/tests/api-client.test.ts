import { afterEach, describe, expect, test, vi } from "vitest";
import { api, ApiError } from "@/lib/api/client";
import { query } from "./fixtures";
afterEach(() => vi.unstubAllGlobals());
describe("getypeerde API-grens", () => {
  test("verwerkt en valideert de queryresponse", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ queries: [query()], policy: { top_k: 2 } }),
        ),
      );
    vi.stubGlobal("fetch", fetch);
    expect((await api.getQueries()).queries[0].rank).toBe(1);
    expect(fetch.mock.calls[0][0]).toBe("/api/queries?top_k=2");
  });
  test("weigert een onvolledig contract in plaats van succesvelden in te vullen", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response('{"queries":[{"query_id":"x"}]}')),
    );
    await expect(api.getQueries()).rejects.toThrow(/contract/);
  });
  test("houdt HTTP- en netwerkfouten zichtbaar", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response('{"detail":"Niet beschikbaar"}', { status: 409 }),
        ),
    );
    await expect(api.getQueries()).rejects.toMatchObject({ status: 409 });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(api.getQueries()).rejects.toBeInstanceOf(ApiError);
  });
});
