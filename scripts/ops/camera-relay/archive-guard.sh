#!/bin/sh
set -eu

ARCHIVE_MOUNT=/mnt/archive
RECORDINGS_ROOT=$ARCHIVE_MOUNT/v2x-camera/recordings
LOW_WATER_BYTES=$((60 * 1024 * 1024 * 1024))
HIGH_WATER_BYTES=$((80 * 1024 * 1024 * 1024))

available_bytes() {
  df -B1 --output=avail "$ARCHIVE_MOUNT" | sed -n '$p' | tr -d ' '
}

if ! mountpoint -q "$ARCHIVE_MOUNT"; then
  logger -t v2x-archive-guard "archive volume is not mounted; refusing cleanup"
  exit 1
fi

if [ ! -d "$RECORDINGS_ROOT" ]; then
  logger -t v2x-archive-guard "recordings directory is missing; refusing cleanup"
  exit 1
fi

available=$(available_bytes)
if [ "$available" -ge "$LOW_WATER_BYTES" ]; then
  logger -t v2x-archive-guard "free space $((available / 1024 / 1024 / 1024)) GiB; no cleanup needed"
  exit 0
fi

candidates=$(mktemp)
trap 'rm -f "$candidates"' EXIT HUP INT TERM
find "$RECORDINGS_ROOT" -type f -name '*.mp4' -printf '%f\t%p\n' | sort >"$candidates"
deleted=0
while IFS="	" read -r name path; do
  available=$(available_bytes)
  [ "$available" -lt "$HIGH_WATER_BYTES" ] || break
  case "$path" in
    "$RECORDINGS_ROOT"/*) ;;
    *)
      logger -t v2x-archive-guard "refusing path outside recordings root: $path"
      exit 1
      ;;
  esac
  if [ -f "$path" ] && [ ! -L "$path" ]; then
    rm -f -- "$path"
    deleted=$((deleted + 1))
    logger -t v2x-archive-guard "deleted oldest segment: $path"
  fi
done <"$candidates"

available=$(available_bytes)
logger -t v2x-archive-guard "cleanup complete: deleted $deleted segment(s), free space $((available / 1024 / 1024 / 1024)) GiB"
[ "$available" -ge "$HIGH_WATER_BYTES" ]
