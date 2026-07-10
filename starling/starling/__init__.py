"""
Starling -- a murmuration of free clouds acting as one giant encrypted drive.

Pool the free tiers of storage accounts you already own (or any local folders)
into a single deduplicated, client-side-encrypted, redundant vault. No provider
ever sees your plaintext, your filenames, or a recoverable copy of anything on
its own.

Public surface:
    Vault    -- create/open a vault and put/get/rm/ls/df/fsck/sync
    Policy   -- redundancy policy (replication or Reed-Solomon erasure coding)
"""

from .engine import PutResult, Vault, VaultError
from .placement import Policy

__version__ = "0.1.0"
__all__ = ["Vault", "VaultError", "PutResult", "Policy", "__version__"]
