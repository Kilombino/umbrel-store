#!/bin/sh
# The relay's sync (mounted over the image's /app/sync.sh; run.sh runs it through torsocks every
# two minutes). With each relay of /app/federation_urls.txt, both ways: orders (38383) and ratings
# (31986) of the last four weeks, chat wraps (1059) of the last two days (a trade's chat lasts
# hours; weeks of them from a busy relay took the first sync past ten minutes). Then, as Kilobot
# does, the orders of the last two weeks up to each public relay of /app/external_urls.txt, so
# Nostr clients find them too. Older events are dropped here.
weeks=$(date -d "4 weeks ago" +%s)
twoweeks=$(date -d "2 weeks ago" +%s)
days=$(date -d "2 days ago" +%s)
timeout 30s /app/strfry --config /etc/strfry.conf delete --filter "{\"until\":$weeks}" >/dev/null 2>&1
timeout 30s /app/strfry --config /etc/strfry.conf delete --filter "{\"kinds\":[1059],\"until\":$days}" >/dev/null 2>&1
grep -v '^\s*#' /app/federation_urls.txt 2>/dev/null | while read -r url; do
  [ -n "$url" ] || continue
  timeout 300s /app/strfry --config /etc/strfry.conf sync "$url" --filter "{\"kinds\":[38383,31986],\"since\":$weeks}" --dir both >/dev/null 2>&1 \
    || echo "sync of orders and ratings with $url failed"
  timeout 300s /app/strfry --config /etc/strfry.conf sync "$url" --filter "{\"kinds\":[1059],\"since\":$days}" --dir both >/dev/null 2>&1 \
    || echo "sync of chats with $url failed"
done
grep -v '^\s*#' /app/external_urls.txt 2>/dev/null | while read -r url; do
  [ -n "$url" ] || continue
  timeout 120s /app/strfry --config /etc/strfry.conf sync "$url" --filter "{\"kinds\":[38383],\"since\":$twoweeks}" --dir up >/dev/null 2>&1 \
    || echo "publishing orders to $url failed"
done
exit 0
