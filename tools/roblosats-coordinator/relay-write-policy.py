#!/usr/bin/env python3
# strfry write policy plugin: keeps this relay to its own federation (the same rules as Kilobot's).
#
#  - order events (kind 38383, NIP-69): only when signed by a federation coordinator;
#  - ratings (kind 31986): only when they rate (p tag) a federation coordinator;
#  - events that arrive by `strfry sync`/`stream` from another relay: only the kinds listed in a
#    "sync-kinds" line (if there is one). What clients and the coordinator publish directly (gift
#    wraps 1059, chat, account recovery...) is not affected.
#
# List: /app/strfry-db/allowed-order-pubkeys.txt (or $ALLOWED_ORDER_PUBKEYS), one coordinator hex
# pubkey per line (# comments allowed), plus optionally "sync-kinds 38383 31986". It is kept in
# step with federation.json by /app/fedlist.py (run from the sync every hour) and re-read here when
# it changes. With no pubkeys in it the plugin accepts everything (fail open).
import json
import os
import re
import sys

LIST = os.environ.get("ALLOWED_ORDER_PUBKEYS", "/app/strfry-db/allowed-order-pubkeys.txt")
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
state = {"key": None, "allowed": set(), "sync_kinds": set()}


def load_list():
    try:
        st = os.stat(LIST)
        key = (st.st_ino, st.st_size, st.st_mtime_ns)
    except OSError:
        key = "none"
    if key == state["key"]:
        return
    state["key"] = key
    allowed, sync_kinds = set(), set()
    try:
        with open(LIST) as f:
            for line in f:
                line = line.split("#", 1)[0]
                m = re.match(r"^\s*sync-kinds\s+(.*)$", line)
                if m:
                    sync_kinds.update(int(k) for k in re.findall(r"\d+", m.group(1)))
                    continue
                line = re.sub(r"\s+", "", line)
                if HEX64.match(line):
                    allowed.add(line.lower())
    except OSError:
        pass
    state["allowed"], state["sync_kinds"] = allowed, sync_kinds
    if not allowed:
        print("write-policy: no pubkeys in %s, accepting everything" % LIST, file=sys.stderr, flush=True)


def verdict(req):
    ev = req.get("event") or {}
    kind = ev.get("kind", -1)
    load_list()
    allowed = state["allowed"]
    if not allowed:
        return "accept", ""
    if req.get("sourceType") in ("Sync", "Stream") and state["sync_kinds"] and kind not in state["sync_kinds"]:
        return "reject", "blocked: kind not synced from other relays"
    if kind == 38383 and str(ev.get("pubkey", "")).lower() not in allowed:
        return "reject", "blocked: order events are only accepted from this federation"
    if kind == 31986:
        ps = [str(t[1]).lower() for t in ev.get("tags") or []
              if isinstance(t, list) and len(t) > 1 and t[0] == "p"]
        if not any(p in allowed for p in ps):
            return "reject", "blocked: ratings are only accepted for this federation"
    return "accept", ""


for line in sys.stdin:
    action, msg, eid = "accept", "", ""
    try:
        req = json.loads(line)
        eid = (req.get("event") or {}).get("id", "")
        action, msg = verdict(req)
    except Exception:
        m = re.search(r'"id"\s*:\s*"([0-9a-f]{64})"', line)
        eid = m.group(1) if m else eid
        action, msg = "accept", ""
    res = {"id": eid, "action": action}
    if msg:
        res["msg"] = msg
    sys.stdout.write(json.dumps(res) + "\n")
    sys.stdout.flush()
