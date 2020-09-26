#!/bin/bash
PORT="/dev/ttyUSB0"
WEB="$(realpath '../qrpr.eu/')"
SUMS="/tmp/$$_sums.txt"
SUMS_LAST="/tmp/$$_sums_last.txt"

echo "Pushing new software"
ampy --port "$PORT" put 'main.py'  || exit 4

echo -n "Getting last content hashes"
ampy --port "$PORT" get "web.hashes.txt" "$SUMS_LAST" &>/dev/null || {
  echo -n ".. no found"
  touch "$SUMS_LAST"
}
echo ""
SUMS_LAST="$(cat "$SUMS_LAST")"

cd "$WEB" || { echo "FATAL: Web directory does not exist">&2; exit 1; }

# Do only incremental updates
# echo "Removing previous files"
# ampy --port "$PORT" rmdir web || exit 4

declare -A createdDirs
echo "Patching files"
while read -r f; do
        tf="web/$f"  # target file
        td="$(dirname "$tf")"  # target directory
        [[ -z "${createdDirs[$td]}" ]] && {
          echo "- $td"
          ampy --port "$PORT" mkdir "$td" &>/dev/null
        }
        createdDirs["$td"]=1
        sum="$(md5sum "$f")"
        echo "$sum" >> "$SUMS"
        echo "$SUMS_LAST" | grep -Fs "$sum" &>/dev/null || {
          echo "  $f -> $tf"
          ampy --port "$PORT" put "$f" "$tf" || exit 4
        }
done <<< "$(git ls-files)"

echo "Sending new content hashes"
ampy --port "$PORT" put "$SUMS" "web.hashes.txt"

echo "Cleaning"
rm "$SUMS"

echo "Rebooting"
ampy --port "$PORT" reset || exit 4

echo "All set!"