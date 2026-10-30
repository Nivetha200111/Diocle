#!/bin/sh
# Fetch the pinned SQLite JDBC driver (org.xerial sqlite-jdbc, Apache-2.0) into services/verifier/lib/ (gitignored),
# where diocle_verifier.sqlrun and the EXEC SQL tests look for it. Same version and SHA-256 as deploy/Dockerfile.api;
# keep the two in step. Fails closed: a wrong checksum deletes the download and exits non-zero. Idempotent.
set -eu
VERSION=3.46.1.3
SHA256=4a4832720a65eaf7f4d6fd7ede52087b994dc5633c076f9e994dc0c8b4b0b4fa
here=$(cd "$(dirname "$0")" && pwd)
dest="$here/../services/verifier/lib"
jar="$dest/sqlite-jdbc.jar"

sum() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }

if [ -f "$jar" ] && [ "$(sum "$jar")" = "$SHA256" ]; then
  echo "sqlite-jdbc $VERSION already present: $jar"
  exit 0
fi
mkdir -p "$dest"
tmp="$jar.part"
curl -sSfL -o "$tmp" "https://repo1.maven.org/maven2/org/xerial/sqlite-jdbc/$VERSION/sqlite-jdbc-$VERSION.jar"
got=$(sum "$tmp")
if [ "$got" != "$SHA256" ]; then
  rm -f "$tmp"
  echo "sqlite-jdbc checksum mismatch: got $got, want $SHA256" >&2
  exit 1
fi
mv "$tmp" "$jar"
echo "sqlite-jdbc $VERSION installed: $jar"
