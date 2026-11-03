#!/bin/bash
# Mempool Kilombino exports. umbreld sources this under `set -euo pipefail` for this
# app and every app depending on it: nothing here may exit non-zero.

# Lightning Fork (PaulsCode.Com store), when installed: its read-only macaroon and
# TLS certificate are mounted into the api container. umbrelOS injects only the env
# of required dependencies, so its REST address is written out
# (paulscode-lightning-fork/exports.sh: APP_LIGHTNING_FORK_NODE_IP, REST port 8180).
# Absent, the mount points at an empty directory of this app's own.
kilombino_mempool_lnd_dir="$(dirname "${EXPORTS_APP_DIR:-/nonexistent/x}" 2>/dev/null || true)/paulscode-lightning-fork/data/lnd"
if [ -d "${kilombino_mempool_lnd_dir}" ]; then
  export APP_KILOMBINO_MEMPOOL_LIGHTNING_FORK="true"
  export APP_KILOMBINO_MEMPOOL_LND_DIR="${kilombino_mempool_lnd_dir}"
else
  export APP_KILOMBINO_MEMPOOL_LIGHTNING_FORK="false"
  export APP_KILOMBINO_MEMPOOL_LND_DIR="${EXPORTS_APP_DIR:-/nonexistent}/data/no-lightning"
fi
unset kilombino_mempool_lnd_dir
export APP_KILOMBINO_MEMPOOL_LND_REST_URL="https://10.21.21.66:8180"
