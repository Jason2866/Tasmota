#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
temp_dir=$(mktemp -d)
trap 'rm -rf "$temp_dir"' EXIT
awk '/^void uDisplay::DisplayInit\(/ { printing = 1 } printing { print } printing && /^}/ { exit }' "$root/lib/lib_display/UDisplay/src/uDisplay.cpp" > "$temp_dir/udisp_under_test.inc"
awk '/^void uDisplay::Splash\(/ { printing = 1 } printing { print } printing && /^}/ { exit }' "$root/lib/lib_display/UDisplay/src/uDisplay_control.cpp" >> "$temp_dir/udisp_under_test.inc"
awk '/^void uDisplay::pushColors\(/ { printing = 1 } /^bool uDisplay::setAddrWindowChecked\(/ { exit } printing { print }' "$root/lib/lib_display/UDisplay/src/uDisplay_graphics.cpp" >> "$temp_dir/udisp_under_test.inc"
${CXX:-c++} ${CXXFLAGS:-} -std=c++17 -I"$temp_dir" "$root/tests/test_udisp_splash_transfer.cpp" -o "$temp_dir/test_udisp_splash_transfer"
"$temp_dir/test_udisp_splash_transfer"
