import { describe, expect, it } from "vitest";
import { search } from "@/lib/search";

// These tests exercise the retrieval layer directly — the job the old
// `/api/search` debug endpoint used to do, but deterministic and in CI.
describe("search", () => {
  it("finds the dependency-install FAQ for a natural-language question", () => {
    const results = search("How do I install the course dependencies?");

    expect(results.length).toBeGreaterThan(0);
    // The top hits should be about environment/dependency setup.
    const haystack = (results[0].question + " " + results[0].answer).toLowerCase();
    expect(haystack).toMatch(/install|uv|dependenc|environment/);
  });

  it("tolerates typos (fuzzy matching)", () => {
    const results = search("instal dependancies");
    expect(results.length).toBeGreaterThan(0);
  });

  it("respects the limit and clamps it to the 1..10 range", () => {
    expect(search("docker", 3).length).toBeLessThanOrEqual(3);
    expect(search("docker", 999).length).toBeLessThanOrEqual(10);
  });

  it("returns an empty array for a blank query", () => {
    expect(search("   ")).toEqual([]);
  });

  it("returns results sorted by descending score", () => {
    const scores = search("kestra docker compose").map((r) => r.score);
    const sorted = [...scores].sort((a, b) => b - a);
    expect(scores).toEqual(sorted);
  });
});
