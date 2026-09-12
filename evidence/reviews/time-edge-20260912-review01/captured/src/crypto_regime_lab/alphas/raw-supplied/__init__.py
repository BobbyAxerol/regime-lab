"""Import guard for the raw_supplied alpha tier (guide L01.3).

Importing these modules executes the original alpha source. Guide L01.3 forbids
running the original modules before containment, so any import through the
normal machinery stops here.

Two weaker guards were tried and MEASURED to be insufficient in this session:

  * no ``__init__.py``  -> PEP 420 implicit namespace packages still made
    ``crypto_regime_lab.alphas.raw_supplied.vwap`` importable;
  * a hyphenated directory name -> blocks the ``import`` statement's syntax but
    NOT ``importlib.import_module("...raw-supplied.vwap")``.

LAB-02 adapters read these files as text/AST. To load one deliberately for a
diagnostic, do it explicitly by path inside ``safety.sandbox``.
"""

raise ImportError(
    "crypto_regime_lab.alphas.raw-supplied holds original alpha source and must not be imported. "
    "Guide L01.3 forbids executing the original modules before containment; read them as text/AST "
    "via the LAB-02 adapters, or load one by path inside safety.sandbox."
)
