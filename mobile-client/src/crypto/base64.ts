/* eslint-disable no-bitwise -- byte-level encoding is the entire point of this file */
/**
 * Manual standard (padded, +/) base64 encode/decode — distinct from
 * base64url.ts. This is only for the byte-array-over-the-RN-bridge leg
 * (mesh payloads to/from android/.../NearbyConnectionsModule.kt, which
 * encodes with Android's `android.util.Base64.NO_WRAP`, i.e. the standard
 * alphabet with padding). Schema fields (sender_pubkey, signature.value,
 * etc.) always use base64url.ts instead, per message-schema.json.
 * Verified in base64.test.ts against Node's `Buffer.toString('base64')`.
 */
const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

export function base64Encode(bytes: Uint8Array): string {
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
    output += ALPHABET[(chunk >> 18) & 0x3f] + ALPHABET[(chunk >> 12) & 0x3f] + "==";
  } else if (remaining === 2) {
    const chunk = (bytes[i] << 16) | (bytes[i + 1] << 8);
    output +=
      ALPHABET[(chunk >> 18) & 0x3f] + ALPHABET[(chunk >> 12) & 0x3f] + ALPHABET[(chunk >> 6) & 0x3f] + "=";
  }
  return output;
}

const DECODE_TABLE: Record<string, number> = (() => {
  const table: Record<string, number> = {};
  for (let i = 0; i < ALPHABET.length; i++) table[ALPHABET[i]] = i;
  return table;
})();

export function base64Decode(value: string): Uint8Array {
  const cleaned = value.replace(/[=]+$/, "");
  const bytes: number[] = [];
  let buffer = 0;
  let bitsFilled = 0;
  for (const char of cleaned) {
    const bits = DECODE_TABLE[char];
    if (bits === undefined) {
      throw new Error(`Invalid base64 character: ${char}`);
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
