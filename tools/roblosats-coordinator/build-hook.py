#!/usr/bin/env python3
# Builds kilombino-roblosats-coordinator/hooks/pre-start from pre-start.in and the app's own files
# here. On an update Umbrel brings the app's docker-compose.yml, umbrel-app.yml and hooks/, but not
# the other files beside them (and never overwrites what is already in data/), so the hook carries
# the files and writes them to app/ in the app's directory on every start.
# Run it after changing any file here, and commit both.
import base64
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "kilombino-roblosats-coordinator", "hooks", "pre-start")
FILES = [("run.sh", "755"), ("panel.py", "644"), ("nginx.conf", "644"), ("torrc", "644"),
         ("strfry.conf", "644"), ("federation_urls.txt", "644")]

parts = [open(os.path.join(HERE, "pre-start.in")).read().rstrip("\n"), """
# The app's own files, fresh on every start (see tools/roblosats-coordinator in the store's repo).
umask 022
A="${APP_DATA_DIR}/app"
mkdir -p "${A}"
put() {
  base64 -d > "${A}/$1.tmp"
  chmod "$2" "${A}/$1.tmp"
  mv -f "${A}/$1.tmp" "${A}/$1"
}"""]
names = []
for name, mode in FILES:
    names.append(name)
    b64 = base64.encodebytes(open(os.path.join(HERE, name), "rb").read()).decode()
    parts.append("put %s %s <<'B64'\n%sB64" % (name, mode, b64))
parts.append("""# rl15-3 to rl15-4 mounted these from the app's directory, where an update never put them, so
# docker made empty directories in their place: remove those.
for f in %s; do
  [ -d "${APP_DATA_DIR}/${f}" ] && rmdir "${APP_DATA_DIR}/${f}" 2>/dev/null || true
done
""" % " ".join(names))
with open(OUT, "w") as f:
    f.write("\n".join(parts))
os.chmod(OUT, 0o755)
print("wrote", os.path.relpath(OUT), os.path.getsize(OUT), "bytes")
