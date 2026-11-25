#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
temp_dir=$(mktemp -d)
trap 'rm -rf "$temp_dir"' EXIT
test_file="$temp_dir/comic_install.be"
cat > "$test_file" <<'BERRY'
var comic_source_path = "source"
var comic_download_path = "download"
var comic_backup_path = "backup"

class TestPath
  var files, fail_remove, fail_rename_from, fail_rename_to
  def init()
    self.files = {}
    self.fail_remove = nil
    self.fail_rename_from = nil
    self.fail_rename_to = nil
  end
  def exists(name)
    return self.files.find(name) != nil
  end
  def remove(name)
    if name == self.fail_remove return false end
    self.files.remove(name)
    return true
  end
  def rename(source, dest)
    if source == self.fail_rename_from && dest == self.fail_rename_to return false end
    if !self.exists(source) || self.exists(dest) return false end
    self.files[dest] = self.files[source]
    self.files.remove(source)
    return true
  end
end
var path = TestPath()
BERRY
awk '/^def install_downloaded_cover\(\)/ { printing = 1 } printing { print } printing && /^end$/ { exit }' "$root/tasmota/berry/inky/comic_display.be" >> "$test_file"
cat >> "$test_file" <<'BERRY'
path.files = {"source":"uncommitted", "backup":"committed", "download":"new"}
install_downloaded_cover()
assert(path.files.find("source") == "new")
assert(path.files.find("backup") == "committed")

path.files = {"source":"uncommitted", "backup":"committed", "download":"new"}
path.fail_remove = "source"
try
  install_downloaded_cover()
  assert(false)
except "io_error"
end
assert(path.files.find("source") == "uncommitted")
assert(path.files.find("backup") == "committed")
assert(path.files.find("download") == "new")
path.fail_remove = nil

path.fail_rename_from = "backup"
path.fail_rename_to = "source"
try
  install_downloaded_cover()
  assert(false)
except "io_error"
end
assert(path.files.find("source") == nil)
assert(path.files.find("backup") == "committed")
assert(path.files.find("download") == "new")
path.fail_rename_from = nil
path.fail_rename_to = nil

install_downloaded_cover()
assert(path.files.find("source") == "new")
assert(path.files.find("backup") == "committed")

path.files = {"source":"committed", "download":"new"}
path.fail_rename_from = "download"
path.fail_rename_to = "source"
try
  install_downloaded_cover()
  assert(false)
except "io_error"
end
assert(path.files.find("source") == "committed")
assert(path.files.find("backup") == nil)
assert(path.files.find("download") == "new")

path.fail_rename_from = nil
path.fail_rename_to = nil
path.files = {"download":"new"}
install_downloaded_cover()
assert(path.files.find("source") == "new")
assert(path.files.find("backup") == nil)
BERRY
"${BERRY_EXEC:-$root/lib/libesp32/berry/berry}" "$test_file"
