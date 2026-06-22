#!/bin/bash
# Inspect ELF page alignment of every .so in the APK.
# Run from inside WSL after build_apk.sh: bash tools/android/check_apk_alignment.sh
set -e
APK=$(ls -t /root/builds/gaia_ultimatum/bin/*.apk 2>/dev/null | head -1)
if [ -z "$APK" ]; then
    echo "No APK found at /root/builds/gaia_ultimatum/bin/" >&2
    exit 1
fi
echo "Inspecting: $APK"
WORK=/tmp/apk_check
rm -rf "$WORK"
mkdir -p "$WORK"
cd "$WORK"
unzip -q "$APK" "lib/*"
for f in $(find lib -name "*.so" | sort); do
    align=$(readelf -lW "$f" 2>/dev/null | awk '/LOAD/ { print $NF; exit }')
    echo "$align  $f"
done
