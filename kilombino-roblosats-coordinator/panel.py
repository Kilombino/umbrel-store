#!/usr/bin/env python3
# The coordinator's own page on Umbrel's tile (port 81, behind Umbrel's login; never on the onion):
# what is running, the coordinator's identity, its channels, its settings, and the request to join
# the federation, signed by its node. Python's standard library plus what the Roblosats image
# already has (grpc, psycopg2, nostr_sdk, requests). Mounted read-only; its writable state is in
# /umbrel/panel (settings.local.env, read by every service after settings.env; federation.json).
import base64
import html
import json
import os
import re
import secrets
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/usr/src/robosats")

DEFAULTS = "/umbrel/settings.env"
LOCAL = "/umbrel/panel/settings.local.env"
FEDERATION = "/umbrel/panel/federation.json"
ONION_FILE = "/tor/coordinator/hostname"
LND_DIR = "/lnd"
MACAROON = "data/chain/bitcoin/mainnet/admin.macaroon"
REPO = "https://github.com/Kilombino/roblosats"
GUIDE = "https://github.com/Kilombino/roblosats-deploy/blob/roblosats/COORDINATOR.md"
CSRF = secrets.token_urlsafe(24)

# name, label, kind, help
FIELDS = [
    ("COORDINATOR_ALIAS", "Coordinator name", "text", "How robots and the federation see you. Letters, digits and spaces."),
    ("FEE", "Trade fee", "num", "0.002 = 0.2 % of each trade."),
    ("MAKER_FEE_SPLIT", "Maker's share of the fee", "num", "0.125 = the maker pays 12.5 % of the fee, the taker the rest."),
    ("MIN_ORDER_SIZE", "Smallest order (sats)", "int", ""),
    ("MAX_ORDER_SIZE", "Largest order (sats)", "int", "No bigger than what one of your channels can receive and what one can send (see Liquidity)."),
    ("MAX_PUBLIC_ORDERS", "Orders in the book at once", "int", ""),
    ("DISABLE_ONCHAIN", "On-chain payouts to buyers", "onchain", "Needs on-chain funds in Lightning Fork."),
    ("MIN_SWAP_AMOUNT", "Smallest on-chain payout (sats)", "int", ""),
    ("MAX_SWAP_AMOUNT", "Largest on-chain payout (sats)", "int", ""),
    ("DEVFUND", "Donation to Roblosats", "num", "Share of your fees, by keysend to the Roblosats maintainer (0.1 = 10 %)."),
    ("NOTICE_SEVERITY", "Notice on your page", "severity", ""),
    ("NOTICE_MESSAGE", "Notice text", "text", ""),
    ("TELEGRAM_TOKEN", "Telegram bot token", "secret", "From @BotFather: your robots get their order alerts through it."),
    ("TELEGRAM_BOT_NAME", "Telegram bot name", "text", "Without the @."),
    ("TELEGRAM_COORDINATOR_CHAT_ID", "Your Telegram chat id", "text", "Where the bot tells you about disputes."),
    ("ADMIN_TIME_ZONE", "Time zone of the admin panel", "text", "For example UTC or Europe/Madrid."),
]
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


def settings():
    s = read_env(DEFAULTS)
    s.update(read_env(LOCAL))
    return s


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_atomic(path, text):
    # Private, and owned like its directory (the Umbrel user): docker compose reads it as an env_file.
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
    return {"error": "No Bitcoin node: pick one for this app in Umbrel."}


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
            return {"busy": busy, "public": public}
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
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
code{font:13px ui-monospace,monospace;overflow-wrap:anywhere}
label{display:block;margin:12px 0 4px;font-weight:600}.help{color:var(--mute);font-size:13px;margin:2px 0 0}
input,select,textarea{width:100%;padding:8px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);font:inherit}
.copy{margin-left:6px;padding:2px 8px;font-size:12px}.note{padding:10px 12px;border-radius:8px;border:1px solid var(--line);margin:0 0 14px}
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
            '<nav><a href="/setup/">Status</a><a href="/setup/settings">Settings</a><a href="/setup/federation">Join the federation</a>'
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
    ok = lambda b: '<span class=ok>●</span> ' if b else '<span class=bad>●</span> '
    parts = []
    starting = bool(srv.get("error") or db.get("error") or not on)
    if starting:
        parts.append('<div class="note warn">Starting… this page refreshes itself. The first start creates the database and the onion, and can take a few minutes.</div>')
    st = [row(ok(on) + "Tor", "onion ready" if on else "creating the onion…")]
    st.append(row(ok(not ln.get("error")) + "Lightning Fork", esc(ln["error"]) if ln.get("error") else
                  "%s · %s · block %s" % (esc(ln["alias"] or "no alias"), "synced" if ln["synced"] else "syncing", ln["height"])))
    st.append(row(ok(not btc.get("error") and not btc.get("ibd")) + "Bitcoin node", esc(btc["error"]) if btc.get("error") else
                  ("block %s%s" % (btc["blocks"], " · syncing %.1f %%" % (btc["progress"] * 100) if btc["ibd"] else ""))))
    st.append(row(ok(not db.get("error")) + "Database", esc(db.get("error") or "ready")))
    st.append(row(ok(not srv.get("error")) + "Roblosats server", esc(srv.get("error") or "running")))
    if not db.get("error"):
        st.append(row("Orders", "%s in the book · %s in progress%s" % (db["public"], db["busy"],
                      " (don't restart now)" if db["busy"] else "")))
    parts.append('<div class=card><h2>Status</h2>%s</div>' % "".join(st))

    ident = [row("Name", esc(s.get("COORDINATOR_ALIAS", ""))),
             row("Onion", copyable(on)),
             row("Nostr key (hex)", copyable(nhex)), row("Nostr key (npub)", copyable(npub)),
             row("Node id", copyable(ln.get("pubkey", "")))]
    parts.append('<div class=card><h2>Identity</h2>%s<p class=help>Robots can reach your coordinator by its onion right away: in Roblosats, Coordinators → add one by its address. To be listed for everyone, join the federation.</p></div>' % "".join(ident))

    if not ln.get("error"):
        mx = int(s.get("MAX_ORDER_SIZE", "0") or 0)
        lim = min(ln["max_local"], ln["max_remote"])
        liq = [row("Active channels", "%s (%s inactive) · %s peers" % (ln["active"], ln["inactive"], ln["peers"])),
               row("Can send (outbound)", "%s sats · largest channel %s" % (sats(ln["local"]), sats(ln["max_local"]))),
               row("Can receive (inbound)", "%s sats · largest channel %s" % (sats(ln["remote"]), sats(ln["max_remote"]))),
               row("Largest order", "%s sats" % sats(mx), "warn" if mx > lim else "ok")]
        tip = ("<p class='help warn'>Your largest order (%s sats) is bigger than what one channel can receive or send (%s sats): "
               "lower it in Settings, or open channels with more capacity.</p>" % (sats(mx), sats(lim))) if mx > lim else \
              "<p class=help>The bonds and the seller's escrow come in through your inbound capacity; buyers are paid from your outbound capacity. Keep both above your largest order, ideally twice, for several orders at once.</p>"
        parts.append('<div class=card><h2>Liquidity</h2>%s%s</div>' % ("".join(liq), tip))

    steps = """<ol>
<li>Open channels in Lightning Fork, with liquidity both ways.</li>
<li>Set your name, fees and limits in <a href="/setup/settings">Settings</a>, then restart the app in Umbrel.</li>
<li>Try a small buy and a small sell against your own onion, paying from a wallet on another node.</li>
<li><a href="/setup/federation">Join the federation</a>: your node signs the request and you send it.</li>
<li>Look after your orders and disputes in the <a href="/coordinator/">admin panel</a> (user <code>admin</code>, the password Umbrel shows for this app).</li>
</ol>"""
    parts.append('<div class=card><h2>Getting started</h2>%s</div>' % steps)
    return page("Status", "".join(parts), refresh=starting)


def field_html(name, label, kind, help_, val):
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
    return '<label>%s</label>%s%s' % (esc(label), ctl, '<p class=help>%s</p>' % esc(help_) if help_ else "")


def settings_page(msg="", cls="ok"):
    s = settings()
    db = db_status()
    form = "".join(field_html(n, l, k, h, s.get(n, "")) for n, l, k, h in FIELDS)
    note = '<div class="note %s">%s</div>' % (cls, msg) if msg else ""
    busy = ('<div class="note warn">%s orders are in progress: restart only when they finish.</div>' % db["busy"]) if db.get("busy") else ""
    body = ('%s%s<div class=card><h2>Settings</h2><form method=post action="/setup/settings">'
            '<input type=hidden name=csrf value="%s">%s<p><button class="btn p">Save</button></p></form>'
            '<p class=help>Saved settings take effect when the app restarts (Umbrel → this app → Restart). Never restart while an order is in progress.</p></div>') % (note, busy, CSRF, form)
    return page("Settings", body)


VALID = {
    "int": re.compile(r"^\d{1,12}$"),
    "num": re.compile(r"^\d{0,3}(\.\d{1,6})?$"),
}


def save_settings(form):
    s = settings()
    local = read_env(LOCAL)
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
        local[name] = v
    if "COORDINATOR_ALIAS" in local:
        if not re.match(r"^[A-Za-z0-9 ._-]{1,40}$", local["COORDINATOR_ALIAS"]):
            return "Coordinator name: letters, digits, spaces, dots, dashes; up to 40.", "bad"
        local["NODE_ALIAS"] = local["COORDINATOR_ALIAS"]
    try:
        if int(local.get("MIN_ORDER_SIZE", s.get("MIN_ORDER_SIZE", "0"))) > int(local.get("MAX_ORDER_SIZE", s.get("MAX_ORDER_SIZE", "0"))):
            return "The smallest order is bigger than the largest.", "bad"
    except ValueError:
        pass
    text = "# Written by the app's Settings page; read by every service after settings.env.\n" + \
        "".join("%s='%s'\n" % (k, v) for k, v in sorted(local.items()))
    write_atomic(LOCAL, text)
    return "Saved. Restart the app in Umbrel to apply it.", "ok"


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
    fields = "".join('<label>%s</label>%s<p class=help>%s</p>' % (
        esc(l), ('<textarea name="%s" rows=3>%s</textarea>' if n == "description" else '<input name="%s" value="%s">') % (n, esc(fed.get(n, ""))), esc(h))
        for n, l, h in FED_FIELDS)
    parts = [note, """<div class=card><h2>Join the federation</h2>
<p>Coordinators in the federation appear in every Roblosats app, web and relay. To join, your node signs a message with your onion, and you send that with your details as an issue on GitHub; once it is checked, you are added in the next release.</p>
<ol><li>Fill in the details below and press <b>Sign with my node</b>.</li><li>Press <b>Open the request on GitHub</b>: it opens with everything filled in; submit it (you need a GitHub account).</li>
<li>No GitHub? Copy the request and send it on Telegram, <a href="https://t.me/roblosats" target=_blank rel=noopener>t.me/roblosats</a>.</li></ol></div>"""]
    if missing:
        parts.append('<div class="note warn">Not ready yet: %s.</div>' % "; ".join(missing))
    parts.append('<div class=card><form method=post action="/setup/federation"><input type=hidden name=csrf value="%s">%s'
                 '<p><button class="btn p"%s>Sign with my node</button></p></form></div>' % (CSRF, fields, " disabled" if missing else ""))
    if sig and on:
        body = ("Alias: %s\nOnion: %s\nNostr public key (hex): %s\nNode id: %s\nContact: %s\nMotto: %s\nDescription: %s\n\n"
                "Signed message: %s\nSignature: %s\n\nFee: %s · Orders: %s to %s sats\n") % (
            s.get("COORDINATOR_ALIAS", ""), on, nhex, ln.get("pubkey", ""), fed.get("contact", ""), fed.get("motto", ""),
            fed.get("description", ""), text, sig, s.get("FEE", ""), s.get("MIN_ORDER_SIZE", ""), s.get("MAX_ORDER_SIZE", ""))
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
        except Exception as e:
            return self.send(page("Error", '<div class="note bad">%s</div>' % esc(e)), 500)
        self.send(page("Not found", '<div class="note warn">Not found.</div>'), 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20000:
            return self.send(page("Error", '<div class="note bad">Too big.</div>'), 413)
        form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode(), keep_blank_values=True).items()}
        if not secrets.compare_digest(form.get("csrf", ""), CSRF):
            return self.send(page("Expired", '<div class="note warn">This page had expired: open it again.</div>'), 403)
        p = urllib.parse.urlparse(self.path).path.rstrip("/")
        if p == "/setup/settings":
            msg, cls = save_settings(form)
            return self.send(settings_page(msg, cls))
        if p == "/setup/federation":
            sig, msg, cls = sign_federation(form)
            return self.send(federation_page(sig, msg, cls))
        self.send(page("Not found", '<div class="note warn">Not found.</div>'), 404)


if __name__ == "__main__":
    os.makedirs(os.path.dirname(LOCAL), exist_ok=True)
    ThreadingHTTPServer(("127.0.0.1", 8090), Handler).serve_forever()
