#!/bin/sh
# Build the effects library's helper programs on this Mac (setup runs this; core.py also runs it the first time a
# helper is missing). They're built from the Swift sources in this folder with Apple's compiler, so nothing is
# downloaded and no compiled program is kept in git.
#
#   sh effects/build_helpers.sh          build what's missing
#   sh effects/build_helpers.sh --force  build again
#
# Needs the Xcode command line tools (`xcode-select --install`) and macOS 14 or later (Apple Vision person masks).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HERE/cache/bin"
mkdir -p "$BIN"
if ! command -v swiftc >/dev/null 2>&1; then
  echo "swiftc isn't installed. Run: xcode-select --install   then run this again." >&2
  exit 1
fi
build() {   # build <source.swift> <program name>
  if [ "$FORCE" = 1 ] || [ ! -x "$BIN/$2" ] || [ "$HERE/$1" -nt "$BIN/$2" ]; then
    echo "building $2 from $1 ..."
    swiftc -O "$HERE/$1" -o "$BIN/$2.part"
    mv "$BIN/$2.part" "$BIN/$2"
  fi
  echo "ok: effects/cache/bin/$2"
}
FORCE=0
[ "$1" = "--force" ] && FORCE=1
build track.swift track
