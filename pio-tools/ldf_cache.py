# ldf_cache.py
"""
PlatformIO Advanced Script for intelligent LDF caching using idedata.json.
All LDF-cached build options (except lib_ldf_mode) are written to ldf_cache.ini,
which must be included in platformio.ini via 'extra_configs = ldf_cache.ini'.
Framework and toolchain files are excluded from the project hash.

Copyright: Jason2866
"""

Import("env")
import os
import hashlib
import time
import datetime
import re
import pprint
import json
from platformio.project.config import ProjectConfig

def ensure_idedata_dependency():
    """
    Ensure that the idedata target is always built together with the main firmware build.
    """
    progpath = env.get("PROGPATH")
    if progpath:
        env.Depends(progpath, env.Alias("idedata"))
        print("🔧 [LDF-Cache] idedata target is now a dependency of the firmware build.")

ensure_idedata_dependency()

class LDFCacheOptimizer:
    """
    PlatformIO LDF (Library Dependency Finder) cache optimizer.

    Reads LDF results from idedata.json, writes all build options to ldf_cache.ini,
    and stores the cache as a Python dict for robust validation.
    Framework and toolchain files are excluded from the project hash.
    """

    HEADER_EXTENSIONS = frozenset(['.h', '.hpp', '.hxx', '.h++', '.hh', '.inc', '.tpp', '.tcc'])
    SOURCE_EXTENSIONS = frozenset(['.c', '.cpp', '.cxx', '.c++', '.cc', '.ino'])
    CONFIG_EXTENSIONS = frozenset(['.json', '.properties', '.txt', '.ini'])

    IGNORE_DIRS = frozenset([
        '.git', '.github', '.cache', '.vscode', '.pio', 'boards',
        'data', 'build', 'pio-tools', 'tools', '__pycache__', 'variants', 
        'berry', 'berry_tasmota', 'berry_matter', 'berry_custom',
        'berry_animate', 'berry_mapping', 'berry_int64', 'displaydesc',
        'html_compressed', 'html_uncompressed', 'language', 'energy_modbus_configs'
    ])

    def __init__(self, environment):
        """
        Initialize the LDF Cache Optimizer.

        Args:
            environment: PlatformIO SCons environment object
        """
        self.env = environment
        self.project_dir = self.env.subst("$PROJECT_DIR")
        self.src_dir = self.env.subst("$PROJECT_SRC_DIR")
        self.cache_file = os.path.join(self.project_dir, ".pio", "ldf_cache", f"ldf_cache_{self.env['PIOENV']}.py")
        self.ldf_cache_ini = os.path.join(self.project_dir, "ldf_cache.ini")
        self.platformio_ini = os.path.join(self.project_dir, "platformio.ini")
        self.idedata_file = os.path.join(self.project_dir, ".pio", "build", self.env['PIOENV'], "idedata.json")
        self.original_ldf_mode = None
        self.ALL_RELEVANT_EXTENSIONS = self.HEADER_EXTENSIONS | self.SOURCE_EXTENSIONS | self.CONFIG_EXTENSIONS

    def is_framework_or_toolchain_path(self, path):
        """
        Check if the path belongs to PlatformIO framework or toolchain packages.

        Args:
            path (str): Path to check

        Returns:
            bool: True if path is part of framework or toolchain
        """
        pio_dir = os.path.expanduser("~/.platformio/packages")
        norm_path = os.path.normpath(path)
        if norm_path.startswith(pio_dir):
            rest = norm_path[len(pio_dir):].lstrip(os.sep)
            if rest.startswith("framework-") or rest.startswith("toolchain-"):
                return True
        return False

    def is_platformio_path(self, path):
        """
        Check if path belongs to PlatformIO installation (including .pio, .platformio, etc).

        Args:
            path (str): Path to check

        Returns:
            bool: True if path is part of PlatformIO installation
        """
        platformio_paths = set()
        if 'PLATFORMIO_CORE_DIR' in os.environ:
            platformio_paths.add(os.path.normpath(os.environ['PLATFORMIO_CORE_DIR']))
        pio_home = os.path.join(ProjectConfig.get_instance().get("platformio", "platforms_dir"))
        platformio_paths.add(os.path.normpath(pio_home))
        platformio_paths.add(os.path.normpath(os.path.join(self.project_dir, ".pio")))
        norm_path = os.path.normpath(path)
        return any(norm_path.startswith(pio_path) for pio_path in platformio_paths)

    def _get_file_hash(self, file_path):
        """
        Generate SHA256 hash of a file.

        Args:
            file_path (str): Path to the file to hash

        Returns:
            str: SHA256 hash of the file content (first 16 characters) or "unreadable" if error
        """
        try:
            with open(file_path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()[:16]
        except (IOError, OSError, PermissionError):
            return "unreadable"

    def get_include_relevant_hash(self, file_path):
        """
        Generate hash only from include-relevant lines in source files.

        Args:
            file_path (str): Path to the source file

        Returns:
            str: SHA256 hash of include-relevant content (first 16 characters)
        """
        include_lines = []
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith('//'):
                        continue
                    if (stripped.startswith('#include') or 
                        (stripped.startswith('#define') and 
                         any(keyword in stripped.upper() for keyword in ['INCLUDE', 'PATH', 'CONFIG']))):
                        include_lines.append(stripped)
            content = '\n'.join(include_lines)
            return hashlib.sha256(content.encode()).hexdigest()[:16]
        except (IOError, OSError, PermissionError, UnicodeDecodeError):
            return self._get_file_hash(file_path)

    def get_project_hash_with_details(self):
        """
        Generate hash with detailed file tracking and optimized early filtering.
        Excludes all PlatformIO-installed components, framework, toolchain, and lib_ldf_mode settings.

        Returns:
            dict: Contains final_hash, file_hashes dict, total_files count, and timing info
        """
        start_time = time.time()
        file_hashes = {}
        hash_data = []
        generated_cpp = os.path.basename(self.project_dir).lower() + ".ino.cpp"
        if os.path.exists(self.platformio_ini):
            try:
                with open(self.platformio_ini, 'r', encoding='utf-8') as f:
                    ini_content = f.read()
                filtered_content = re.sub(r'lib_ldf_mode\s*=\s*\w+\n?', '', ini_content)
                ini_hash = hashlib.sha256(filtered_content.encode()).hexdigest()[:16]
                hash_data.append(ini_hash)
                file_hashes['platformio.ini'] = ini_hash
            except Exception as e:
                print(f"⚠ Error reading platformio.ini: {e}")
        scan_dirs = []
        if os.path.exists(self.src_dir):
            scan_dirs.append(('source', self.src_dir))
        lib_dir = os.path.join(self.project_dir, "lib")
        if os.path.exists(lib_dir) and not self.is_platformio_path(lib_dir):
            scan_dirs.append(('library', lib_dir))
        for inc_path in self.env.get('CPPPATH', []):
            inc_dir = str(inc_path)
            # Exclude framework/toolchain and PlatformIO paths
            if self.is_framework_or_toolchain_path(inc_dir) or self.is_platformio_path(inc_dir):
                continue
            if any(skip_dir in inc_dir for skip_dir in ['variants', '.platformio', '.pio']):
                continue
            if os.path.exists(inc_dir) and inc_dir != self.src_dir:
                scan_dirs.append(('include', inc_dir))
        total_scanned = 0
        total_relevant = 0
        scan_start_time = time.time()
        for dir_type, scan_dir in scan_dirs:
            print(f"🔍 Scanning {dir_type} directory: {scan_dir}")
            try:
                for root, dirs, files in os.walk(scan_dir):
                    if self.is_platformio_path(root) or self.is_framework_or_toolchain_path(root):
                        continue
                    dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]
                    relevant_files = []
                    for file in files:
                        total_scanned += 1
                        file_ext = os.path.splitext(file)[1].lower()
                        if file_ext in self.ALL_RELEVANT_EXTENSIONS:
                            relevant_files.append((file, file_ext))
                            total_relevant += 1
                    for file, file_ext in relevant_files:
                        if file == generated_cpp:
                            continue
                        file_path = os.path.join(root, file)
                        if file_ext in self.HEADER_EXTENSIONS or file_ext in self.CONFIG_EXTENSIONS:
                            file_hash = self._get_file_hash(file_path)
                        elif file_ext in self.SOURCE_EXTENSIONS:
                            file_hash = self.get_include_relevant_hash(file_path)
                        else:
                            continue
                        file_hashes[file_path] = file_hash
                        hash_data.append(file_hash)
            except (IOError, OSError, PermissionError) as e:
                print(f"⚠ Warning: Could not scan directory {scan_dir}: {e}")
                continue
        scan_elapsed = time.time() - scan_start_time
        final_hash = hashlib.sha256(''.join(hash_data).encode()).hexdigest()[:16]
        total_elapsed = time.time() - start_time
        print(f"🔍 Scanning completed in {scan_elapsed:.2f}s")
        print(f"🔍 Total hash calculation completed in {total_elapsed:.2f}s")
        print(f"🔍 Scan complete: {total_scanned} files scanned, {total_relevant} relevant, {len(file_hashes)} hashed")
        if total_scanned > 0:
            print(f"🔍 Performance: {((total_relevant/total_scanned)*100):.1f}% relevance ratio")
        return {
            'final_hash': final_hash,
            'file_hashes': file_hashes,
            'total_files': len(file_hashes),
            'scan_time': scan_elapsed,
            'total_time': total_elapsed,
            'files_scanned': total_scanned,
            'files_relevant': total_relevant
        }

    # --- All other methods remain unchanged from the previous version ---
    # (For brevity, see previous script for the unchanged methods, such as:
    # find_lib_ldf_mode_in_ini, modify_platformio_ini, add_lib_ldf_mode_to_platformio_section,
    # restore_platformio_ini, read_existing_idedata, _process_real_idedata_structure,
    # write_ldf_cache_ini, apply_ldf_cache, save_ldf_cache, load_and_validate_cache,
    # compute_signature, setup_ldf_caching, clear_ldf_cache, show_ldf_cache_info, show_ldf_config)

# Register custom targets
env.AlwaysBuild(env.Alias("clear_ldf_cache", None, lambda: None))
env.AlwaysBuild(env.Alias("ldf_cache_info", None, lambda: None))
env.AlwaysBuild(env.Alias("show_ldf_config", None, lambda: None))

# Initialize and run
ldf_optimizer = LDFCacheOptimizer(env)
ldf_optimizer.setup_ldf_caching()
