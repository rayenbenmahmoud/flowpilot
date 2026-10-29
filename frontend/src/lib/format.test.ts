import { conditionValueToText, formatDuration, parseConditionValue, timeAgo } from "./format";

describe("formatDuration", () => {
  it("handles missing, milliseconds, seconds and minutes", () => {
    expect(formatDuration(null)).toBe("–");
    expect(formatDuration(450)).toBe("450 ms");
    expect(formatDuration(5200)).toBe("5.2 s");
    expect(formatDuration(125000)).toBe("2 min 5 s");
  });
});

describe("timeAgo", () => {
  const now = new Date("2026-10-28T12:00:00Z").getTime();
  it("describes recent and old times", () => {
    expect(timeAgo(null, now)).toBe("never");
    expect(timeAgo("2026-10-28T11:59:40Z", now)).toBe("just now");
    expect(timeAgo("2026-10-28T11:30:00Z", now)).toBe("30 min ago");
    expect(timeAgo("2026-10-28T07:00:00Z", now)).toBe("5 h ago");
    expect(timeAgo("2026-10-20T12:00:00Z", now)).toBe("8 days ago");
  });
});

describe("rule values", () => {
  it("turns numbers into numbers, keeps text and placeholders as text", () => {
    expect(parseConditionValue("gte", "100")).toBe(100);
    expect(parseConditionValue("eq", "urgent")).toBe("urgent");
    expect(parseConditionValue("lte", "{{ payload.reorder_level }}")).toBe("{{ payload.reorder_level }}");
  });
  it("splits lists for 'is one of'", () => {
    expect(parseConditionValue("in", "TN, FR, 7")).toEqual(["TN", "FR", 7]);
  });
  it("round-trips back to text", () => {
    expect(conditionValueToText(["a", "b"])).toBe("a, b");
    expect(conditionValueToText(undefined)).toBe("");
  });
});
