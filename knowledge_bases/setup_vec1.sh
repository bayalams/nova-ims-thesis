#!/usr/bin/env bash
set -euo pipefail

# This script installs the local SQLite Vec1 extension used by the KB builder.
# It writes only to .local_tools/, which is ignored by git.

TOOLS_DIR=".local_tools/vec1"
VEC1_URL="https://sqlite.org/vec1/raw/vec1.c?ci=d07018452330b0a3904a6552818febc51ce0a73ac657e578b38e893c72a49681"
VEC1_SHA256="b20b6394f50fdaab2ca7fc112f47f39a1b52488087021cd86f7bf3d9b9b209c8"
SOURCE_PATH="${TOOLS_DIR}/vec1.c"
MANIFEST_PATH="${TOOLS_DIR}/manifest.json"

echo "[INFO] Setting up SQLite Vec1"
echo "[INFO] Output folder: ${TOOLS_DIR}"

mkdir -p "${TOOLS_DIR}"

echo "[1/4] Downloading pinned Vec1 source"
curl -sS -L "${VEC1_URL}" -o "${SOURCE_PATH}"

echo "[2/4] Verifying Vec1 checksum"
DOWNLOADED_SHA256="$(LC_ALL=C shasum -a 256 "${SOURCE_PATH}" | awk '{print $1}')"

if [[ "${DOWNLOADED_SHA256}" != "${VEC1_SHA256}" ]]; then
  echo "[ERROR] Vec1 checksum mismatch"
  echo "[ERROR] Expected: ${VEC1_SHA256}"
  echo "[ERROR] Actual:   ${DOWNLOADED_SHA256}"
  exit 1
fi

UNAME_SYSTEM="$(uname -s)"
UNAME_MACHINE="$(uname -m)"
OUTPUT_PATH="${TOOLS_DIR}/vec1.so"
COMPILE_COMMAND=""

echo "[3/4] Compiling Vec1 for ${UNAME_SYSTEM} ${UNAME_MACHINE}"

if [[ "${UNAME_SYSTEM}" == "Darwin" ]]; then
  OUTPUT_PATH="${TOOLS_DIR}/vec1.dylib"
  SQLITE_PREFIX=""

  if [[ -d "/usr/local/opt/sqlite" ]]; then
    SQLITE_PREFIX="/usr/local/opt/sqlite"
  elif [[ -d "/opt/homebrew/opt/sqlite" ]]; then
    SQLITE_PREFIX="/opt/homebrew/opt/sqlite"
  fi

  if [[ -n "${SQLITE_PREFIX}" ]]; then
    echo "[INFO] Using SQLite from: ${SQLITE_PREFIX}"
    COMPILE_COMMAND="cc -O3 -DNDEBUG -fPIC -dynamiclib ${SOURCE_PATH} -I${SQLITE_PREFIX}/include -L${SQLITE_PREFIX}/lib -lsqlite3 -o ${OUTPUT_PATH}"
  else
    echo "[WARNING] Homebrew SQLite was not found; falling back to system SQLite"
    COMPILE_COMMAND="cc -O3 -DNDEBUG -fPIC -dynamiclib ${SOURCE_PATH} -lsqlite3 -o ${OUTPUT_PATH}"
  fi
elif [[ "${UNAME_SYSTEM}" == "Linux" ]]; then
  OUTPUT_PATH="${TOOLS_DIR}/vec1.so"
  COMPILE_COMMAND="cc -O3 -DNDEBUG -fPIC -shared ${SOURCE_PATH} -o ${OUTPUT_PATH}"
else
  echo "[ERROR] Unsupported operating system for automatic Vec1 setup: ${UNAME_SYSTEM}"
  exit 1
fi

echo "[INFO] Compile command: ${COMPILE_COMMAND}"
${COMPILE_COMMAND}

echo "[4/4] Writing setup manifest"
cat > "${MANIFEST_PATH}" <<EOF
{
  "source_url": "${VEC1_URL}",
  "source_sha256": "${VEC1_SHA256}",
  "downloaded_sha256": "${DOWNLOADED_SHA256}",
  "system": "${UNAME_SYSTEM}",
  "machine": "${UNAME_MACHINE}",
  "compile_command": "${COMPILE_COMMAND}",
  "output_path": "${OUTPUT_PATH}"
}
EOF

echo "[INFO] Vec1 setup complete"
echo "[INFO] Extension path: ${OUTPUT_PATH}"
