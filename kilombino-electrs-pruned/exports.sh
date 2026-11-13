#!/bin/bash

# Electrs Pruned exports (Paul Lamb's app, copied for Kilombino's store).
# Static IP addresses for this app's containers on Umbrel's Docker network, plus
# the Electrum endpoint other apps can depend on. umbreld sources this under
# `set -euo pipefail`, for this app and every app depending on it: keep it to
# lines that cannot fail.
#
# .102 and .103 (and 10.21.22.102): clear of the official apps (the highest
# below .151 are core-lightning's .94 and .96), of Paul's store (Electrs Pruned
# .70/.71 and 10.21.22.70, Fulcrum Pruned .74/.76, the rest .60 to .78), of
# Horizon's store and of this store's other apps (.86 to .94).

export APP_KILOMBINO_ELECTRS_PRUNED_WEB_IP="10.21.22.102"
export APP_KILOMBINO_ELECTRS_PRUNED_SERVER_IP="10.21.21.102"
export APP_KILOMBINO_ELECTRS_PRUNED_PROXY_IP="10.21.21.103"

# Electrum protocol port (plaintext TCP) served on the internal network.
# Dependent apps should connect to ${SERVER_IP}:${SERVER_PORT}.
export APP_KILOMBINO_ELECTRS_PRUNED_SERVER_PORT="50001"

# The block-fetching proxy's RPC port. Exported because it is a working
# bitcoind-compatible RPC endpoint for a pruned node: it answers getblock for
# blocks the node has dropped. Another app wanting that can use it rather than
# running a second proxy.
export APP_KILOMBINO_ELECTRS_PRUNED_PROXY_PORT="8332"

# ---------------------------------------------------------------------------
# Which node this app indexes is Umbrel's choice, not ours.
#
# `dependencies: [bitcoin]` in umbrel-app.yml makes Umbrel offer every installed app
# declaring `implements: [bitcoin]` and set APP_BITCOIN_* from the one selected. That
# now includes Knots (BLAKE2b) Companion, so the BLAKE2b chain is reachable through
# the same picker as every other node rather than through a second selector of ours.
#
# This app therefore reads APP_BITCOIN_* directly and resolves nothing itself. An
# earlier version served its own settings page for this, written before Umbrel's
# alternatives mechanism was found; it is gone, and the native picker is the one
# place the choice is made.
#
# The p2p port is the whitebind one where the selected node publishes it. 18444-style
# ordinary listeners are shared with inbound peers, where a connection earns no
# permissions and can be evicted to seat another; the whitebind listener grants noban
# and download. electrs does not reconnect its p2p connection, so an eviction ends the
# process, and under a busy wallet that is a restart loop.
export APP_KILOMBINO_ELECTRS_PRUNED_BACKEND_P2P_PORT="${APP_BITCOIN_P2P_WHITEBIND_PORT:-${APP_BITCOIN_P2P_PORT}}"

# Offered as an implementation of paulscode-electrs-pruned (umbrel-app.yml), so an
# app that depends on Paul's Electrs Pruned, Mempool Kilombino from this store
# among them, can select this server instead. Those apps read APP_ELECTRS_PRUNED_*,
# so the names Paul's app exports get this app's values. `:=`, not plain
# assignment, the same as Paul's Fulcrum Pruned does it: when Paul's Electrs
# Pruned itself was selected, its exports are the ones that count, and these fill
# only what is still unset.
for var in WEB_IP SERVER_IP PROXY_IP SERVER_PORT PROXY_PORT BACKEND_P2P_PORT; do
    electrs_var="APP_ELECTRS_PRUNED_${var}"
    kilombino_var="APP_KILOMBINO_ELECTRS_PRUNED_${var}"
    export "$electrs_var"="${!electrs_var:=${!kilombino_var}}"
done
unset var electrs_var kilombino_var
