#!/bin/bash
# Mempool Kilombino exports. umbreld sources this under `set -euo pipefail` for this
# app and every app depending on it: nothing here may exit non-zero.

# A Lightning node, when installed: Lightning XBT from this store first, else Paul's
# Lightning Fork (PaulsCode.Com store). Its read-only macaroon and TLS certificate are
# mounted into the api container. umbrelOS injects only the env of required
# dependencies, so the REST addresses are written out: Lightning XBT's
# (kilombino-lightning-xbt/exports.sh: 10.21.21.86, REST port 8181) and Lightning
# Fork's (paulscode-lightning-fork/exports.sh: 10.21.21.66, REST port 8180). Absent,
# the mount points at an empty directory of this app's own.
kilombino_mempool_apps_dir="$(dirname "${EXPORTS_APP_DIR:-/nonexistent/x}" 2>/dev/null || true)"
export APP_KILOMBINO_MEMPOOL_LIGHTNING_FORK="false"
export APP_KILOMBINO_MEMPOOL_LND_DIR="${EXPORTS_APP_DIR:-/nonexistent}/data/no-lightning"
export APP_KILOMBINO_MEMPOOL_LND_REST_URL="https://10.21.21.86:8181"
if [ -d "${kilombino_mempool_apps_dir}/kilombino-lightning-xbt/data/lnd" ]; then
  export APP_KILOMBINO_MEMPOOL_LIGHTNING_FORK="true"
  export APP_KILOMBINO_MEMPOOL_LND_DIR="${kilombino_mempool_apps_dir}/kilombino-lightning-xbt/data/lnd"
elif [ -d "${kilombino_mempool_apps_dir}/paulscode-lightning-fork/data/lnd" ]; then
  export APP_KILOMBINO_MEMPOOL_LIGHTNING_FORK="true"
  export APP_KILOMBINO_MEMPOOL_LND_DIR="${kilombino_mempool_apps_dir}/paulscode-lightning-fork/data/lnd"
  export APP_KILOMBINO_MEMPOOL_LND_REST_URL="https://10.21.21.66:8180"
fi
unset kilombino_mempool_apps_dir

# The web UI on umbrel_main_network, whose nginx serves /api/v1/fees/recommended
# and /api/block-height/<n>: Lightning Fork's dashboard reads this line (with sed,
# never sourcing this file) to offer this app for fee rates and transaction links.
export APP_KILOMBINO_MEMPOOL_MEMPOOL_API="http://kilombino-mempool_web_1:8080"
