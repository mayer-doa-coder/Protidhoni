/* eslint-disable no-bitwise -- byte-level encoding is the entire point of this file */
/**
 * Manual base64url encode/decode. Same rationale as utf8.ts: this feeds the
 * signed report's identity/signature fields, so it must not depend on
 * `btoa`/`atob` (unreliable across RN/Hermes versions and don't produce the
 * unpadded, URL-safe alphabet contracts/message-schema.json requires anyway).
 * Verified in base64url.test.ts against Node's `Buffer.toString('base64url')`.
 */
const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

export function base64UrlEncode(bytes: Uint8Array): string {
  let output = "";
  let i = 0;
  for (; i + 2 < bytes.length; i += 3) {
    const chunk = (bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2];
    output +=
      ALPHABET[(chunk >> 18) & 0x3f] +
      ALPHABET[(chunk >> 12) & 0x3f] +
      ALPHABET[(chunk >> 6) & 0x3f] +
      ALPHABET[chunk & 0x3f];
  }
  const remaining = bytes.length - i;
  if (remaining === 1) {
    const chunk = bytes[i] << 16;
    output += ALPHABET[(chunk >> 18) & 0x3f] + ALPHABET[(chunk >> 12) & 0x3f];
  } else if (remaining === 2) {
    const chunk = (bytes[i] << 16) | (bytes[i + 1] << 8);
    output +=
      ALPHABET[(chunk >> 18) & 0x3f] + ALPHABET[(chunk >> 12) & 0x3f] + ALPHABET[(chunk >> 6) & 0x3f];
  }
  return output;
}

const DECODE_TABLE: Record<string, number> = (() => {
  const table: Record<string, number> = {};
  for (let i = 0; i < ALPHABET.length; i++) table[ALPHABET[i]] = i;
  return table;
})();

export function base64UrlDecode(value: string): Uint8Array {
  const cleaned = value.replace(/[=]+$/, "");
  const bytes: number[] = [];
  let buffer = 0;
  let bitsFilled = 0;
  for (const char of cleaned) {
    const bits = DECODE_TABLE[char];
    if (bits === undefined) {
      throw new Error(`Invalid base64url character: ${char}`);
    }
    buffer = (buffer << 6) | bits;
    bitsFilled += 6;
    if (bitsFilled >= 8) {
      bitsFilled -= 8;
      bytes.push((buffer >> bitsFilled) & 0xff);
    }
  }
  return new Uint8Array(bytes);
}
