/* eslint-disable no-bitwise -- byte-level RFC 4122 version/variant bits */
import { randomBytes } from "@noble/hashes/utils.js";

/** RFC 4122 version-4 (random) UUID. No extra dependency needed beyond the
 * secure random source already required for key generation. */
export function randomUuidV4(): string {
  const bytes = randomBytes(16);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
