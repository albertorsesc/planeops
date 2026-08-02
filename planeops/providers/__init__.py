"""The third-party ring: frameworks and drivers live here, nowhere else.

One capability package per third-party library the engine consumes. Each
package's `__init__` is the PORT (neutral names, no vendor in any signature)
and each vendor implementation is one leaf module named after the library.
Swapping a library is: add a sibling leaf, repoint the port's import.

The rule is mechanical, not aspirational: the architecture fitness tests map
every third-party import name to its one sanctioned home under this package
and fail the suite on an import anywhere else.
"""
