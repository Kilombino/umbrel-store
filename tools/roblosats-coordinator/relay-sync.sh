#!/bin/sh
# The relay's sync (mounted over the image's /app/sync.sh; run.sh runs it through torsocks every
# two minutes), kept to this relay's own federation:
#  - once an hour, the coordinator list (/app/strfry-db/allowed-order-pubkeys.txt, read by the
#    write policy too) is brought in step with the official federation.json by /app/fedlist.py;
#    on any failure the last good list stays;
#  - with each relay of /app/federation_urls.txt, both ways: orders (38383) of those coordinators
#    and ratings (31986) of them, of the last four weeks; chat wraps (1059) of the last two days only
#    if the list's "sync-kinds" line has 1059 (they carry no federation mark);
#  - as Kilobot does, the orders of the last two weeks up to each public relay of
#    /app/external_urls.txt, so Nostr clients find them too.
# Older events are dropped here.
LIST=/app/strfry-db/allowed-order-pubkeys.txt
python3 /app/fedlist.py --list "$LIST" --seed /app/allowed-order-pubkeys.seed \
  --url "${FEDERATION_JSON_URL:-https://raw.githubusercontent.com/Kilombino/roblosats/roblosats/frontend/static/federation.json}" \
  --own-file /app/own-pubkey.txt --stamp /app/strfry-db/.fedlist-checked --every 3600 \
  || echo "coordinator list not updated, keeping the last good one"

authors=$(sed 's/#.*//' "$LIST" 2>/dev/null | grep -oE '^[[:space:]]*[0-9a-fA-F]{64}' | tr -d ' \t' | sed 's/.*/"&"/' | paste -sd, -)
synckinds=$(sed 's/#.*//' "$LIST" 2>/dev/null | sed -n 's/^[[:space:]]*sync-kinds[[:space:]]*//p')
weeks=$(date -d "4 weeks ago" +%s)
twoweeks=$(date -d "2 weeks ago" +%s)
days=$(date -d "2 days ago" +%s)
if [ -n "$authors" ]; then
  f_orders="{\"kinds\":[38383],\"authors\":[$authors],\"since\":$weeks}"
  f_ratings="{\"kinds\":[31986],\"#p\":[$authors],\"since\":$weeks}"
else
  f_orders="{\"kinds\":[38383],\"since\":$weeks}"
  f_ratings="{\"kinds\":[31986],\"since\":$weeks}"
fi
chats=no
if [ -z "$authors" ] || [ -z "$synckinds" ] || echo " $synckinds " | grep -q " 1059 "; then chats=yes; fi
timeout 30s /app/strfry --config /etc/strfry.conf delete --filter "{\"until\":$weeks}" >/dev/null 2>&1
# Once (0.9.11-1): drop the order events of other federations stored before the write policy.
if [ -n "$authors" ] && [ ! -e /app/strfry-db/.federation-purge-1 ]; then
  foreign=$(timeout 120s /app/strfry --config /etc/strfry.conf scan '{"kinds":[38383]}' 2>/dev/null | python3 -c '
import json, sys
ok = set(sys.argv[1].replace("\"", "").split(","))
seen = set()
for line in sys.stdin:
    try:
        pk = json.loads(line)["pubkey"]
    except Exception:
        continue
    if pk not in ok:
        seen.add(pk)
print(",".join("\"%s\"" % pk for pk in sorted(seen)))' "$authors") \
  && { [ -z "$foreign" ] || timeout 120s /app/strfry --config /etc/strfry.conf delete --filter "{\"kinds\":[38383],\"authors\":[$foreign]}" >/dev/null 2>&1; } \
  && touch /app/strfry-db/.federation-purge-1 && echo "dropped the order events of other federations"
fi
timeout 30s /app/strfry --config /etc/strfry.conf delete --filter "{\"kinds\":[1059],\"until\":$days}" >/dev/null 2>&1
grep -v '^\s*#' /app/federation_urls.txt 2>/dev/null | while read -r url; do
  [ -n "$url" ] || continue
  timeout 300s /app/strfry --config /etc/strfry.conf sync "$url" --filter "$f_orders" --dir both >/dev/null 2>&1 \
    || echo "sync of orders with $url failed"
  timeout 300s /app/strfry --config /etc/strfry.conf sync "$url" --filter "$f_ratings" --dir both >/dev/null 2>&1 \
    || echo "sync of ratings with $url failed"
  if [ "$chats" = yes ]; then
    timeout 300s /app/strfry --config /etc/strfry.conf sync "$url" --filter "{\"kinds\":[1059],\"since\":$days}" --dir both >/dev/null 2>&1 \
      || echo "sync of chats with $url failed"
  fi
done
grep -v '^\s*#' /app/external_urls.txt 2>/dev/null | while read -r url; do
  [ -n "$url" ] || continue
  timeout 120s /app/strfry --config /etc/strfry.conf sync "$url" --filter "{\"kinds\":[38383],\"since\":$twoweeks}" --dir up >/dev/null 2>&1 \
    || echo "publishing orders to $url failed"
done
exit 0
