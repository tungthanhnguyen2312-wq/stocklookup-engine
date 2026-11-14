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

## Rebaseline after completed Daily registry advancement

Keep the original inventory and its sync receipt. For an authorized rebaseline,
run the reviewed release-sync tool in read-only mode from the frozen Producer
checkout with the active retained-evidence profile. Pass the full Producer
head recorded with the original inventory.

    python -B <reviewed-source>/tools/sync_producer_release.py --inventory <original-inventory> --rebaseline-from <original-head> --history-root <verified-git-store>

The history store must contain the observed checkout and live canonical main.
The tool requires each intervening registry change to be a first-parent,
registry-only Daily commit adding one matching session to both ledgers. It
checks retained completion records, the pending freeze classifier, protected
source byte hashes and artifact self-identities. Removing those exact additions
must reproduce the original registry byte hash. Keep the JSON returned on
stdout beside the original inventory. Its original and current inventories,
commit identities and completion record hashes form the audit trail.

Save the result's `inventory` object separately for the existing
`--approved-head` sync command. Sync continues to require exact registry and
protected source bytes and unchanged protected Git paths across the target
fast-forward. Future verified Daily registry advancement can be reconciled by
running the same read-only proof from the original receipt. Use a new reviewed
disposition if the frozen inputs or pending sessions actually change.
