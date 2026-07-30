import { canonicalizeToBytes } from "../canonical";

function bytesToUtf8(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString("utf-8");
}

describe("canonicalizeToBytes", () => {
  it("sorts object keys", () => {
    const json = bytesToUtf8(canonicalizeToBytes({ b: 1, a: 2 }));
    expect(json).toBe('{"a":2,"b":1}');
  });

  it("drops the trailing .0 for whole-number floats, matching JS Number semantics", () => {
    const json = bytesToUtf8(canonicalizeToBytes({ lat: 23.0 }));
    expect(json).toBe('{"lat":23}');
  });

  it("preserves non-integer decimals", () => {
    const json = bytesToUtf8(canonicalizeToBytes({ lat: 23.81 }));
    expect(json).toBe('{"lat":23.81}');
  });

  it("leaves non-ASCII (Bangla) characters unescaped", () => {
    const json = bytesToUtf8(canonicalizeToBytes({ text: "সাহায্য" }));
    expect(json).toBe('{"text":"সাহায্য"}');
  });

  it("recursively sorts nested object keys", () => {
    const json = bytesToUtf8(
      canonicalizeToBytes({ z: { y: 1, x: 2 }, a: 1 }),
    );
    expect(json).toBe('{"a":1,"z":{"x":2,"y":1}}');
  });

  it("preserves array order (arrays are not sorted)", () => {
    const json = bytesToUtf8(canonicalizeToBytes({ needs: ["water", "medical"] }));
    expect(json).toBe('{"needs":["water","medical"]}');
  });

  it("serializes null explicitly", () => {
    const json = bytesToUtf8(canonicalizeToBytes({ priority: null }));
    expect(json).toBe('{"priority":null}');
  });
});
