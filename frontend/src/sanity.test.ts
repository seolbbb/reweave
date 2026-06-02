import { describe, expect, it } from "vitest";

describe("frontend sanity", () => {
  it("runs tests", () => {
    expect("archive").toContain("arch");
  });
});
