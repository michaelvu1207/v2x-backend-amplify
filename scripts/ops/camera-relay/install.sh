#!/bin/sh
set -eu

MEDIAMTX_VERSION="1.20.1"
MEDIAMTX_SHA256="81b143f55a5d23d4a8c028d52869c14ea4a59919900528698fcc97a747fd69c6"
MEDIAMTX_ARCHIVE="mediamtx_v${MEDIAMTX_VERSION}_linux_amd64.tar.gz"
MEDIAMTX_URL="https://github.com/bluenviron/mediamtx/releases/download/v${MEDIAMTX_VERSION}/${MEDIAMTX_ARCHIVE}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SYSTEMD_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/../../systemd" && pwd)

if [ "$(id -u)" -ne 0 ]; then
  echo "install.sh must run as root" >&2
  exit 1
fi

if ! getent passwd v2x-camera >/dev/null; then
  useradd --system --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin v2x-camera
fi

install -d -o root -g v2x-camera -m 0750 /etc/v2x-camera /opt/v2x-camera
if ! mountpoint -q /mnt/archive; then
  echo "/mnt/archive must be mounted before installing the camera relay" >&2
  exit 1
fi
install -d -o v2x-camera -g v2x-camera -m 0750 /var/lib/v2x-camera /mnt/archive/v2x-camera/recordings

installed_version=""
if [ -x /usr/local/bin/mediamtx ]; then
  installed_version=$(/usr/local/bin/mediamtx --version 2>/dev/null | sed -n 's/^v//p')
fi
if [ "$installed_version" != "$MEDIAMTX_VERSION" ]; then
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' EXIT HUP INT TERM
  curl -fsSL "$MEDIAMTX_URL" -o "$tmpdir/$MEDIAMTX_ARCHIVE"
  printf '%s  %s\n' "$MEDIAMTX_SHA256" "$tmpdir/$MEDIAMTX_ARCHIVE" | sha256sum -c -
  tar -xzf "$tmpdir/$MEDIAMTX_ARCHIVE" -C "$tmpdir" mediamtx
  install -o root -g root -m 0755 "$tmpdir/mediamtx" /usr/local/bin/mediamtx
  rm -rf "$tmpdir"
  trap - EXIT HUP INT TERM
fi

install -o root -g v2x-camera -m 0640 "$SCRIPT_DIR/mediamtx.yml" /etc/v2x-camera/mediamtx.yml
install -o root -g root -m 0755 "$SCRIPT_DIR/demux_to_rtsp.py" /opt/v2x-camera/demux_to_rtsp.py
install -o root -g root -m 0755 "$SCRIPT_DIR/archive-guard.sh" /opt/v2x-camera/archive-guard.sh
install -o root -g root -m 0644 "$SCRIPT_DIR/mediamtx.service" /etc/systemd/system/mediamtx.service
install -o root -g root -m 0644 "$SCRIPT_DIR/v2x-camera-relay@.service" /etc/systemd/system/v2x-camera-relay@.service
install -o root -g root -m 0644 "$SYSTEMD_DIR/v2x-archive-guard.service" /etc/systemd/system/v2x-archive-guard.service
install -o root -g root -m 0644 "$SYSTEMD_DIR/v2x-archive-guard.timer" /etc/systemd/system/v2x-archive-guard.timer

systemctl daemon-reload
systemctl enable --now mediamtx.service \
  v2x-camera-relay@0.service v2x-camera-relay@1.service \
  v2x-camera-relay@2.service v2x-camera-relay@3.service \
  v2x-archive-guard.timer
