#!/usr/bin/env python3
# The coordinator's own page (port 81, behind the platform's login; never on the onion): what is
# running, the coordinator's identity, its channels, its settings, its backup, and the request to
# join the federation, signed by its node. Python's standard library plus what the Roblosats image
# already has (grpc, psycopg2, nostr_sdk, requests, gpg). The same file runs on Umbrel and on
# StartOS (PANEL_PLATFORM picks the paths and the wording): Kilombino/umbrel-store
# tools/roblosats-coordinator, copied as is to roblosats-coordinator-startos assets/.
import base64
import hashlib
import html
import io
import json
import os
import re
import secrets
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/usr/src/robosats")

PLATFORM = os.environ.get("PANEL_PLATFORM", "umbrel")
if PLATFORM == "startos":
    P = {
        # The package's defaults (assets/), then nothing of the user's but the page's own file.
        "defaults": ["/startos/defaults.env"], "user": None,
        "data": "/main", "name": "StartOS",
        "restart": "restart the service in StartOS (its page → Restart)",
        "restart_short": "StartOS → this service → Restart",
        "password": "the password of the <b>Admin credentials</b> action in StartOS",
        "lightning": "Install Lightning Fork (Paul's registry, start9.paulscode.com) and create its wallet; this service picks it up by itself.",
        "no_node": "No Bitcoin node: install Knots (BLAKE2b) Companion.",
        "own_backup": "StartOS's own backups (System → Backups) include this service: its identity, settings and database, copied while it is stopped. Restoring one brings the service back as it was, on this or another server.",
    }
else:
    P = {
        # The app's defaults (app/defaults.env, replaced on updates), then the user's own file.
        "defaults": ["/umbrel/defaults.env"], "user": "/umbrel/data/settings.env",
        "data": "/umbrel/data", "name": "Umbrel",
        "restart": "restart the app in Umbrel (right-click its icon → Restart)",
        "restart_short": "Umbrel → this app → Restart",
        "password": "the password Umbrel shows for this app",
        "lightning": "Install Lightning Fork (PaulsCode.Com store) and create its wallet; then restart this app.",
        "no_node": "No Bitcoin node: pick one for this app in Umbrel.",
        "own_backup": "Umbrel's own backups, if you use them, copy this app's data folder too. Keep this file as well: its database copy is taken consistently by PostgreSQL itself, it holds only this coordinator, and it restores on a new Umbrel or on StartOS.",
    }
DATA = P["data"]
LOCAL = DATA + "/panel/settings.local.env"
FEDERATION = DATA + "/panel/federation.json"
RESTORED = DATA + "/panel/restored.json"
LAST_BACKUP = DATA + "/panel/last-backup.json"
WORK = DATA + "/panel/backup"
SECRETS = DATA + "/secrets.env"
TOR_DIR = DATA + "/tor/coordinator"
ONION_FILE = TOR_DIR + "/hostname"
LND_DIR = "/lnd"
MACAROON = "data/chain/bitcoin/mainnet/admin.macaroon"
REPO = "https://github.com/Kilombino/roblosats"
FEDERATION_URL = "https://raw.githubusercontent.com/Kilombino/roblosats/roblosats/frontend/static/federation.json"
GUIDE = "https://github.com/Kilombino/roblosats-deploy/blob/roblosats/COORDINATOR.md"
CSRF = secrets.token_urlsafe(24)
BACKUP_FORMAT = 1
# The onion's keys: what Tor needs to bring the same address back.
TOR_FILES = ("hs_ed25519_secret_key", "hs_ed25519_public_key", "hostname")
# Secrets that travel in a backup; on import the coordinator's identity (SECRET_KEY, NOSTR_NSEC)
# comes back, while the database password and the admin password stay this install's.
SECRET_KEYS = ("SECRET_KEY", "NOSTR_NSEC", "POSTGRES_PASSWORD", "ADMIN_PASSWORD")
RESTORE_SECRETS = ("SECRET_KEY", "NOSTR_NSEC")
MAX_UPLOAD = 512 * 1024 * 1024

# name, label, kind, help
FIELDS = [
    ("COORDINATOR_ALIAS", "Coordinator name", "text", "How robots and the federation see you. Letters, digits and spaces."),
    ("FEE", "Trade fee", "num", "0.0019 = 0.19 % of each trade, split between maker and taker."),
    ("MAKER_FEE_SPLIT", "Maker's share of the fee", "num", "0.105 = the maker pays 10.5 % of the fee, the taker the rest."),
    ("MIN_ORDER_SIZE", "Smallest order (sats)", "int", ""),
    ("MAX_ORDER_SIZE", "Largest order (sats)", "int", "No bigger than what one of your channels can receive and what one can send (see Liquidity). It also caps any single payout to a buyer. The Roblosats apps start a new coordinator at 25M sats and raise that every two weeks."),
    ("MAX_PUBLIC_ORDERS", "Orders in the book at once", "int", ""),
    ("DISABLE_ONCHAIN", "On-chain payouts to buyers", "onchain", "Paid from Lightning Fork's on-chain wallet; offered only when it has the funds."),
    ("MIN_SWAP_AMOUNT", "Smallest on-chain payout (sats)", "int", ""),
    ("MAX_SWAP_AMOUNT", "Largest on-chain payout (sats)", "int", ""),
    ("DEVFUND", "Donation to Roblosats", "num", "Share of your fees, by keysend to the Roblosats maintainer (0.1 = 10 %)."),
    ("NOTICE_SEVERITY", "Notice on your page", "severity", ""),
    ("NOTICE_MESSAGE", "Notice text", "text", ""),
    ("TELEGRAM_TOKEN", "Telegram bot token", "secret", "Optional. In Telegram, talk to @BotFather, send /newbot and paste the token it gives you. Your robots get their order alerts through this bot."),
    ("TELEGRAM_BOT_NAME", "Telegram bot name", "text", "The bot's username, without the @ (it ends in bot)."),
    ("TELEGRAM_COORDINATOR_CHAT_ID", "Your Telegram chat id", "text", "Where the bot tells you about disputes: send any message to @userinfobot and copy the number it answers (your Id). After restarting, send /start to your own bot once."),
    ("ADMIN_TIME_ZONE", "Time zone of the admin panel", "text", "For example UTC or Europe/Madrid."),
]
# What "Use the recommended values" puts back: the trade terms, not the name, notice or Telegram.
TERMS = ("FEE", "MAKER_FEE_SPLIT", "MIN_ORDER_SIZE", "MAX_ORDER_SIZE", "MAX_PUBLIC_ORDERS", "DISABLE_ONCHAIN",
         "MIN_SWAP_AMOUNT", "MAX_SWAP_AMOUNT", "DEVFUND")
FED_FIELDS = [
    ("contact", "Contact", "An email, a Nostr npub, a Telegram user or a SimpleX link, for robots and the other coordinators."),
    ("motto", "Motto", "One short line."),
    ("description", "Description", "A few lines about your coordinator."),
]


def read_env(path):
    out = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                    v = v[1:-1]
                out[k.strip()] = v
    except OSError:
        pass
    return out


def recommended():
    """The app's own settings (Kilobot's), before anything of the user's."""
    s = {}
    for f in P["defaults"]:
        s.update(read_env(f))
    return s


def base_settings():
    """What applies without the Settings page: the app's, then the user's own file (Umbrel)."""
    s = recommended()
    if P["user"]:
        s.update(read_env(P["user"]))
    return s


def settings():
    s = base_settings()
    s.update(read_env(LOCAL))
    return s


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_atomic(path, text):
    # Private, and owned like its directory (Umbrel's user): docker compose (Umbrel) or run.sh
    # (StartOS) reads it at every start.
    tmp = path + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(text)
    st = os.stat(os.path.dirname(path))
    try:
        os.chown(tmp, st.st_uid, st.st_gid)
    except OSError:
        pass
    os.replace(tmp, path)


def onion():
    try:
        with open(ONION_FILE) as f:
            return f.read().strip()
    except OSError:
        return ""


def nostr_keys():
    nsec = os.environ.get("NOSTR_NSEC", "")
    if not nsec:
        return "", ""
    try:
        from nostr_sdk import Keys
        pk = Keys.parse(nsec).public_key()
        return pk.to_hex(), pk.to_bech32()
    except Exception:
        return "", ""


_stub = None


def lnd():
    global _stub
    if _stub is None:
        import grpc
        from api.lightning import lightning_pb2_grpc
        os.environ["GRPC_SSL_CIPHER_SUITES"] = "HIGH+ECDSA"
        with open(os.path.join(LND_DIR, "tls.cert"), "rb") as f:
            cert = f.read()
        with open(os.path.join(LND_DIR, MACAROON), "rb") as f:
            mac = f.read().hex()
        creds = grpc.composite_channel_credentials(
            grpc.ssl_channel_credentials(cert),
            grpc.metadata_call_credentials(lambda ctx, cb: cb([("macaroon", mac)], None)),
        )
        _stub = lightning_pb2_grpc.LightningStub(grpc.secure_channel(os.environ["LND_GRPC_HOST"], creds))
    return _stub


def lnd_ready():
    return os.path.isfile(os.path.join(LND_DIR, "tls.cert")) and os.path.isfile(os.path.join(LND_DIR, MACAROON))


def lnd_status():
    global _stub
    if not lnd_ready():
        return {"error": "Lightning Fork has no wallet yet (or is not installed): create it in Lightning Fork."}
    try:
        from api.lightning import lightning_pb2 as l
        s = lnd()
        info = s.GetInfo(l.GetInfoRequest(), timeout=5)
        chans = s.ListChannels(l.ListChannelsRequest(active_only=True), timeout=5).channels
        return {
            "alias": info.alias, "pubkey": info.identity_pubkey, "synced": info.synced_to_chain,
            "height": info.block_height, "active": info.num_active_channels,
            "inactive": info.num_inactive_channels, "peers": info.num_peers,
            "local": sum(c.local_balance for c in chans), "remote": sum(c.remote_balance for c in chans),
            "max_local": max((c.local_balance for c in chans), default=0),
            "max_remote": max((c.remote_balance for c in chans), default=0),
        }
    except Exception as e:
        _stub = None
        return {"error": "Lightning Fork does not answer: %s" % (getattr(e, "details", lambda: str(e))() or e)}


def bitcoin_status():
    for p in ("KNOTS_BLAKE2B", "BITCOIN_KNOTS", "BITCOIN"):
        ip, port = os.environ.get("NODE_%s_IP" % p), os.environ.get("NODE_%s_PORT" % p)
        if ip and port:
            try:
                import requests
                r = requests.post("http://%s:%s" % (ip, port), timeout=5,
                                  auth=(os.environ.get("NODE_%s_USER" % p, ""), os.environ.get("NODE_%s_PASS" % p, "")),
                                  json={"jsonrpc": "1.0", "id": "panel", "method": "getblockchaininfo", "params": []})
                b = r.json()["result"]
                return {"blocks": b["blocks"], "ibd": b.get("initialblockdownload", False),
                        "progress": b.get("verificationprogress", 0)}
            except Exception as e:
                return {"error": "The Bitcoin node does not answer (%s:%s): %s" % (ip, port, e.__class__.__name__)}
    return {"error": P["no_node"]}


def db_status():
    try:
        import psycopg2
        c = psycopg2.connect(host="127.0.0.1", port=5432, dbname="roblosats", user="roblosats",
                             password=os.environ.get("POSTGRES_PASSWORD", ""), connect_timeout=3)
        try:
            cur = c.cursor()
            cur.execute("SELECT to_regclass('api_order')")
            if cur.fetchone()[0] is None:
                return {"error": "The database is being created."}
            cur.execute("SELECT count(*) FROM api_order WHERE status BETWEEN 6 AND 11")
            busy = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM api_order WHERE status = 1")
            public = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM api_order WHERE status = 14")
            done = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM api_order WHERE status = 11")
            disputes = cur.fetchone()[0]
            return {"busy": busy, "public": public, "done": done, "disputes": disputes}
        finally:
            c.close()
    except Exception:
        return {"error": "The database is starting."}


def server_status():
    import socket
    try:
        socket.create_connection(("127.0.0.1", 8000), timeout=2).close()
        return {}
    except OSError:
        return {"error": "The Roblosats server is starting (it waits for Tor, Lightning Fork and the database)."}


def live_info():
    """What the coordinator tells robots now (its /api/info), or {} while it starts."""
    try:
        import requests
        return requests.get("http://127.0.0.1:8000/api/info/", headers={"Host": "localhost"}, timeout=4).json()
    except Exception:
        return {}


def pending_restart(s, live):
    """The saved settings that the running coordinator does not use yet."""
    if not live:
        return []
    out = []
    try:
        if abs(float(live.get("maker_fee", 0)) + float(live.get("taker_fee", 0)) - float(s.get("FEE", "0"))) > 1e-7:
            out.append("fee")
    except ValueError:
        pass
    for key, name in (("MIN_ORDER_SIZE", "min_order_size"), ("MAX_ORDER_SIZE", "max_order_size")):
        if str(live.get(name, "")) != s.get(key, "").strip():
            out.append(key.lower().replace("_", " "))
    if live.get("node_alias", "") != s.get("NODE_ALIAS", s.get("COORDINATOR_ALIAS", "")):
        out.append("name")
    if live.get("notice_message", "") != s.get("NOTICE_MESSAGE", ""):
        out.append("notice")
    return out


_fed = {"at": 0, "onions": None, "keys": None}


def listed(on, nhex="", force=False):
    """Whether the federation published in Roblosats lists this coordinator, by its onion or its
    Nostr key (checked every 10 minutes, or now with force). None when the list can't be read."""
    if force or time.time() - _fed["at"] > 600:
        try:
            import requests
            d = requests.get(FEDERATION_URL, timeout=6).json()
            _fed["onions"] = {str(v.get("mainnet", {}).get("onion", "")).replace("http://", "").strip("/") for v in d.values()}
            _fed["keys"] = {str(v.get("nostrHexPubkey", "")).lower() for v in d.values()}
        except Exception:
            pass
        _fed["at"] = time.time()
    if _fed["onions"] is None:
        return None
    return bool(on and on in _fed["onions"]) or bool(nhex and nhex.lower() in _fed["keys"])


def short_alias(alias):
    a = re.sub(r"[^a-z0-9]", "", alias.lower())[:20]
    return a if len(a) >= 2 else "mycoordinator"


def federation_entry(s, on, nhex, npub, node, fed):
    """This coordinator's entry as federation.json keeps it (roblosats-deploy tools/federation-template.json),
    ready for tools/add_coordinator.py."""
    c = fed.get("contact", "").strip()
    contact = {"telegram": "", "nostr": npub, "simplex": "", "email": "", "website": ""}
    if c.startswith("npub1"):
        contact["nostr"] = c
    elif "simplex" in c:
        contact["simplex"] = c
    elif c.startswith("@") or "t.me/" in c:
        contact["telegram"] = c
    elif re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", c):
        contact["email"] = c
    elif c:
        contact["website"] = c
    a = short_alias(s.get("COORDINATOR_ALIAS", ""))
    return {a: {
        "longAlias": s.get("COORDINATOR_ALIAS", ""), "shortAlias": a, "identifier": a,
        "description": fed.get("description", ""), "motto": fed.get("motto", ""), "color": "#8b7cf6",
        "established": time.strftime("%Y-%m-%d", time.gmtime(fed.get("signed_at") or time.time())),
        "nostrHexPubkey": nhex, "contact": contact,
        "badges": {"isFounder": False, "donatesToDevFund": int(round(float(s.get("DEVFUND", "0") or 0) * 100)),
                   "hasGoodOpSec": True, "hasLargeLimits": False},
        "policies": {"Privacy Policy": ""},
        "mainnet": {"onion": "http://" + on, "clearnet": None, "i2p": None},
        "testnet": {"onion": None, "clearnet": None, "i2p": None},
        "mainnetNodesPubkeys": [node] if node else [], "testnetNodesPubkeys": [], "federated": True}}


def restart_note(s=None, live=None):
    s = s if s is not None else settings()
    live = live if live is not None else live_info()
    p = pending_restart(s, live)
    if not p:
        return ""
    return ('<div class="note warn">Saved settings not in use yet (%s): %s when no order is in progress.</div>') % (
        esc(", ".join(p)), P["restart"])


def sats(n):
    return "{:,}".format(int(n))


def esc(s):
    return html.escape(str(s), quote=True)


CSS = """
:root{--bg:#0f1115;--card:#171a21;--line:#262b36;--fg:#e6e8ee;--mute:#9aa3b2;--ok:#3fb950;--warn:#d29922;--bad:#f85149;--acc:#8b7cf6}
@media (prefers-color-scheme: light){:root{--bg:#f6f7f9;--card:#fff;--line:#e3e6eb;--fg:#15181e;--mute:#5d6675;--acc:#5b4bd6}}
a{color:var(--acc)}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:860px;margin:0 auto;padding:20px 16px 60px}h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:0 0 12px}
.sub{color:var(--mute);margin:0 0 18px}nav{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 18px}
nav a,.btn{display:inline-block;padding:7px 12px;border:1px solid var(--line);border-radius:8px;color:var(--fg);text-decoration:none;background:var(--card);cursor:pointer;font:inherit}
.btn.p{background:var(--acc);border-color:var(--acc);color:#fff}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0 0 14px}
.row{display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-top:1px solid var(--line)}.row:first-of-type{border-top:0}
.k{color:var(--mute)}.v{text-align:right;overflow-wrap:anywhere}
.ok{color:var(--ok)}.mute{color:var(--mute)}.warn{color:var(--warn)}.bad{color:var(--bad)}
code{font:13px ui-monospace,monospace;overflow-wrap:anywhere}
label{display:block;margin:12px 0 4px;font-weight:600}.help{color:var(--mute);font-size:13px;margin:2px 0 0}
input,select,textarea{width:100%;padding:8px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);font:inherit}
.copy{margin-left:6px;padding:2px 8px;font-size:12px}.note{padding:10px 12px;border-radius:8px;border:1px solid var(--line);margin:0 0 14px}
.chk{list-style:none;padding:0;margin:0}.chk li{display:flex;gap:10px;padding:8px 0;border-top:1px solid var(--line)}.chk li:first-child{border-top:0}
.chk .i{flex:0 0 22px;font-weight:700}.chk .t{flex:1}.chk .d{color:var(--mute);font-size:13px}.bar{height:6px;border-radius:3px;background:var(--line);margin:0 0 12px;overflow:hidden}.bar i{display:block;height:100%;background:var(--ok)}
.note.ok{border-color:var(--ok)}.note.warn{border-color:var(--warn)}.note.bad{border-color:var(--bad)}
ol{padding-left:20px}li{margin:4px 0}
"""

JS = """
document.querySelectorAll('[data-copy]').forEach(b=>b.addEventListener('click',()=>{
 const t=b.getAttribute('data-copy');
 (navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(()=>{b.textContent='Copied'},()=>{
  const a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();document.execCommand('copy');a.remove();b.textContent='Copied'});
 setTimeout(()=>{b.textContent='Copy'},1500)}));
"""


def page(title, body, refresh=False):
    meta = '<meta http-equiv="refresh" content="10">' if refresh else ""
    return ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            '<meta name=viewport content="width=device-width,initial-scale=1">%s<title>%s</title><style>%s</style></head>'
            "<body><main><h1>Roblosats Coordinator</h1><p class=sub>Your coordinator on Bitcoin (BLAKE2b)</p>"
            '<nav><a href="/setup/">Status</a><a href="/setup/settings">Settings</a><a href="/setup/federation">Join the federation</a><a href="/setup/backup">Backup</a>'
            '<a href="/coordinator/">Admin panel</a><a href="%s" target=_blank rel=noopener>Guide</a></nav>%s'
            "<script>%s</script></main></body></html>") % (meta, esc(title), CSS, GUIDE, body, JS)


def row(k, v, cls=""):
    return '<div class=row><span class=k>%s</span><span class="v %s">%s</span></div>' % (k, cls, v)


def copyable(text):
    if not text:
        return '<span class=warn>not yet</span>'
    return '<code>%s</code><button class="btn copy" data-copy="%s">Copy</button>' % (esc(text), esc(text))


def status_page():
    on, (nhex, npub), ln, btc, db, srv, s = onion(), nostr_keys(), lnd_status(), bitcoin_status(), db_status(), server_status(), settings()
    live = live_info() if not srv.get("error") else {}
    fed = read_json(FEDERATION)
    ok = lambda b: '<span class=ok>●</span> ' if b else '<span class=bad>●</span> '
    parts = []
    starting = bool(srv.get("error") or db.get("error") or not on)
    if starting:
        parts.append('<div class="note warn">Starting… this page refreshes itself. The first start creates the database and the onion, and can take a few minutes.</div>')
    parts.append(restore_note())
    parts.append(restart_note(s, live))

    # The way to a running coordinator, ticked as each step is done.
    mx = int(s.get("MAX_ORDER_SIZE", "0") or 0)
    ln_ok = not ln.get("error")
    liq_ok = ln_ok and ln["active"] > 0 and min(ln["max_local"], ln["max_remote"]) >= mx
    is_listed = listed(on, nhex) if on else False
    last_backup = read_json(LAST_BACKUP).get("at", 0)
    steps = [
        (ln_ok, "Lightning Fork with a wallet", P["lightning"] if not ln_ok else "%s · %s" % (esc(ln["alias"] or "no alias"), "synced" if ln["synced"] else "syncing")),
        (not btc.get("error") and not btc.get("ibd"), "Bitcoin node synced", esc(btc.get("error") or ("syncing %.1f %%" % (btc["progress"] * 100) if btc.get("ibd") else "block %s" % btc.get("blocks")))),
        (liq_ok, "Channels for your largest order", ("Open channels in Lightning Fork that can both receive and send at least %s sats (your largest order), or lower it in <a href=\"/setup/settings\">Settings</a>." % sats(mx)) if not liq_ok else "inbound and outbound above %s sats" % sats(mx)),
        (s.get("COORDINATOR_ALIAS", "My coordinator") not in ("", "My coordinator") and "name" not in pending_restart(s, live), "Your name, fees and limits", "Set them in <a href=\"/setup/settings\">Settings</a> and restart the app." if s.get("COORDINATOR_ALIAS", "My coordinator") in ("", "My coordinator") else esc(s.get("COORDINATOR_ALIAS"))),
        (bool(s.get("TELEGRAM_TOKEN")), "Telegram alerts (optional)", "A bot for your robots' order alerts and your dispute alerts: <a href=\"/setup/settings\">Settings</a>."),
        (bool(last_backup), "A backup of your coordinator", ("Exported on %s. Export again after changing settings." % time.strftime("%Y-%m-%d", time.gmtime(last_backup))) if last_backup else
         "Your onion, Nostr key, settings and database in one encrypted file: <a href=\"/setup/backup\">Backup</a>. Keep it off this server."),
        (bool(db.get("done")), "A first trade", "Open Roblosats with Tor Browser, add your onion under Coordinators, and buy and sell a small amount with two robots, paying from a wallet on another node." if not db.get("done") else "%s finished" % db["done"]),
        (bool(fed.get("signature")) and fed.get("onion") == on, "Request to join the federation", "Your node signs it on <a href=\"/setup/federation\">Join the federation</a>; send it on GitHub or Telegram."),
        (bool(is_listed), "Listed in the federation", ("Listed in the federation ✓" if is_listed else ("Request signed: waiting to be added. Roblosats apps and webs won't list you until a Roblosats release includes you." if fed.get("signature") and fed.get("onion") == on else "Shown in every Roblosats app, web and relay once you are added.")) if is_listed is not None else "Could not check the published list right now."),
    ]
    done = sum(1 for d, _, _ in steps if d)
    items = "".join('<li><span class="i %s">%s</span><span class=t>%s<br><span class=d>%s</span></span></li>' % (
        "ok" if d else "mute", "✓" if d else "○", t, h) for d, t, h in steps)
    parts.append('<div class=card><h2>Getting started · %d of %d</h2><div class=bar><i style="width:%d%%"></i></div><ul class=chk>%s</ul></div>' % (
        done, len(steps), done * 100 // len(steps), items))

    st = [row(ok(on) + "Tor", "onion ready" if on else "creating the onion…")]
    st.append(row(ok(ln_ok) + "Lightning Fork", esc(ln["error"]) if not ln_ok else
                  "%s · %s · block %s" % (esc(ln["alias"] or "no alias"), "synced" if ln["synced"] else "syncing", ln["height"])))
    st.append(row(ok(not btc.get("error") and not btc.get("ibd")) + "Bitcoin node", esc(btc["error"]) if btc.get("error") else
                  ("block %s%s" % (btc["blocks"], " · syncing %.1f %%" % (btc["progress"] * 100) if btc["ibd"] else ""))))
    st.append(row(ok(not db.get("error")) + "Database", esc(db.get("error") or "ready")))
    st.append(row(ok(not srv.get("error")) + "Roblosats server", esc(srv.get("error") or "running")))
    if not db.get("error"):
        st.append(row("Orders", "%s in the book · %s in progress%s · %s finished" % (db["public"], db["busy"],
                      " (don't restart now)" if db["busy"] else "", db["done"]), "warn" if db["busy"] else ""))
        if db["disputes"]:
            st.append(row("Disputes", '<a href="/coordinator/api/order/?status__exact=11">%s open: solve them in the admin panel</a>' % db["disputes"], "warn"))
    parts.append('<div class=card><h2>Status</h2>%s</div>' % "".join(st))

    if live:
        fee = float(live.get("maker_fee", 0)) + float(live.get("taker_fee", 0))
        pub = [row("Name", esc(live.get("node_alias", ""))),
               row("Trade fee", "%.2f %% (maker %.3f %% · taker %.3f %%)" % (fee * 100, float(live.get("maker_fee", 0)) * 100, float(live.get("taker_fee", 0)) * 100)),
               row("Orders", "%s to %s sats" % (sats(live.get("min_order_size", 0)), sats(live.get("max_order_size", 0)))),
               row("On-chain payouts", "up to %s sats" % sats(live.get("max_swap", 0)) if live.get("swap_enabled") else "off"),
               row("Donation to Roblosats", "%g %% of fees" % float(live.get("devfund", 0))),
               row("Version", "Roblosats %s.%s.%s · LND %s" % (live.get("version", {}).get("major", "?"), live.get("version", {}).get("minor", "?"),
                                                          live.get("version", {}).get("patch", "?"), esc(live.get("lnd_version", ""))))]
        parts.append('<div class=card><h2>What robots see</h2>%s<p class=help>Read from your coordinator just now. If it differs from Settings, restart the app.</p></div>' % "".join(pub))

    ident = [row("Onion", copyable(on)),
             row("Nostr key (hex)", copyable(nhex)), row("Nostr key (npub)", copyable(npub)),
             row("Node id", copyable(ln.get("pubkey", "")))]
    parts.append('<div class=card><h2>Identity</h2>%s<p class=help>Robots can reach your coordinator by its onion right away: in Roblosats, Coordinators → add one by its address. To be listed for everyone, join the federation. Your onion and Nostr key are your coordinator\'s identity: they are kept in this app\'s data and in %s backups of it; keep a copy of your own from <a href="/setup/backup">Backup</a>. Its private key never leaves your server and is never shown here; if you lose it, you would have to join the federation again under a new key.</p></div>' % ("".join(ident), P["name"]))

    if ln_ok:
        lim = min(ln["max_local"], ln["max_remote"])
        liq = [row("Active channels", "%s (%s inactive) · %s peers" % (ln["active"], ln["inactive"], ln["peers"])),
               row("Can send (outbound)", "%s sats · largest channel %s" % (sats(ln["local"]), sats(ln["max_local"]))),
               row("Can receive (inbound)", "%s sats · largest channel %s" % (sats(ln["remote"]), sats(ln["max_remote"]))),
               row("Largest order", "%s sats" % sats(mx), "warn" if mx > lim else "ok")]
        tip = ("<p class='help warn'>Your largest order (%s sats) is bigger than what one channel can receive or send (%s sats): "
               "lower it in Settings, or open channels with more capacity.</p>" % (sats(mx), sats(lim))) if mx > lim else \
              "<p class=help>The bonds and the seller's escrow come in through your inbound capacity; buyers are paid from your outbound capacity. Keep both above your largest order, ideally twice, for several orders at once.</p>"
        parts.append('<div class=card><h2>Liquidity</h2>%s%s</div>' % ("".join(liq), tip))

    parts.append('<div class=card><h2>Day to day</h2><ul>'
                 '<li>Orders, disputes and robots: the <a href="/coordinator/">admin panel</a> (user <code>admin</code>, %s).</li>'
                 '<li>A dispute: read both robots\' chat in the order, ask them for proof, and settle it for one of them.</li>'
                 '<li>Never restart or update the app while an order is in progress.</li>'
                 '<li>Keep a copy of your coordinator from <a href="/setup/backup">Backup</a> somewhere else, and again after changing its settings.</li>'
                 '<li>Questions: <a href="https://t.me/roblosats" target=_blank rel=noopener>t.me/roblosats</a>.</li></ul></div>' % P["password"])
    return page("Status", "".join(parts), refresh=starting)


def shown(name, kind, val):
    if kind == "onchain":
        return "on" if str(val).lower() == "false" else "off"
    if kind == "int":
        try:
            return sats(val)
        except ValueError:
            return val
    return val


def field_html(name, label, kind, help_, val, rec):
    if kind == "onchain":
        ctl = '<select name="%s"><option value="True"%s>Off</option><option value="False"%s>On</option></select>' % (
            name, " selected" if val.lower() != "false" else "", " selected" if val.lower() == "false" else "")
    elif kind == "severity":
        ctl = '<select name="%s">%s</select>' % (name, "".join(
            '<option%s>%s</option>' % (" selected" if val == o else "", o) for o in ("none", "info", "warning", "error", "success")))
    elif kind == "secret":
        ctl = '<input name="%s" type=password autocomplete=off placeholder="%s">' % (name, "set (leave empty to keep)" if val else "")
    else:
        ctl = '<input name="%s" value="%s"%s>' % (name, esc(val), ' inputmode=decimal' if kind in ("int", "num") else "")
    hint = esc(help_)
    if name in TERMS and rec is not None:
        r = esc(shown(name, kind, rec))
        if str(val) == str(rec):
            hint += (" " if hint else "") + '<span class=ok>Recommended (%s).</span>' % r
        else:
            hint += (" " if hint else "") + '<span class=warn>Recommended: %s.</span>' % r
    return '<label>%s</label>%s%s' % (esc(label), ctl, '<p class=help>%s</p>' % hint if hint else "")


def settings_page(msg="", cls="ok"):
    s, rec = settings(), recommended()
    db = db_status()
    form = "".join(field_html(n, l, k, h, s.get(n, ""), rec.get(n)) for n, l, k, h in FIELDS)
    note = '<div class="note %s">%s</div>' % (cls, msg) if msg else ""
    busy = ('<div class="note warn">%s orders are in progress: restart only when they finish.</div>' % db["busy"]) if db.get("busy") else ""
    busy += restart_note(s)
    differ = [n for n in TERMS if str(s.get(n, "")) != str(rec.get(n, ""))]
    reset = ""
    if differ:
        reset = ('<div class=card><h2>Recommended values</h2><p>The app recommends the fees and limits Kilobot, the first Roblosats '
                 'coordinator, runs with. Yours differ in: %s.</p><form method=post action="/setup/settings/recommended">'
                 '<input type=hidden name=csrf value="%s"><p><button class=btn>Use the recommended values</button></p></form>'
                 '<p class=help>Only fees, order limits, on-chain payouts and the donation; your name, notice and Telegram stay. '
                 'Then restart, when no order is in progress.</p></div>') % (
            esc(", ".join(l for n, l, _, _ in FIELDS if n in differ)), CSRF)
    body = ('%s%s<div class=card><h2>Settings</h2><form method=post action="/setup/settings">'
            '<input type=hidden name=csrf value="%s">%s<p><button class="btn p">Save</button></p></form>'
            '<p class=help>Saved settings take effect when the app restarts (%s). Never restart while an order is in progress.</p></div>%s') % (
        note, busy, CSRF, form, P["restart_short"], reset)
    return page("Settings", body)


VALID = {
    "int": re.compile(r"^\d{1,12}$"),
    "num": re.compile(r"^\d{0,3}(\.\d{1,6})?$"),
}


def write_local(local):
    text = "# Written by the app's Settings page: only what differs from the app's settings; read after them.\n" + \
        "".join("%s='%s'\n" % (k, v) for k, v in sorted(local.items()))
    write_atomic(LOCAL, text)


def save_settings(form):
    base = base_settings()
    local = read_env(LOCAL)
    new = dict(base)
    new.update(local)
    for name, label, kind, _ in FIELDS:
        if name not in form:
            continue
        v = form[name].strip()
        if kind == "secret" and v == "":
            continue
        if "\n" in v or "'" in v or len(v) > 300:
            return "%s: no quotes or line breaks, please." % esc(label), "bad"
        if kind in VALID and v and not VALID[kind].match(v):
            return "%s: that is not a number." % esc(label), "bad"
        if kind == "onchain" and v not in ("True", "False"):
            return "%s: pick one." % esc(label), "bad"
        new[name] = v
    if not re.match(r"^[A-Za-z0-9 ._-]{1,40}$", new.get("COORDINATOR_ALIAS", "")):
        return "Coordinator name: letters, digits, spaces, dots, dashes; up to 40.", "bad"
    new["NODE_ALIAS"] = new["COORDINATOR_ALIAS"]
    try:
        if int(new.get("MIN_ORDER_SIZE", "0")) > int(new.get("MAX_ORDER_SIZE", "0")):
            return "The smallest order is bigger than the largest.", "bad"
    except ValueError:
        pass
    # Keep only what differs from the app's settings, so that better defaults in an update
    # still reach what the user never changed.
    names = {n for n, _, _, _ in FIELDS} | {"NODE_ALIAS"}
    out = {k: v for k, v in local.items() if k not in names}
    out.update({k: new[k] for k in names if k in new and str(new[k]) != str(base.get(k, ""))})
    write_local(out)
    return "Saved. To apply it, %s." % P["restart"], "ok"


def use_recommended():
    local = {k: v for k, v in read_env(LOCAL).items() if k not in TERMS}
    write_local(local)
    if P["user"] and os.path.exists(P["user"]):
        # The user's own file (Umbrel's data/settings.env) may set them too: comment those out.
        with open(P["user"]) as f:
            lines = f.read().splitlines()
        out = []
        for line in lines:
            k = line.split("=", 1)[0].strip()
            out.append(("# " + line) if "=" in line and not line.lstrip().startswith("#") and k in TERMS else line)
        rewrite_in_place(P["user"], "\n".join(out) + "\n")
    return "The recommended values are saved. To apply them, %s." % P["restart"], "ok"


def rewrite_in_place(path, text):
    """Rewrite a file keeping its inode, owner and mode (a single file may be bind-mounted)."""
    with open(path, "r+") as f:
        f.seek(0)
        f.write(text)
        f.truncate()


def federation_page(sig="", msg="", cls="ok"):
    on, (nhex, npub), ln, s, fed = onion(), nostr_keys(), lnd_status(), settings(), read_json(FEDERATION)
    sig = sig or fed.get("signature", "") if fed.get("onion") == on else sig
    text = "Roblosats federation: %s" % on if on else ""
    missing = []
    if not on:
        missing.append("the onion (Tor is still creating it)")
    if ln.get("error"):
        missing.append("Lightning Fork (%s)" % esc(ln["error"]))
    if not nhex:
        missing.append("the Nostr key")
    if s.get("COORDINATOR_ALIAS", "My coordinator") in ("", "My coordinator"):
        missing.append('your name (in <a href="/setup/settings">Settings</a>, then restart)')
    note = '<div class="note %s">%s</div>' % (cls, msg) if msg else ""
    is_listed = listed(on, nhex, force=True) if on else False
    signed = bool(fed.get("signature")) and fed.get("onion") == on
    if is_listed:
        where = '<div class="note ok"><b>Listed in the federation ✓</b> Every Roblosats app, web and relay shows your coordinator.</div>'
    elif is_listed is None:
        where = '<div class="note warn">Could not read the published federation list right now (%s); try again later.</div>' % esc(FEDERATION_URL)
    elif signed:
        where = ('<div class="note warn"><b>Waiting to be added to the federation.</b> Your request was signed on %s. '
                 'Roblosats apps and webs won\'t list you until a Roblosats release includes you; this page checks the published list and turns green then. '
                 'Meanwhile robots can still reach you by adding your onion under Coordinators.</div>') % time.strftime("%Y-%m-%d", time.gmtime(fed.get("signed_at") or 0))
    else:
        where = '<div class="note">Not in the federation yet: robots reach you only if they add your onion by hand.</div>'
    ident = "".join([row("Name", esc(s.get("COORDINATOR_ALIAS", ""))), row("Onion", copyable(on)),
                     row("Nostr public key (hex)", copyable(nhex)), row("Nostr public key (npub)", copyable(npub)),
                     row("Lightning node id", copyable(ln.get("pubkey", "")))])
    ident = ('<div class=card><h2>What you send</h2>%s<p class=help>Public data only. The Nostr key is your coordinator\'s identity: '
             'it is kept in this app\'s data and in ' + P["name"] + '\'s backups (and in your <a href="/setup/backup">exported backup</a>), its private key is never shown or sent, and losing it means '
             'joining the federation again under a new key.</p></div>') % ident
    fields = "".join('<label>%s</label>%s<p class=help>%s</p>' % (
        esc(l), ('<textarea name="%s" rows=3>%s</textarea>' if n == "description" else '<input name="%s" value="%s">') % (n, esc(fed.get(n, ""))), esc(h))
        for n, l, h in FED_FIELDS)
    parts = [note, """<div class=card><h2>Join the federation</h2>
<p>Coordinators in the federation appear in every Roblosats app, web and relay. To join, your node signs a message with your onion, and you send that with your details as an issue on GitHub; once it is checked, you are added in the next release.</p>
<ol><li>Fill in the details below and press <b>Sign with my node</b>.</li><li>Press <b>Open the request on GitHub</b>: it opens with everything filled in; submit it (you need a GitHub account).</li>
<li>Attach your coordinator's avatar to the issue (a square image, 200×200 or larger).</li>
<li>No GitHub? Copy the request and send it on Telegram, <a href="https://t.me/roblosats" target=_blank rel=noopener>t.me/roblosats</a>.</li>
<li>Wait for the next Roblosats release that includes you: this page then shows <b>Listed in the federation ✓</b>.</li></ol></div>"""]
    parts.insert(1, where)
    parts.append(ident)
    if missing:
        parts.append('<div class="note warn">Not ready yet: %s.</div>' % "; ".join(missing))
    parts.append('<div class=card><form method=post action="/setup/federation"><input type=hidden name=csrf value="%s">%s'
                 '<p><button class="btn p"%s>Sign with my node</button></p></form></div>' % (CSRF, fields, " disabled" if missing else ""))
    if sig and on:
        entry = json.dumps(federation_entry(s, on, nhex, npub, ln.get("pubkey", ""), fed), indent=2, ensure_ascii=False)
        body = ("Alias: %s\nOnion: %s\nNostr public key (hex): %s\nNostr public key (npub): %s\nNode id: %s\nContact: %s\nMotto: %s\nDescription: %s\n\n"
                "Signed message: %s\nSignature: %s\n(check: lncli verifymessage --msg \"%s\" --sig %s)\n\nFee: %s · Orders: %s to %s sats\n\n"
                "Entry for federation.json:\n```json\n%s\n```\n") % (
            s.get("COORDINATOR_ALIAS", ""), on, nhex, npub, ln.get("pubkey", ""), fed.get("contact", ""), fed.get("motto", ""),
            fed.get("description", ""), text, sig, text, sig, s.get("FEE", ""), s.get("MIN_ORDER_SIZE", ""), s.get("MAX_ORDER_SIZE", ""), entry)
        url = REPO + "/issues/new?" + urllib.parse.urlencode({"title": "Join the federation: %s" % s.get("COORDINATOR_ALIAS", ""), "body": body})
        parts.append('<div class=card><h2>Your request</h2><p><code style="white-space:pre-wrap">%s</code></p>'
                     '<p><a class="btn p" href="%s" target=_blank rel=noopener>Open the request on GitHub</a> '
                     '<button class=btn data-copy="%s">Copy</button></p></div>' % (esc(body), esc(url), esc(body)))
    return page("Join the federation", "".join(parts))


def sign_federation(form):
    on = onion()
    if not on:
        return "", "Tor has not created the onion yet.", "bad"
    fed = read_json(FEDERATION)
    for n, l, _ in FED_FIELDS:
        v = form.get(n, "").strip()
        if len(v) > (600 if n == "description" else 200):
            return "", "%s is too long." % esc(l), "bad"
        fed[n] = v
    try:
        from api.lightning import lightning_pb2 as l
        r = lnd().SignMessage(l.SignMessageRequest(msg=("Roblosats federation: %s" % on).encode()), timeout=10)
    except Exception as e:
        return "", "Lightning Fork did not sign: %s" % esc(getattr(e, "details", lambda: str(e))() or e), "bad"
    fed.update({"onion": on, "signature": r.signature, "signed_at": int(time.time())})
    write_atomic(FEDERATION, json.dumps(fed, indent=1))
    return r.signature, "Signed by your node.", "ok"


# ---- Backup: one encrypted file with the coordinator's identity, settings and database ----

def pg():
    import psycopg2
    return psycopg2.connect(host="127.0.0.1", port=5432, dbname="roblosats", user="roblosats",
                            password=os.environ.get("POSTGRES_PASSWORD", ""), connect_timeout=5)


def db_facts():
    """Orders by state and the applied migrations of this install's database (None while it is
    being created)."""
    c = pg()
    try:
        cur = c.cursor()
        cur.execute("SELECT to_regclass('api_order')")
        if cur.fetchone()[0] is None:
            return None
        cur.execute("SELECT count(*), count(*) FILTER (WHERE status BETWEEN 6 AND 11) FROM api_order")
        total, busy = cur.fetchone()
        cur.execute("SELECT app || '.' || name FROM django_migrations")
        migrations = sorted(r[0] for r in cur.fetchall())
        return {"orders": total, "busy": busy, "migrations": migrations}
    finally:
        c.close()


def db_tool(op, timeout=600):
    """Ask the db-tool service (PostgreSQL's image: pg_dump, psql) for a dump or a restore."""
    os.makedirs(WORK, mode=0o700, exist_ok=True)
    for ext in ("done", "err"):
        try:
            os.remove("%s/%s.%s" % (WORK, op, ext))
        except OSError:
            pass
    with open("%s/%s.req" % (WORK, op), "w"):
        pass
    end = time.time() + timeout
    while time.time() < end:
        if os.path.exists("%s/%s.done" % (WORK, op)):
            os.remove("%s/%s.done" % (WORK, op))
            return
        if os.path.exists("%s/%s.err" % (WORK, op)):
            with open("%s/%s.err" % (WORK, op)) as f:
                err = f.read().strip()[-600:]
            os.remove("%s/%s.err" % (WORK, op))
            raise RuntimeError("the database %s failed: %s" % (op, err or "no message"))
        time.sleep(0.5)
    try:
        os.remove("%s/%s.req" % (WORK, op))
    except OSError:
        pass
    raise RuntimeError("the database helper (db-tool) did not answer: is the app fully started?")


def gpg(args, data, passphrase):
    """OpenPGP symmetric encryption (AES-256, a SHA-512 key derivation iterated 65M times, with an
    integrity check): any gpg decrypts the file with the passphrase, here or by hand."""
    with tempfile.TemporaryDirectory(prefix="g") as home:
        r, w = os.pipe()
        os.write(w, passphrase.encode())
        os.close(w)
        try:
            p = subprocess.run(["gpg", "--homedir", home, "--batch", "--yes", "--no-tty", "--quiet",
                                "--pinentry-mode", "loopback", "--no-symkey-cache", "--passphrase-fd", str(r)] + args,
                               input=data, capture_output=True, pass_fds=(r,), timeout=600)
        finally:
            os.close(r)
            subprocess.run(["gpgconf", "--homedir", home, "--kill", "all"], capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode(errors="replace").strip()[-300:] or "gpg failed")
    return p.stdout


def encrypt(data, passphrase):
    return gpg(["--symmetric", "--cipher-algo", "AES256", "--s2k-mode", "3", "--s2k-digest-algo", "SHA512",
                "--s2k-count", "65011712", "--compress-algo", "none", "--output", "-"], data, passphrase)


def decrypt(data, passphrase):
    return gpg(["--decrypt", "--output", "-"], data, passphrase)


def parse_env(text):
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        out[k.strip()] = v
    return out


def update_secrets(values):
    """Set some keys of secrets.env, keeping its other lines and its quoting (Umbrel quotes,
    StartOS doesn't)."""
    with open(SECRETS) as f:
        lines = f.read().splitlines()
    seen, out = set(), []
    for line in lines:
        k = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and k in values:
            q = "'" if line.split("=", 1)[1].strip()[:1] == "'" else ""
            out.append("%s=%s%s%s" % (k, q, values[k], q))
            seen.add(k)
        else:
            out.append(line)
    for k, v in values.items():
        if k not in seen:
            out.append("%s=%s" % (k, v))
    rewrite_in_place(SECRETS, "\n".join(out) + "\n")


def django_password(password):
    """Django's own pbkdf2_sha256 format, so the admin login works without loading Django here."""
    salt = "".join(secrets.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(22))
    it = 1000000
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), it)
    return "pbkdf2_sha256$%d$%s$%s" % (it, salt, base64.b64encode(h).decode())


def add_file(tar, name, data, mode=0o600):
    ti = tarfile.TarInfo(name)
    ti.size, ti.mode, ti.mtime = len(data), mode, int(time.time())
    tar.addfile(ti, io.BytesIO(data))


def export_backup(form):
    pw, pw2 = form.get("passphrase", ""), form.get("passphrase2", "")
    if len(pw) < 12:
        raise ValueError("The passphrase needs 12 characters or more.")
    if pw != pw2:
        raise ValueError("The two passphrases differ.")
    on, (nhex, npub), s = onion(), nostr_keys(), settings()
    if not on or not os.path.exists(os.path.join(TOR_DIR, "hs_ed25519_secret_key")):
        raise ValueError("Tor has not created the onion yet.")
    facts = db_facts()
    if facts is None:
        raise ValueError("The database is still being created.")
    db_tool("dump")
    dump = os.path.join(WORK, "dump.sql")
    with open(dump, "rb") as f:
        sql = f.read()
    os.remove(dump)
    sec = read_env(SECRETS)
    manifest = {
        "format": BACKUP_FORMAT, "kind": "roblosats-coordinator-backup", "created": int(time.time()),
        "platform": PLATFORM, "package_version": os.environ.get("APP_VERSION", ""),
        "alias": s.get("COORDINATOR_ALIAS", ""), "onion": on, "nostr_hex": nhex, "npub": npub,
        "orders": facts["orders"], "orders_in_progress": facts["busy"], "migrations": facts["migrations"],
    }
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        add_file(tar, "manifest.json", json.dumps(manifest, indent=1).encode(), 0o644)
        add_file(tar, "secrets.env", "".join("%s=%s\n" % (k, sec[k]) for k in SECRET_KEYS if sec.get(k)).encode())
        for n in TOR_FILES:
            with open(os.path.join(TOR_DIR, n), "rb") as f:
                add_file(tar, "tor/" + n, f.read())
        for name, path in (("settings/settings.local.env", LOCAL), ("settings/federation.json", FEDERATION),
                           ("settings/settings.env", P["user"])):
            if path and os.path.exists(path):
                with open(path, "rb") as f:
                    add_file(tar, name, f.read())
        add_file(tar, "db.sql", sql)
    name = "roblosats-coordinator-%s-%s.backup.gpg" % (short_alias(s.get("COORDINATOR_ALIAS", "")), time.strftime("%Y%m%d-%H%M"))
    data = encrypt(buf.getvalue(), pw)
    write_atomic(LAST_BACKUP, json.dumps({"at": int(time.time()), "onion": on}))
    return name, data


ALLOWED = {"manifest.json", "secrets.env", "db.sql", "settings/settings.local.env", "settings/federation.json",
           "settings/settings.env"} | {"tor/" + n for n in TOR_FILES}


def import_backup(data, pw, confirm, replace):
    """Restore a backup onto this install: the database now (through db-tool), then the onion's
    keys, the identity secrets and the settings, which apply when the app restarts."""
    if not data:
        raise ValueError("Pick the backup file.")
    if not confirm:
        raise ValueError("Tick the box that the old coordinator is off for good.")
    try:
        plain = decrypt(data, pw)
    except RuntimeError as e:
        raise ValueError("Could not decrypt the file: wrong passphrase, or not a coordinator backup (%s)." % e)
    files = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(plain), mode="r:gz") as tar:
            for m in tar.getmembers():
                if m.isfile() and m.name in ALLOWED:
                    files[m.name] = tar.extractfile(m).read()
    except tarfile.TarError:
        raise ValueError("The decrypted file is not a coordinator backup.")
    try:
        man = json.loads(files["manifest.json"])
    except (KeyError, ValueError):
        raise ValueError("The backup has no manifest.")
    if man.get("kind") != "roblosats-coordinator-backup" or man.get("format") != BACKUP_FORMAT:
        raise ValueError("Unknown backup format.")
    sec = parse_env(files.get("secrets.env", b"").decode())
    if not re.fullmatch(r"[0-9a-f]{64}", sec.get("NOSTR_NSEC", "")) or not re.fullmatch(r"[0-9a-f]{64}", sec.get("SECRET_KEY", "")):
        raise ValueError("The backup lacks the coordinator's keys.")
    if any("tor/" + n not in files for n in TOR_FILES) or "db.sql" not in files:
        raise ValueError("The backup lacks the onion's keys or the database.")
    host = files["tor/hostname"].decode().strip()
    if not re.fullmatch(r"[a-z2-7]{56}\.onion", host):
        raise ValueError("The backup's onion is not valid.")

    facts = db_facts()
    if facts is None:
        raise ValueError("This install's database is still being created: wait until the app has started.")
    if facts["busy"]:
        raise ValueError("This install has %s orders in progress: a backup only goes onto a new, empty install." % facts["busy"])
    if facts["orders"] and not replace:
        raise ValueError("This install already has %s orders. A backup goes onto a new install; to replace them anyway, tick the second box." % facts["orders"])
    newer = sorted(set(man.get("migrations", [])) - set(facts["migrations"]))
    if newer:
        raise ValueError("The backup comes from a newer version of the coordinator (%s): update this app first." % ", ".join(newer[:3]))

    # The database: replaced in one transaction; the server's processes reconnect to it.
    os.makedirs(WORK, mode=0o700, exist_ok=True)
    with open(os.open(os.path.join(WORK, "restore.sql"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
        f.write(files["db.sql"])
    db_tool("restore")
    # The admin login stays this install's (the password the platform shows).
    admin = os.environ.get("ADMIN_PASSWORD", "")
    if admin:
        c = pg()
        try:
            cur = c.cursor()
            cur.execute("UPDATE auth_user SET password = %s WHERE username = %s",
                        (django_password(admin), os.environ.get("ESCROW_USERNAME", "admin")))
            c.commit()
        finally:
            c.close()

    # The onion's keys: Tor serves them from its next start.
    os.makedirs(TOR_DIR, mode=0o700, exist_ok=True)
    st = os.stat(TOR_DIR)
    for n in os.listdir(TOR_DIR):
        p = os.path.join(TOR_DIR, n)
        if os.path.isfile(p) and n not in TOR_FILES:
            os.remove(p)
    for n in TOR_FILES:
        p = os.path.join(TOR_DIR, n)
        tmp = p + ".tmp"
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
            f.write(files["tor/" + n])
        try:
            os.chown(tmp, st.st_uid, st.st_gid)
        except OSError:
            pass
        os.replace(tmp, p)

    # The coordinator's identity (Django's key, the Nostr key), from its next start.
    update_secrets({k: sec[k] for k in RESTORE_SECRETS})

    # Settings and the federation request.
    local = files.get("settings/settings.local.env")
    user = files.get("settings/settings.env")
    names = {n for n, _, _, _ in FIELDS} | {"NODE_ALIAS"}
    if user and not P["user"]:
        # From Umbrel to StartOS: the user's own settings file joins the page's.
        merged = {k: v for k, v in parse_env(user.decode()).items() if k in names}
        merged.update(parse_env(local.decode()) if local else {})
        write_local(merged)
    else:
        if local is not None:
            write_atomic(LOCAL, local.decode())
        elif os.path.exists(LOCAL):
            os.remove(LOCAL)
        if user is not None and P["user"] and os.path.exists(P["user"]):
            rewrite_in_place(P["user"], user.decode())
    if "settings/federation.json" in files:
        write_atomic(FEDERATION, files["settings/federation.json"].decode())
    info = {"at": int(time.time()), "onion": host, "npub": man.get("npub", ""), "nostr_hex": man.get("nostr_hex", ""),
            "alias": man.get("alias", ""), "created": man.get("created", 0), "orders": man.get("orders", 0),
            "orders_in_progress": man.get("orders_in_progress", 0), "from": man.get("platform", "")}
    write_atomic(RESTORED, json.dumps(info))
    return info


def restore_pending():
    """A restore whose identity the running services don't use yet (they need a restart)."""
    r = read_json(RESTORED)
    if not r:
        return None
    if r.get("nostr_hex") and r["nostr_hex"] == nostr_keys()[0]:
        try:
            os.remove(RESTORED)
        except OSError:
            pass
        return None
    return r


def restore_note():
    r = restore_pending()
    if not r:
        return ""
    return ('<div class="note bad"><b>Backup restored: restart now.</b> The database is back; the onion <code>%s</code> and '
            'the Nostr key <code>%s</code> take over when you %s. Until then this install still shows its old identity.</div>') % (
        esc(r["onion"]), esc(r.get("npub", "")), P["restart"])


BACKUP_EXPORT = """<div class=card><h2>Export a backup</h2>%s
<p>One file with everything that makes this coordinator itself: its secrets (Django's key, the Nostr key, the database and
admin passwords), the onion's keys, your settings and federation request, and a copy of the database (orders, robots, rewards,
disputes). The relay's events are left out: they come back from the federation.</p>
<p>The file is encrypted with your passphrase (OpenPGP, AES-256). Without the passphrase nobody can use it, and nobody can
recover it for you: write it down. Keep the file off this server (your computer, a USB stick, a password manager), and export
again after changing settings.</p>
<form method=post action="/setup/backup/export"><input type=hidden name=csrf value="%s">
<label>Passphrase</label><input name=passphrase type=password autocomplete=new-password minlength=12 required>
<label>Passphrase again</label><input name=passphrase2 type=password autocomplete=new-password minlength=12 required>
<p class=help>12 characters or more; a few unrelated words are best.</p>
<p><button class="btn p">Download the encrypted backup</button></p></form>
<p class=help>By hand: <code>gpg -d FILE.backup.gpg &gt; backup.tar.gz</code> asks for the passphrase and gives a tar.gz with
manifest.json, secrets.env, tor/ (the onion's keys), settings/ and db.sql (a PostgreSQL dump).</p></div>"""

BACKUP_IMPORT = """<div class=card><h2>Import a backup</h2>
<div class="note warn"><b>Only onto a new install, and only once the old coordinator is off for good.</b> Two coordinators
with the same onion and Nostr key at once fight over the address and publish the same orders twice. Orders that were in
progress when the backup was taken hold invoices in the old Lightning node: they come back as records, not as payments.</div>
<form method=post action="/setup/backup/import" enctype="multipart/form-data"><input type=hidden name=csrf value="%s">
<label>Backup file</label><input name=file type=file accept=".gpg" required>
<label>Passphrase</label><input name=passphrase type=password autocomplete=off required>
<label><input type=checkbox name=confirm value=1 style="width:auto"> The old coordinator is off and will not run again</label>
<label><input type=checkbox name=replace value=1 style="width:auto"> Replace this install's own orders%s</label>
<p><button class="btn p">Restore</button></p></form>
<p class=help>The database is replaced right away; the onion, the Nostr key and your settings take over at the next restart
(%s), which this page asks for. The admin password stays this install's: %s. Your Lightning node is not in this backup:
restore Lightning Fork from its own seed and channel backup; if its node id changes, tell the federation.</p></div>"""


def backup_page(msg="", cls="ok"):
    on, (nhex, npub) = onion(), nostr_keys()
    try:
        facts = db_facts()
    except Exception:
        facts = None
    note = '<div class="note %s">%s</div>' % (cls, msg) if msg else ""
    parts = [note, restore_note()]
    parts.append('<div class=card><h2>Your coordinator\'s identity</h2>%s<p class=help>The onion is where robots and the federation '
                 'reach you; the Nostr key signs your orders. Both are in the backup below: if your server breaks, a new install '
                 'restored from it comes back with the same onion, the same Nostr key and the same orders, robots and rewards.</p></div>' % "".join([
                     row("Onion", copyable(on)), row("Nostr key (npub)", copyable(npub)), row("Nostr key (hex)", copyable(nhex))]))
    busy = ""
    if facts and facts["busy"]:
        busy = ('<div class="note warn">%s orders are in progress. A backup taken now has them, but their hold invoices live in '
                'Lightning Fork, not here: back up when none is in progress if you can.</div>') % facts["busy"]
    parts.append(BACKUP_EXPORT % (busy, CSRF))
    parts.append(BACKUP_IMPORT % (CSRF, (" (it has %s)" % facts["orders"]) if facts and facts["orders"] else " (it has none)",
                                  P["restart_short"], P["password"]))
    parts.append('<div class=card><h2>%s\'s own backups</h2><p>%s</p></div>' % (P["name"], P["own_backup"]))
    return page("Backup", "".join(parts))


def multipart(ctype, body):
    """Fields of a multipart/form-data body (Python 3.13 has no cgi module)."""
    from email.parser import BytesParser
    from email.policy import HTTP
    msg = BytesParser(policy=HTTP).parsebytes(b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + body)
    out = {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if name:
            out[name] = part.get_payload(decode=True) or b""
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "roblosats-panel"

    def log_message(self, *a):
        pass

    def send(self, body, code=200):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path.rstrip("/")
        try:
            if p in ("", "/setup"):
                return self.send(status_page())
            if p == "/setup/settings":
                return self.send(settings_page())
            if p == "/setup/federation":
                return self.send(federation_page())
            if p == "/setup/backup":
                return self.send(backup_page())
        except Exception as e:
            return self.send(page("Error", '<div class="note bad">%s</div>' % esc(e)), 500)
        self.send(page("Not found", '<div class="note warn">Not found.</div>'), 404)

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path.rstrip("/")
        n = int(self.headers.get("Content-Length") or 0)
        if n > (MAX_UPLOAD if p == "/setup/backup/import" else 20000):
            return self.send(page("Error", '<div class="note bad">Too big.</div>'), 413)
        body = self.rfile.read(n)
        if p == "/setup/backup/import":
            try:
                raw = multipart(self.headers.get("Content-Type", ""), body)
            except Exception:
                raw = {}
            form = {k: v.decode(errors="replace") for k, v in raw.items() if k != "file"}
        else:
            raw = {}
            form = {k: v[0] for k, v in urllib.parse.parse_qs(body.decode(errors="replace"), keep_blank_values=True).items()}
        if not secrets.compare_digest(form.get("csrf", ""), CSRF):
            return self.send(page("Expired", '<div class="note warn">This page had expired: open it again.</div>'), 403)
        if p == "/setup/settings":
            msg, cls = save_settings(form)
            return self.send(settings_page(msg, cls))
        if p == "/setup/settings/recommended":
            msg, cls = use_recommended()
            return self.send(settings_page(msg, cls))
        if p == "/setup/federation":
            sig, msg, cls = sign_federation(form)
            return self.send(federation_page(sig, msg, cls))
        if p == "/setup/backup/export":
            try:
                name, data = export_backup(form)
            except (ValueError, RuntimeError, OSError) as e:
                return self.send(backup_page(esc(e), "bad"))
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % name)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if p == "/setup/backup/import":
            try:
                info = import_backup(raw.get("file", b""), form.get("passphrase", ""), form.get("confirm") == "1",
                                     form.get("replace") == "1")
            except (ValueError, RuntimeError, OSError) as e:
                return self.send(backup_page(esc(e), "bad"))
            msg = ("Restored <b>%s</b> (backup of %s, %s orders). Now %s." % (
                esc(info["alias"]), time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(info["created"])), info["orders"], P["restart"]))
            return self.send(backup_page(msg, "ok"))
        self.send(page("Not found", '<div class="note warn">Not found.</div>'), 404)


if __name__ == "__main__":
    os.makedirs(os.path.dirname(LOCAL), exist_ok=True)
    # A leftover of an interrupted export or import (the database dump) does not stay around.
    for n in ("dump.sql", "dump.sql.tmp", "restore.sql"):
        try:
            os.remove(os.path.join(WORK, n))
        except OSError:
            pass
    ThreadingHTTPServer(("127.0.0.1", 8090), Handler).serve_forever()
