#!/usr/bin/env bash
# Convenience wrapper around build_aab.sh — reads the keystore password
# from a local file instead of asking you to export four env vars by
# hand every build.
#
# Setup (one-time, after running init_keystore.sh):
#
#   1. Save your keystore password to a local file (NOT git-tracked):
#
#        echo 'your-password-here' > ~/keys/terre-vivante-release.passwd
#        chmod 600 ~/keys/terre-vivante-release.passwd
#
#      (Use single quotes if your password contains $, !, backslashes,
#      etc., to stop the shell from interpreting them.)
#
#   2. Run this script:
#
#        bash tools/android/release_aab.sh
#
# The password file is the only secret on your filesystem. To rotate
# the password (recommended after publishing the first release):
#
#   keytool -storepasswd -keystore ~/keys/terre-vivante-release.jks
#   keytool -keypasswd -alias terre-vivante \
#           -keystore ~/keys/terre-vivante-release.jks
#   (then update the .passwd file)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

KEYSTORE="${HOME}/keys/terre-vivante-release.jks"
PASSWD_FILE="${HOME}/keys/terre-vivante-release.passwd"
ALIAS="terre-vivante"

if [ ! -f "$KEYSTORE" ]; then
    echo "ERROR: keystore not found at $KEYSTORE" >&2
    echo "Run: bash tools/android/init_keystore.sh" >&2
    exit 1
fi

if [ ! -f "$PASSWD_FILE" ]; then
    cat <<EOF >&2
ERROR: password file not found at $PASSWD_FILE

Create it once (replace <password> with the keystore password you set
during init_keystore.sh):

    echo '<password>' > $PASSWD_FILE
    chmod 600 $PASSWD_FILE

EOF
    exit 1
fi

if [ "$(stat -c '%a' "$PASSWD_FILE")" != "600" ]; then
    echo "WARNING: $PASSWD_FILE is not mode 600. Fixing now."
    chmod 600 "$PASSWD_FILE"
fi

PASSWORD=$(cat "$PASSWD_FILE")
# Trim trailing newline if any (echo "..." adds one).
PASSWORD=$(printf '%s' "$PASSWORD" | tr -d '\r\n')

if [ -z "$PASSWORD" ]; then
    echo "ERROR: $PASSWD_FILE is empty" >&2
    exit 1
fi

# Activate the buildozer venv if it exists and we're not in one.
if ! command -v buildozer >/dev/null 2>&1; then
    if [ -f "${HOME}/buildozer-venv/bin/activate" ]; then
        # shellcheck disable=SC1091
        source "${HOME}/buildozer-venv/bin/activate"
    else
        echo "ERROR: buildozer not on PATH and no venv at ~/buildozer-venv" >&2
        exit 1
    fi
fi

export P4A_RELEASE_KEYSTORE="$KEYSTORE"
export P4A_RELEASE_KEYSTORE_PASSWD="$PASSWORD"
export P4A_RELEASE_KEYALIAS="$ALIAS"
export P4A_RELEASE_KEYALIAS_PASSWD="$PASSWORD"

# Hand off to the existing release-build script.
cd "$REPO_ROOT"
exec bash tools/android/build_aab.sh
