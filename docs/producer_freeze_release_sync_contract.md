# Explicit Producer release sync with a pending input freeze

An unsealed input freeze is the sole additive registry diff plus its selected
artifact identities. It is separate from historical executable source pins,
reviewed amendments and the capacity receipt. Ordinary Daily still requires
the frozen checkout to be at main before it starts. An operator may use
`python -B tools/sync_producer_release.py --approved-head <sha> --inventory <path>`
from verified released code to synchronize the Producer alone. This operation
does not launch Daily or confer approval on another commit.

Record the registry and selected artifact SHA-256s once from a verified freeze
using `freeze_byte_inventory(root)` and retain the returned inventory outside
the checkout. Retain the same inventory across releases. A different approved
SHA requires its own source review and CI. The active Production profile,
canonical GitHub origin, existing writer leases, clean index, ancestry and live
main must agree. Git must see identical tree entries at the registry and all
selected in-checkout paths. Both the original bytes and freeze identities are
checked again after the fast-forward. A matching retry returns
`FREEZE_PRESERVED_AT_APPROVED_HEAD`.

A release that changes executable sources continues through their existing
reviewed transition and capacity checks. This sync refuses changed freeze paths,
mismatched inventory, divergent history or concurrent writers. Any change to
the protected input data requires its own governing disposition.
