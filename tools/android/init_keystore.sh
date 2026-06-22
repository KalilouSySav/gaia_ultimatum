#!/usr/bin/env bash
# One-time interactive keystore generator for Terre Vivante release signing.
#
# Why a wrapper instead of running ``keytool`` directly:
#
#   * Defaults are pre-filled (path, alias, validity, key algorithm)
#     so the only things you have to think about are name + password.
#   * Refuses to overwrite an existing keystore — losing the existing
#     one would permanently break the Play Store update path for any
#     APK/AAB previously published with it.
#   * Reminds you at the end to back up the .jks file AND record the
#     password somewhere durable.
#
# This script is purely interactive — passwords are typed into keytool's
# own prompt and never appear in shell history, env vars, or files.
#
# Usage (WSL Ubuntu-22.04):
#
#   bash tools/android/init_keystore.sh
#
# Output: ~/keys/terre-vivante-release.jks

set -euo pipefail

KEYSTORE="${HOME}/keys/terre-vivante-release.jks"
ALIAS="terre-vivante"
VALIDITY_DAYS=10000  # ~27 years, well past Play Store key-rotation policies

if [ -f "$KEYSTORE" ]; then
    echo "ERROR: keystore already exists at $KEYSTORE"
    echo ""
    echo "Refusing to overwrite — that would permanently break the"
    echo "Play Store update path for any version of the app already"
    echo "published with the current keystore."
    echo ""
    echo "If you genuinely want to start over from scratch and you have"
    echo "NEVER published this app on Play Store with the current key,"
    echo "delete the file manually first:"
    echo ""
    echo "  rm '$KEYSTORE'"
    echo ""
    exit 1
fi

mkdir -p "$(dirname "$KEYSTORE")"

cat <<'EOF'
==============================================================================
Generating Terre Vivante release keystore.

You will be prompted by keytool to enter:

  1. Keystore password (then confirm)
       - Use 16+ characters. Save it to your password manager NOW.
       - This password is required for EVERY app update, forever.
       - Lose it → permanently locked out of updating this app.

  2. First and last name (e.g. Kalilou Sy Savane)
  3. Organizational unit (e.g. Indie — or just press ENTER)
  4. Organization (e.g. Kalilou Sy Savane)
  5. City / State / Country code (e.g. Paris / Île-de-France / FR)
  6. Confirm "yes"
  7. Key password — press ENTER to reuse the keystore password
     (recommended; build scripts assume keystore-pw == key-pw)

==============================================================================
EOF
echo ""
read -rp "Press ENTER to start, or Ctrl-C to abort. > "

keytool -genkey -v \
    -keystore "$KEYSTORE" \
    -alias "$ALIAS" \
    -keyalg RSA \
    -keysize 2048 \
    -validity "$VALIDITY_DAYS"

chmod 600 "$KEYSTORE"

cat <<EOF

==============================================================================
DONE. Keystore written to: $KEYSTORE  (mode 600)
==============================================================================

CRITICAL NEXT STEPS (do these BEFORE you publish):

  1. Save the keystore password to your password manager.
     Without it you cannot update the app on Play Store, ever.

  2. Back up the keystore file to TWO independent places, e.g.:

       cp $KEYSTORE ~/Dropbox/keys/
       cp $KEYSTORE /mnt/c/Users/sysav/OneDrive/keys/

     Even after Play App Signing is set up, you need this file to
     upload new releases.

  3. To build the release AAB:

       export P4A_RELEASE_KEYSTORE="$KEYSTORE"
       export P4A_RELEASE_KEYSTORE_PASSWD='<your password>'
       export P4A_RELEASE_KEYALIAS="$ALIAS"
       export P4A_RELEASE_KEYALIAS_PASSWD='<same password>'
       source ~/buildozer-venv/bin/activate
       cd "/mnt/c/Users/sysav/OneDrive/Desktop/projet logciel/gaia_ultimatum"
       bash tools/android/build_aab.sh

==============================================================================
EOF
