/* eslint-disable no-bitwise -- byte-level encoding is the entire point of this file */
/**
 * Manual UTF-8 encoder. Hermes does not reliably expose a global
 * `TextEncoder` across React Native versions/engines, and this byte
 * encoding feeds directly into what gets Ed25519-signed — so it must not
 * depend on an environment global that may or may not exist. Verified in
 * utf8.test.ts against Node's own `Buffer`/`TextEncoder` output for ASCII,
 * Bangla (BMP), and emoji (surrogate pair / astral) inputs.
 */
export function utf8Encode(input: string): Uint8Array {
  const bytes: number[] = [];
  for (let i = 0; i < input.length; i++) {
    let codePoint = input.codePointAt(i);
    if (codePoint === undefined) continue;
    if (codePoint > 0xffff) {
      i++; // consumed a low surrogate as part of this code point
    }
    if (codePoint < 0x80) {
      bytes.push(codePoint);
    } else if (codePoint < 0x800) {
      bytes.push(0xc0 | (codePoint >> 6), 0x80 | (codePoint & 0x3f));
    } else if (codePoint < 0x10000) {
      bytes.push(
        0xe0 | (codePoint >> 12),
        0x80 | ((codePoint >> 6) & 0x3f),
        0x80 | (codePoint & 0x3f),
      );
    } else {
      bytes.push(
        0xf0 | (codePoint >> 18),
        0x80 | ((codePoint >> 12) & 0x3f),
        0x80 | ((codePoint >> 6) & 0x3f),
        0x80 | (codePoint & 0x3f),
      );
    }
  }
  return new Uint8Array(bytes);
}

/** Inverse of utf8Encode. Also verified against Node's `Buffer`/`TextDecoder`
 * in utf8.test.ts. */
export function utf8Decode(bytes: Uint8Array): string {
  let result = "";
  let i = 0;
  while (i < bytes.length) {
    const byte0 = bytes[i];
    let codePoint: number;
    let length: number;
    if (byte0 < 0x80) {
      codePoint = byte0;
      length = 1;
    } else if ((byte0 & 0xe0) === 0xc0) {
      codePoint = byte0 & 0x1f;
      length = 2;
    } else if ((byte0 & 0xf0) === 0xe0) {
      codePoint = byte0 & 0x0f;
      length = 3;
    } else if ((byte0 & 0xf8) === 0xf0) {
      codePoint = byte0 & 0x07;
      length = 4;
    } else {
      throw new Error(`Invalid UTF-8 leading byte at offset ${i}`);
    }
    if (i + length > bytes.length) {
      throw new Error("Truncated UTF-8 sequence");
    }
    for (let k = 1; k < length; k++) {
      const continuation = bytes[i + k];
      if ((continuation & 0xc0) !== 0x80) {
        throw new Error(`Invalid UTF-8 continuation byte at offset ${i + k}`);
      }
      codePoint = (codePoint << 6) | (continuation & 0x3f);
    }
    result += String.fromCodePoint(codePoint);
    i += length;
  }
  return result;
}
