FROM python:3.12-slim

# Listing 0.1.4. python:3.12-slim is multi-arch. A Raspberry Pi pulls the arm64 image.
# crcmod 1.7 ships source only, so this build compiles it, then removes the compiler.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/routehash

RUN apt-get update \
  && apt-get install -y --no-install-recommends gcc libc6-dev \
  && pip install --no-cache-dir \
    'coincurve==21.0.0' \
    'bip-utils==2.12.2' \
    'websocket-client==1.9.2' \
    'cryptography==50.0.1' \
  && apt-get purge -y gcc libc6-dev \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/routehash
COPY runtime/ /opt/routehash/

USER 1000:1000

CMD ["python3", "/opt/routehash/pool_balance_loop.py", "--data", "/data", "--ui", "7156"]
