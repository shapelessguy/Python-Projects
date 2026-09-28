// Encrypted folders (vaults): the browser's half of VAULT.md, format v1.
// Every key lives here, in the page's memory; the server only ever stores
// and serves what this produces. The app (Vault.kt) implements the same
// format.
import { argon2id } from "hash-wasm";

export interface Kdf { alg: "argon2id"; m: number; t: number; p: number }
export interface Wrap { salt: string; nonce: string; key: string }
/** `.cyanhouse-vault.json`: nothing in it decrypts anything without a secret. */
export interface VaultFile { v: 1; kdf: Kdf; password: Wrap; recovery: Wrap }

export const VAULT_FILE = ".cyanhouse-vault.json";
export const DEFAULT_KDF: Kdf = { alg: "argon2id", m: 65536, t: 3, p: 1 };
export const CHUNK = 65536;
export const MAX_NAME_BYTES = 150;

const enc = new TextEncoder();
const dec = new TextDecoder("utf-8", { fatal: true });
const WRAP_AAD = enc.encode("cyanhouse-vault-v1");
const NAME_AAD = enc.encode("cyanhouse-name-v1");
const MAGIC = enc.encode("CHV1");
const HEADER = 4 + 12 + 48;

export class VaultError extends Error {}

/** Bytes backed by a plain ArrayBuffer -- what WebCrypto and Blob take. */
export type Bytes = Uint8Array<ArrayBuffer>;

// ── bytes ────────────────────────────────────────────────────────────────
const random = (n: number) => crypto.getRandomValues(new Uint8Array(n));

export function b64(bytes: Bytes): string {
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}
export function unb64(s: string): Bytes {
  const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
const b64url = (bytes: Bytes) => b64(bytes).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

function concat(...parts: Bytes[]): Bytes {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let at = 0;
  for (const p of parts) { out.set(p, at); at += p.length; }
  return out;
}

// ── AES-GCM ──────────────────────────────────────────────────────────────
const aesKey = (raw: Bytes) =>
  crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]);

async function seal(key: CryptoKey, nonce: Bytes, data: Bytes, aad: Bytes): Promise<Bytes> {
  return new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce, additionalData: aad }, key, data));
}
async function open(key: CryptoKey, nonce: Bytes, data: Bytes, aad: Bytes): Promise<Bytes> {
  try {
    return new Uint8Array(await crypto.subtle.decrypt({ name: "AES-GCM", iv: nonce, additionalData: aad }, key, data));
  } catch {
    throw new VaultError("does not decrypt");
  }
}

// ── secrets ──────────────────────────────────────────────────────────────
const CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

/** 20 random bytes as 32 Crockford base32 characters, in four groups. */
export function recoveryCodeFrom(bytes: Bytes): string {
  let bits = 0, value = 0, out = "";
  for (const b of bytes) {
    value = (value << 8) | b; bits += 8;
    while (bits >= 5) { out += CROCKFORD[(value >>> (bits - 5)) & 31]; bits -= 5; }
  }
  return out.match(/.{8}/g)!.join("-");
}

/** A recovery code as typed back: what it is used as. */
export function normaliseRecoveryCode(code: string): string {
  return code.toUpperCase().replace(/[\s-]/g, "").replace(/O/g, "0").replace(/[IL]/g, "1");
}

async function kek(secret: string, salt: Bytes, kdf: Kdf): Promise<CryptoKey> {
  const raw = await argon2id({
    password: enc.encode(secret), salt, parallelism: kdf.p, iterations: kdf.t,
    memorySize: kdf.m, hashLength: 32, outputType: "binary",
  });
  return aesKey(new Uint8Array(raw));
}

/** `mk` locked with `secret` (vector generation passes salt and nonce). */
export async function wrapWith(secret: string, mk: Bytes, kdf: Kdf,
                               salt = random(16), nonce = random(12)): Promise<Wrap> {
  const key = await seal(await kek(secret, salt, kdf), nonce, mk, WRAP_AAD);
  return { salt: b64(salt), nonce: b64(nonce), key: b64(key) };
}

async function unwrap(secret: string, w: Wrap, kdf: Kdf): Promise<Bytes> {
  return open(await kek(secret, unb64(w.salt), kdf), unb64(w.nonce), unb64(w.key), WRAP_AAD);
}

// ── the vault ────────────────────────────────────────────────────────────
/** An unlocked vault: its master key, in this page's memory only. */
export class Vault {
  private constructor(private readonly mk: Bytes, private readonly key: CryptoKey) {}

  static async fromKey(mk: Bytes): Promise<Vault> {
    return new Vault(mk, await aesKey(mk));
  }

  /** A new vault: its file for the server, the vault unlocked, and the
   *  recovery code to show once. */
  static async create(password: string, kdf: Kdf = DEFAULT_KDF):
      Promise<{ file: VaultFile; vault: Vault; recoveryCode: string }> {
    const mk = random(32);
    const recoveryCode = recoveryCodeFrom(random(20));
    const file: VaultFile = {
      v: 1, kdf,
      password: await wrapWith(password.normalize("NFC"), mk, kdf),
      recovery: await wrapWith(normaliseRecoveryCode(recoveryCode), mk, kdf),
    };
    return { file, vault: await Vault.fromKey(mk), recoveryCode };
  }

  /** Unlock with the password, or (`recovery`) the recovery code. A wrong
   *  one throws VaultError. */
  static async unlock(file: VaultFile, secret: string, recovery = false): Promise<Vault> {
    if (file.v !== 1 || file.kdf?.alg !== "argon2id") throw new VaultError("unknown vault format");
    const s = recovery ? normaliseRecoveryCode(secret) : secret.normalize("NFC");
    try {
      return await Vault.fromKey(await unwrap(s, recovery ? file.recovery : file.password, file.kdf));
    } catch (e) {
      throw e instanceof VaultError ? new VaultError(recovery ? "wrong recovery code" : "wrong password") : e;
    }
  }

  /** The vault file with a new password (the recovery code stays). */
  async withPassword(file: VaultFile, password: string): Promise<VaultFile> {
    return { ...file, password: await wrapWith(password.normalize("NFC"), this.mk, file.kdf) };
  }

  // ── names ──
  async encryptName(name: string, nonce = random(12)): Promise<string> {
    const plain = enc.encode(name.normalize("NFC"));
    if (!plain.length || plain.length > MAX_NAME_BYTES) throw new VaultError(`a name is 1 to ${MAX_NAME_BYTES} bytes`);
    return b64url(concat(nonce, await seal(this.key, nonce, plain, NAME_AAD)));
  }

  async decryptName(stored: string): Promise<string> {
    const raw = unb64(stored);
    if (raw.length < 12 + 16) throw new VaultError("not an encrypted name");
    return dec.decode(await open(this.key, raw.subarray(0, 12), raw.subarray(12), NAME_AAD));
  }

  // ── contents ──
  /** A file's plaintext as stored: header and chunks (vector generation
   *  passes the file key and nonce). */
  async encryptFile(data: Blob, fk = random(32), fnonce = random(12)): Promise<Blob> {
    const header = concat(MAGIC, fnonce, await seal(this.key, fnonce, fk, MAGIC));
    const fileKey = await aesKey(fk);
    const parts: BlobPart[] = [header];
    const count = Math.max(1, Math.ceil(data.size / CHUNK));
    for (let i = 0; i < count; i++) {
      const chunk = new Uint8Array(await data.slice(i * CHUNK, (i + 1) * CHUNK).arrayBuffer());
      parts.push(await seal(fileKey, chunkNonce(i, i === count - 1), chunk, header));
    }
    return new Blob(parts);
  }

  async decryptFile(stored: Bytes): Promise<Bytes> {
    if (stored.length < HEADER + 16 || !MAGIC.every((b, i) => stored[i] === b)) throw new VaultError("not an encrypted file");
    const header = stored.subarray(0, HEADER);
    const fk = await open(this.key, header.subarray(4, 16), header.subarray(16), MAGIC);
    const fileKey = await aesKey(fk);
    const out: Bytes[] = [];
    let at = HEADER;
    for (let i = 0; ; i++) {
      const end = Math.min(at + CHUNK + 16, stored.length);
      const last = end === stored.length;
      out.push(await open(fileKey, chunkNonce(i, last), stored.subarray(at, end), header));
      at = end;
      if (last) return concat(...out);
    }
  }
}

function chunkNonce(i: number, last: boolean): Bytes {
  const n = new Uint8Array(12);
  new DataView(n.buffer).setUint32(7, i);   // uint88 big-endian; i never needs more than 32 bits
  n[11] = last ? 1 : 0;
  return n;
}


// ── uploads into a vault ──────────────────────────────────────────────────
/** An entry of the folder listing, as much of it as a vault upload needs. */
export interface Listed { path: string; folder: string; name: string; kind: string }

/** Files picked or dropped -- loose (relPath "c.txt") or in folders
 *  ("A/B/c.txt") -- made ready to upload into the vault folder `into`:
 *  every name encrypted, and each file. A folder already there under the
 *  same real name is reused, and one made by this batch is shared by its
 *  files; a file whose name is already taken there is skipped. `known`
 *  holds names already decrypted, by stored name. */
export async function encryptForUpload(
  vault: Vault, picked: { file: File; relPath: string }[], into: string,
  listing: Listed[], known: Record<string, string | null> = {},
): Promise<{ files: { file: File; relPath: string; plainPath: string }[]; skipped: number }> {
  const plainOf = async (stored: string) => {
    if (stored in known) return known[stored];
    try { return await vault.decryptName(stored); } catch { return null; }
  };
  // What a folder holds, by real name: read once per folder.
  const seen = new Map<string, Map<string, Listed>>();
  const children = async (folder: string) => {
    let m = seen.get(folder);
    if (!m) {
      m = new Map();
      for (const f of listing.filter((x) => x.folder === folder)) {
        const n = await plainOf(f.name);
        if (n) m.set(n, f);
      }
      seen.set(folder, m);
    }
    return m;
  };
  const made = new Map<string, string>();   // folders this batch makes, by parent + real name
  const files: { file: File; relPath: string; plainPath: string }[] = [];
  let skipped = 0;
  for (const p of picked) {
    const parts = p.relPath.split("/").map((x) => x.normalize("NFC"));
    const name = parts.pop()!;
    let folder = into;
    const stored: string[] = [];
    for (const part of parts) {
      const key = folder + "\0" + part;
      const existing = (await children(folder)).get(part);
      const s = existing?.kind === "folder" ? existing.name : made.get(key) ?? await vault.encryptName(part);
      made.set(key, s);
      stored.push(s);
      folder = folder + "/" + s;
    }
    if ((await children(folder)).has(name)) { skipped++; continue; }
    const storedName = await vault.encryptName(name);
    files.push({
      file: new File([await vault.encryptFile(p.file)], storedName),
      relPath: [...stored, storedName].join("/"),
      plainPath: p.relPath,
    });
  }
  return { files, skipped };
}
