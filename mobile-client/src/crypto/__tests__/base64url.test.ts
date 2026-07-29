import { base64UrlDecode, base64UrlEncode } from "../base64url";

function nodeB64Url(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString("base64url");
}

describe("base64UrlEncode", () => {
  it.each([0, 1, 2, 3, 4, 5, 16, 31, 32, 63, 64, 65])(
    "matches Node's base64url output for %i random bytes",
    (length) => {
      const bytes = new Uint8Array(length);
      for (let i = 0; i < length; i++) bytes[i] = (i * 37 + 11) % 256;
      expect(base64UrlEncode(bytes)).toBe(nodeB64Url(bytes));
    },
  );

  it("never emits padding or the standard-base64 +/ characters", () => {
    const bytes = new Uint8Array([251, 255, 254, 253, 62, 63]);
    const encoded = base64UrlEncode(bytes);
    expect(encoded).not.toMatch(/[+/=]/);
  });
});

describe("base64UrlDecode", () => {
  it("round-trips arbitrary byte sequences", () => {
    const bytes = new Uint8Array(37);
    for (let i = 0; i < bytes.length; i++) bytes[i] = (i * 91 + 3) % 256;
    expect(base64UrlDecode(base64UrlEncode(bytes))).toEqual(bytes);
  });

  it("decodes real base64url produced by Node for a 32-byte key", () => {
    const bytes = new Uint8Array(32);
    for (let i = 0; i < 32; i++) bytes[i] = i * 7;
    const encoded = nodeB64Url(bytes);
    expect(base64UrlDecode(encoded)).toEqual(bytes);
  });

  it("rejects an invalid character", () => {
    expect(() => base64UrlDecode("not!valid$$")).toThrow();
  });
});
