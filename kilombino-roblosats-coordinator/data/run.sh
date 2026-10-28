#!/bin/sh
# Every Roblosats service starts through this: it waits for the coordinator's onion and for
# Lightning Fork's credentials, works out what depends on them, then runs the image's entrypoint
# with the service's command. Mounted read-only; secrets.env and settings.env come as env_file.
set -e

onion_file=/tor/coordinator/hostname
until [ -s "$onion_file" ]; do echo "waiting for the coordinator's onion"; sleep 3; done
onion="$(cat "$onion_file")"
if [ "${ROBLOSATS_ROLE:-}" = main ]; then
  echo "Coordinator onion: http://$onion"
  python3 -c "from nostr_sdk import Keys; import os; k=Keys.parse(os.environ['NOSTR_NSEC']).public_key(); print('Coordinator Nostr key:', k.to_hex(), k.to_bech32())" 2>/dev/null || true
fi
export HOST_NAME="$onion" ONION_LOCATION="$onion" HOST_NAME2="localhost" LOCAL_ALIAS="localhost"
export CSRF_TRUSTED_ORIGINS="http://$onion,http://localhost"

# The Bitcoin node picked for the "bitcoin" dependency: the first set with an address and a port.
for p in KNOTS_BLAKE2B BITCOIN_KNOTS BITCOIN; do
  eval "ip=\${NODE_${p}_IP:-} port=\${NODE_${p}_PORT:-}"
  if [ -n "$ip" ] && [ -n "$port" ]; then
    eval "BITCOIND_RPCUSER=\${NODE_${p}_USER:-} BITCOIND_RPCPASSWORD=\${NODE_${p}_PASS:-}"
    BITCOIND_RPCURL="http://$ip:$port"
    export BITCOIND_RPCURL BITCOIND_RPCUSER BITCOIND_RPCPASSWORD
    [ "${ROBLOSATS_ROLE:-}" = main ] && echo "Bitcoin node: $BITCOIND_RPCURL (APP_${p}_*)"
    break
  fi
done
unset NODE_KNOTS_BLAKE2B_PASS NODE_BITCOIN_KNOTS_PASS NODE_BITCOIN_PASS

# Lightning Fork (PaulsCode.Com store): its LND directory, read-only.
export LND_DIR=/lnd MACAROON_PATH=data/chain/bitcoin/mainnet/admin.macaroon
until [ -s "$LND_DIR/tls.cert" ] && [ -s "$LND_DIR/$MACAROON_PATH" ]; do
  echo "waiting for Lightning Fork's tls.cert and admin.macaroon (is Lightning Fork running, with a wallet?)"; sleep 10
done
# Its node id, for the coordinator's info page (asked over gRPC, with the same credentials).
if [ -z "${NODE_ID:-}" ]; then
  NODE_ID="$(cd /usr/src/robosats && NODE_ID= python3 manage.py shell -c "from api.lightning.lnd import LNDNode, lightning_pb2, lightning_pb2_grpc; print(lightning_pb2_grpc.LightningStub(LNDNode.channel).GetInfo(lightning_pb2.GetInfoRequest()).identity_pubkey)" 2>/dev/null | tail -n 1 || true)"
  export NODE_ID
fi

# The superuser the escrow and the admin panel use, with Umbrel's app password, once.
if [ "${ROBLOSATS_ROLE:-}" = main ]; then
  python3 manage.py migrate --noinput
  DJANGO_SUPERUSER_USERNAME="${ESCROW_USERNAME:-admin}" DJANGO_SUPERUSER_PASSWORD="$ADMIN_PASSWORD" DJANGO_SUPERUSER_EMAIL=admin@localhost \
    python3 manage.py createsuperuser --noinput 2>/dev/null && echo "admin user created" || true
else
  # The others wait until the main one has migrated the database.
  until python3 manage.py migrate --check >/dev/null 2>&1; do echo "waiting for the database"; sleep 5; done
fi
unset ADMIN_PASSWORD
exec /usr/src/robosats/scripts/entrypoint.sh "$@"
