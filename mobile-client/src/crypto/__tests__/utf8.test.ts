import { utf8Decode, utf8Encode } from "../utf8";

function nodeUtf8(str: string): Uint8Array {
  return new Uint8Array(Buffer.from(str, "utf-8"));
}

describe("utf8Encode", () => {
  it("matches Node's UTF-8 encoding for ASCII", () => {
    expect(utf8Encode("hello world")).toEqual(nodeUtf8("hello world"));
  });

  it("matches Node's UTF-8 encoding for Bangla (BMP) text", () => {
    const text = "সাহায্য দরকার জরুরি ভিত্তিতে";
    expect(utf8Encode(text)).toEqual(nodeUtf8(text));
  });

  it("matches Node's UTF-8 encoding for astral-plane characters (surrogate pairs)", () => {
    const text = "emergency 🚨 flood 🌊";
    expect(utf8Encode(text)).toEqual(nodeUtf8(text));
  });

  it("matches Node's UTF-8 encoding for an empty string", () => {
    expect(utf8Encode("")).toEqual(nodeUtf8(""));
  });
});

describe("utf8Decode", () => {
  it.each([
    "hello world",
    "সাহায্য দরকার জরুরি ভিত্তিতে",
    "emergency 🚨 flood 🌊",
    "",
  ])("round-trips %p through encode/decode", (text) => {
    expect(utf8Decode(utf8Encode(text))).toBe(text);
  });

  it("matches Node's UTF-8 decoding of real UTF-8 bytes", () => {
    const text = "সাহায্য দরকার";
    const bytes = new Uint8Array(Buffer.from(text, "utf-8"));
    expect(utf8Decode(bytes)).toBe(text);
  });
});
