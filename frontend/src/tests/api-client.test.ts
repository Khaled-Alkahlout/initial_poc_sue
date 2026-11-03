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

  test.each([
    [500, "Internal Server Error", "Interne backendfout"],
    [422, '{"detail":[{"loc":["body"],"msg":"invalid"}]}', "Ongeldige invoer"],
    [
      503,
      '{"detail":"Herstart de Python-API.","error_code":"runtime_version_mismatch"}',
      "tijdelijk niet beschikbaar",
    ],
    [
      502,
      '{"detail":"Provider request failed.","error_code":"llm_request_failed"}',
      "AI-modelverzoek mislukt",
    ],
  ])(
    "HTTP %s onderscheidt de foutcategorie en toont endpoint en referentie",
    async (status, body, category) => {
      vi.stubGlobal(
        "fetch",
        vi
          .fn()
          .mockResolvedValue(
            new Response(body, {
              status: Number(status),
              headers: { "X-Request-ID": "ref-123" },
            }),
          ),
      );
      try {
        await api.getQueries();
        expect.fail("Request should fail");
      } catch (error) {
        expect(error).toBeInstanceOf(ApiError);
        expect(error).toMatchObject({
          status: Number(status),
          requestId: "ref-123",
          path: "/queries?top_k=2",
        });
        expect((error as Error).message).toContain(String(category));
        expect((error as Error).message).toContain("Endpoint: /api/queries");
        expect((error as Error).message).toContain("Referentie: ref-123");
        if (Number(status) >= 500)
          expect((error as Error).message).not.toContain(
            "Controleer de invoer",
          );
      }
    },
  );
});
