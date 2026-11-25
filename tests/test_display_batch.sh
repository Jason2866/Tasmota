#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_file="$root/tasmota/tasmota_xdrv_driver/xdrv_13_display.ino"
temp_dir=$(mktemp -d)
trap 'rm -rf "$temp_dir"' EXIT
sed -n '/^struct MULTI_DISP {/,/^#endif \/\/ USE_MULTI_DISPLAY/p' "$source_file" | sed '$d' > "$temp_dir/display_batch_under_test.inc"
awk '/^struct DisplayTextState \{/ { printing = 1 } printing { print } /^uint8_t Display_Text_From_File\(/ { batch = 1 } batch && /^#endif \/\/ USE_UFILESYS/ { exit }' "$source_file" | sed 's/(uint32_t)dp - (uint32_t)linebuf/dp - linebuf/g' >> "$temp_dir/display_batch_under_test.inc"
printf '#ifdef USE_UFILESYS\n' >> "$temp_dir/display_batch_under_test.inc"
awk '/^void CmndDisplayBatch\(/ { printing = 1 } printing && /^\/\*\*\*\*/ { exit } printing { print }' "$source_file" >> "$temp_dir/display_batch_under_test.inc"
${CXX:-c++} ${CXXFLAGS:-} -std=c++17 -fpermissive -I"$temp_dir" "$root/tests/test_display_batch.cpp" -o "$temp_dir/test_display_batch"
"$temp_dir/test_display_batch"
awk '/^static bool DisplayTextPreflight\(/ { printing = 1 } printing { print } printing && /^}/ { exit }' "$source_file" > "$temp_dir/display_preflight_under_test.inc"
${CXX:-c++} ${CXXFLAGS:-} -std=c++17 -I"$temp_dir" "$root/tests/test_display_preflight.cpp" -o "$temp_dir/test_display_preflight"
"$temp_dir/test_display_preflight"
