import { base64Decode, base64Encode } from "../base64";

function nodeB64(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString("base64");
}

describe("base64Encode", () => {
  it.each([0, 1, 2, 3, 4, 5, 16, 31, 32, 63, 64, 65])(
    "matches Node's standard base64 output for %i bytes",
    (length) => {
      const bytes = new Uint8Array(length);
      for (let i = 0; i < length; i++) bytes[i] = (i * 53 + 7) % 256;
      expect(base64Encode(bytes)).toBe(nodeB64(bytes));
    },
  );

  it("uses the standard alphabet and padding (not url-safe)", () => {
    const bytes = new Uint8Array([251, 255, 254, 253, 62, 63]);
    expect(base64Encode(bytes)).toBe(nodeB64(bytes));
  });
});

describe("base64Decode", () => {
  it("round-trips arbitrary byte sequences", () => {
    const bytes = new Uint8Array(40);
    for (let i = 0; i < bytes.length; i++) bytes[i] = (i * 71 + 13) % 256;
    expect(base64Decode(base64Encode(bytes))).toEqual(bytes);
  });

  it("decodes real standard base64 produced by Node", () => {
    const bytes = new Uint8Array(20);
    for (let i = 0; i < bytes.length; i++) bytes[i] = i * 11;
    expect(base64Decode(nodeB64(bytes))).toEqual(bytes);
  });
});
