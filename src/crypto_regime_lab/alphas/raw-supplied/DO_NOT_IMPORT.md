# raw_supplied — original alpha sources, do not import

These four files are the `raw_supplied` tier from guide section 2.1: original
bytes kept for provenance. They are read-only and this directory deliberately
has no `__init__.py`, so they are not importable as
`crypto_regime_lab.alphas.raw_supplied.<name>`.

Do not import or execute them. `hash_momentum.py` raises `NameError: np` on
import, and guide L01.3 forbids running the original modules before
containment. LAB-02 builds versioned adapters that read these as text/AST; the
adapters are the only executable path.

Identity is verified against the SHA-256 values published in guide section 1.1.
The archive they came from is retained read-only at
`vendor_readonly/alpha_zip_original.zip`.
