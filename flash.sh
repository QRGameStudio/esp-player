#!/bin/bash
PORT="/dev/ttyUSB0"
WEB="$(realpath '../qrpr.eu/')"

echo "Pushing new software"
ampy --port "$PORT" put 'main.py'  || exit 4

cd "$WEB" || { echo "FATAL: Web directory does not exist">&2; exit 1; }

echo "Removing previous files"
ampy --port "$PORT" rmdir web || exit 4

declare -A createdDirs
echo "Patching files"
while read -r f; do
        tf="web/$f"  # target file
        td="$(dirname "$tf")"  # target directory
        [[ -z "${createdDirs[$td]}" ]] && {
          echo "-mkdir $td"
          ampy --port "$PORT" mkdir "$td" || exit 4
        }
        createdDirs["$td"]=1
        echo "  $f -> $tf"
        ampy --port "$PORT" put "$f" "$tf" || exit 4
done <<< "$(git ls-files)"

echo "Rebooting"
ampy --port "$PORT" reset || exit 4

echo "All set!"