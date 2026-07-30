// Bridges mobile-client's actual signing libraries into this Python test
// suite. Reads one JSON object (the report's signed subset) on stdin, uses
// the exact same npm packages mobile-client/src/crypto/{canonical,sign}.ts
// import, and prints hex-encoded canonical bytes, a freshly generated Ed25519
// public key, and a real signature over those bytes. Nothing here is a
// reimplementation — it imports mobile-client's own installed dependencies.
import canonicalize from "canonicalize";
import * as ed from "@noble/ed25519";
import { sha512 } from "@noble/hashes/sha2.js";

ed.hashes.sha512 = sha512;

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", chunk => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

const input = JSON.parse(await readStdin());
const canonicalJson = canonicalize(input);
const canonicalBytes = Buffer.from(canonicalJson, "utf8");

const secretKey = ed.utils.randomSecretKey();
const publicKey = ed.getPublicKey(secretKey);
const signature = ed.sign(canonicalBytes, secretKey);
const selfVerified = ed.verify(signature, canonicalBytes, publicKey);

process.stdout.write(
  JSON.stringify({
    canonical_hex: canonicalBytes.toString("hex"),
    public_key_hex: Buffer.from(publicKey).toString("hex"),
    signature_hex: Buffer.from(signature).toString("hex"),
    self_verified: selfVerified,
  }),
);
