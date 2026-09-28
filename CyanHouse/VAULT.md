# Encrypted folders (vaults) — format v1

An encrypted folder of the Documents library is a *vault*. The server stores
it and serves it, but never holds anything that decrypts it: every key is
derived and used in the browser (`react_ui/src/vault.ts`) or the app
(`android_ui/.../net/Vault.kt`). The two implement exactly this document.

All binary values in JSON are base64 (standard alphabet, with padding).
AES-GCM is AES-256 with a 12-byte nonce and a 16-byte tag appended to the
ciphertext.

## The vault file

The vault's top folder holds `.cyanhouse-vault.json` (hidden from listings,
protected by the server):

```json
{
  "v": 1,
  "kdf": {"alg": "argon2id", "m": 65536, "t": 3, "p": 1},
  "password": {"salt": "<16 bytes>", "nonce": "<12 bytes>", "key": "<48 bytes>"},
  "recovery": {"salt": "<16 bytes>", "nonce": "<12 bytes>", "key": "<48 bytes>"}
}
```

- **Master key** `MK`: 32 random bytes, made when the vault is created. It
  never changes, so changing the password only rewrites this file.
- **Unlocking**: `KEK = Argon2id(secret, salt, m KiB, t passes, p lanes,
  32 bytes)`, then `MK = AES-GCM-decrypt(KEK, nonce, key, aad = "cyanhouse-vault-v1")`.
  A wrong secret fails the GCM tag: that is how a wrong password is told.
- **Secrets**: the password as UTF-8 after Unicode NFC normalisation; or the
  recovery code as its 32 characters (see below) — the same unlock, its own
  salt and wrap.
- **Recovery code**: 20 random bytes in Crockford base32
  (`0123456789ABCDEFGHJKMNPQRSTVWXYZ`), 32 characters, shown as four groups
  of eight joined by `-`. Typed back, it is upper-cased, `-` and spaces are
  dropped, and `O`→`0`, `I`/`L`→`1`, before use as the secret.

## Names

Every file and folder *inside* the vault (not the vault folder itself) has
an encrypted name:

    base64url-no-padding( nonce(12) || AES-GCM(MK, nonce, utf8(NFC(name)), aad = "cyanhouse-name-v1") )

with a fresh random nonce each time, so the same name encrypts differently
twice. A name may be at most 150 UTF-8 bytes, which keeps the stored name
within 255 bytes. Stored names never start with `.`.

## File contents

    header  = "CHV1" (4 bytes) || fnonce (12) || wrapped (48)
    wrapped = AES-GCM(MK, fnonce, FK, aad = "CHV1")

`FK` is 32 random bytes, a new one for every file (and every new version of
it). The plaintext is then cut into chunks of 65536 bytes (the last one
shorter, possibly empty), each stored as `AES-GCM(FK, nonce_i, chunk_i, aad =
header)` — 16 bytes longer than the chunk — straight after the header, where

    nonce_i = uint88-big-endian(i) || (0x01 if chunk i is the last, else 0x00)

An empty file is one empty last chunk. A reader decrypts chunk by chunk and
checks the file ends exactly after a chunk whose nonce says it is the last:
a file cut short, reordered or spliced with another fails.

## What the server enforces

- A vault is private to its owner, and stays so.
- Nothing moves between a vault and the outside (or another vault): that
  would mix encrypted and plain files. Within a vault, moves are fine.
- The server offers no text, info, preview or inline view of anything in a
  vault; the raw bytes are served as a download only.
- The vault file itself cannot be renamed, moved, deleted or overwritten
  except through the vault endpoints, by the owner.
