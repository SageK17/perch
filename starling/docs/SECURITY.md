# Security & threat model

## What Starling protects

Starling assumes the storage providers are **untrusted**. A provider — or anyone
who compromises one, or steals the blobs — should learn nothing useful and be
unable to tamper undetected.

- **Confidentiality.** Every byte stored on a provider is encrypted on your
  machine with AES-256-GCM before upload. Keys are derived from your passphrase
  with scrypt (memory-hard) and never leave your machine; only a random salt is
  stored in `config.json`.
- **Integrity / authenticity.** GCM is authenticated encryption: a modified
  ciphertext fails to decrypt. Each chunk is additionally verified against its
  `SHA-256(plaintext)` on read, and each erasure shard against its own hash, so
  corruption or tampering is caught, not served.
- **Metadata minimization.** Blobs are stored under `HMAC(naming_key, hash‖shard)`
  keys. A provider can't tell which blobs belong to the same file, can't
  recognize a blob it has seen in someone else's vault, and can't derive
  anything from the key. The manifest — which holds filenames and structure —
  is itself encrypted and stored locally.
- **No single point of data.** With replication ≥2 or erasure coding, no single
  provider holds a recoverable copy of a chunk on its own (for erasure, a single
  shard is useless without `k-1` others).

## What it does *not* protect against

- **A weak passphrase.** The passphrase is the whole game. scrypt makes guessing
  expensive, but a short or common passphrase is still guessable. Use a long,
  unique one. There is no recovery if you forget it — by design.
- **Your own machine being compromised.** Keys live in memory while the vault is
  open; malware on your device can read your data. Starling secures data *at the
  providers*, not against a compromised client.
- **Traffic analysis of sizes/timing.** A provider sees blob sizes and upload
  times. Chunk sizes are content-defined and compression varies them, but
  Starling does not pad or add cover traffic.
- **Availability if too many providers vanish at once.** Redundancy tolerates up
  to the policy's limit (`replicas-1`, or `m`). Beyond that, affected chunks are
  lost. Choose a policy with margin and run `fsck --repair` regularly.

## Cryptographic details

| Purpose | Primitive |
| --- | --- |
| Key derivation | scrypt (N=2¹⁵, r=8, p=1) → 32-byte master key |
| Sub-key separation | HKDF-SHA256 → independent encryption and naming keys |
| Chunk encryption | AES-256-GCM (12-byte random nonce, `"STRLNG1"` as AAD) |
| Storage-key naming | HMAC-SHA256(naming_key, plaintext_hash ‖ shard_index) |
| Content addressing / integrity | SHA-256 |

**Fallback cipher.** If the `cryptography` package isn't importable (or its
native bindings are broken), Starling falls back to a standard-library
authenticated stream cipher: an HMAC-SHA256 keystream in counter mode with
encrypt-then-MAC (HMAC-SHA256). This is a sound construction under the standard
assumption that HMAC-SHA256 is a PRF, but AES-256-GCM is preferred and used
whenever available. The algorithm is recorded per-blob, so a vault stays
readable regardless of which was used. `starling df`/the test runner report
which is active.

## The "is this legitimate?" question

Starling is explicitly designed **not** to abuse providers:

- It uses accounts **you own**, within their terms of service.
- It does **not** create or rotate throwaway accounts, defeat quotas, or hide
  data inside a service that prohibits arbitrary blobs.
- The "free huge storage" comes from *pooling your own free tiers* plus
  *deduplication* and *compression* — ordinary, legitimate storage engineering.

If a provider's terms forbid this use, don't point Starling at it. The value is
in the engine, which is equally useful across paid buckets, home NAS folders,
and spare drives.
