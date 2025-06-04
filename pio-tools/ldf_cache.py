# ldf_cache.py
"""
PlatformIO Advanced Script for intelligent LDF caching.
This module optimizes build performance through selective LDF caching and restoring.

Copyright: Jason2866
"""

Import("env")
import os
import hashlib
import datetime
import time
import re
from platformio.project.config import ProjectConfig

class LDFCacheOptimizer:
    """
    Intelligent LDF (Library Dependency Finder) cache optimizer for PlatformIO.

    This class manages caching of library dependency resolution results to speed up
    subsequent builds when no include-relevant changes have been made to the project.
    Uses SCons native serialization (env.Dump) to store and restore all build variables
    without losing any information. Only variables present in the environment are saved/restored.
    """

    # File type categories for early filtering
    HEADER_EXTENSIONS = frozenset(['.h', '.hpp', '.hxx', '.h++', '.hh', '.inc', '.tpp', '.tcc'])
    SOURCE_EXTENSIONS = frozenset(['.c', '.cpp', '.cxx', '.c++', '.cc', '.ino'])
    CONFIG_EXTENSIONS = frozenset(['.json', '.properties', '.txt', '.ini'])

    # Directories to ignore during scanning
    IGNORE_DIRS = frozenset([
        '.git', '.github', '.cache', '.vscode', '.pio', 'boards',
        'data', 'build', 'pio-tools', 'tools', '__pycache__', 'variants', 
        'berry', 'berry_tasmota', 'berry_matter', 'berry_custom',
        'berry_animate', 'berry_mapping', 'berry_int64', 'displaydesc',
        'html_compressed', 'html_uncompressed', 'language', 'energy_modbus_configs'
    ])

    # List of all potentially relevant SCons variables for LDF caching
    LDF_SCONS_VARS = [
        'CPPPATH', 'LIBPATH', 'LIBS', 'CPPDEFINES', 'SRC_FILTER',
        'CCFLAGS', 'CXXFLAGS', 'LINKFLAGS'
    ]

    def __init__(self, environment):
        """
        Initialize the LDF Cache Optimizer.

        Args:
            environment: PlatformIO SCons environment object
        """
        self.env = environment
        self.cache_file = os.path.join(self.env.subst("$BUILD_DIR"), "ldf_cache_sconsdump.py")
        self.project_dir = self.env.subst("$PROJECT_DIR")
        self.src_dir = self.env.subst("$PROJECT_SRC_DIR")
        self.platformio_ini = os.path.join(self.project_dir, "platformio.ini")
        self.original_ldf_mode = None
        self.ALL_RELEVANT_EXTENSIONS = self.HEADER_EXTENSIONS | self.SOURCE_EXTENSIONS | self.CONFIG_EXTENSIONS

    def find_lib_ldf_mode_in_ini(self):
        """
        Find all occurrences of lib_ldf_mode in platformio.ini across all sections.

        Returns:
            list: List of dictionaries with section, line_number, and line content
        """
        lib_ldf_mode_lines = []
        try:
            if os.path.exists(self.platformio_ini):
                with open(self.platformio_ini, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                for i, line in enumerate(lines):
                    if 'lib_ldf_mode' in line.lower():
                        section = None
                        for j in range(i, -1, -1):
                            if lines[j].strip().startswith('[') and lines[j].strip().endswith(']'):
                                section = lines[j].strip()
                                break
                        lib_ldf_mode_lines.append({
                            'section': section, 
                            'line_number': i+1, 
                            'line': line.strip(),
                            'line_index': i
                        })
                return lib_ldf_mode_lines
            else:
                print(f"❌ platformio.ini not found: {self.platformio_ini}")
                return []
        except Exception as e:
            print(f"❌ Error reading platformio.ini: {e}")
            return []

    def modify_platformio_ini(self, new_ldf_mode):
        """
        Modify or add lib_ldf_mode in platformio.ini.

        Args:
            new_ldf_mode (str): New LDF mode ('off' or 'chain')
        Returns:
            bool: True if modification was successful, False otherwise
        """
        try:
            ldf_entries = self.find_lib_ldf_mode_in_ini()
            if ldf_entries:
                first_entry = ldf_entries[0]
                with open(self.platformio_ini, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                current_line = lines[first_entry['line_index']]
                match = re.search(r'lib_ldf_mode\s*=\s*(\w+)', current_line)
                if match:
                    self.original_ldf_mode = match.group(1)
                else:
                    self.original_ldf_mode = "chain"
                lines[first_entry['line_index']] = re.sub(
                    r'lib_ldf_mode\s*=\s*\w+', 
                    f'lib_ldf_mode = {new_ldf_mode}', 
                    current_line
                )
                with open(self.platformio_ini, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                print(f"🔧 Modified {first_entry['section']}: lib_ldf_mode = {new_ldf_mode}")
                return True
            else:
                print("🔍 No existing lib_ldf_mode found, adding to [platformio] section")
                return self.add_lib_ldf_mode_to_platformio_section(new_ldf_mode)
        except Exception as e:
            print(f"❌ Error modifying platformio.ini: {e}")
            return False

    def add_lib_ldf_mode_to_platformio_section(self, new_ldf_mode):
        """
        Add lib_ldf_mode to [platformio] section if not present.

        Args:
            new_ldf_mode (str): New LDF mode to add
        Returns:
            bool: True if addition was successful, False otherwise
        """
        try:
            with open(self.platformio_ini, 'r', encoding='utf-8') as f:
                content = f.read()
            self.original_ldf_mode = "chain"
            platformio_section = re.search(r'\[platformio\]', content)
            if platformio_section:
                insert_pos = platformio_section.end()
                new_content = (content[:insert_pos] + 
                             f'\nlib_ldf_mode = {new_ldf_mode}' + 
                             content[insert_pos:])
            else:
                new_content = f'[platformio]\nlib_ldf_mode = {new_ldf_mode}\n\n' + content
            with open(self.platformio_ini, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"🔧 Added to [platformio]: lib_ldf_mode = {new_ldf_mode}")
            return True
        except Exception as e:
            print(f"❌ Error adding lib_ldf_mode: {e}")
            return False

    def restore_platformio_ini(self):
        """
        Restore the original lib_ldf_mode in platformio.ini after build.
        """
        if self.original_ldf_mode is None:
            return
        try:
            ldf_entries = self.find_lib_ldf_mode_in_ini()
            if ldf_entries:
                first_entry = ldf_entries[0]
                with open(self.platformio_ini, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                if self.original_ldf_mode == "chain":
                    lines.pop(first_entry['line_index'])
                else:
                    lines[first_entry['line_index']] = re.sub(
                        r'lib_ldf_mode\s*=\s*\w+', 
                        f'lib_ldf_mode = {self.original_ldf_mode}', 
                        lines[first_entry['line_index']]
                    )
                with open(self.platformio_ini, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                print(f"🔧 Restored lib_ldf_mode = {self.original_ldf_mode}")
        except Exception as e:
            print(f"❌ Error restoring platformio.ini: {e}")

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

    def is_platformio_path(self, path):
        """
        Check if path belongs to PlatformIO installation.

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

    def get_project_hash_with_details(self):
        """
        Generate hash with detailed file tracking and optimized early filtering.
        Excludes all PlatformIO-installed components and lib_ldf_mode settings.

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
            if self.is_platformio_path(inc_dir):
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
                    if self.is_platformio_path(root):
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

    def load_and_validate_cache(self):
        """
        Load cache using Python text format (eval).

        Returns:
            dict or None: Cache data if valid, None if invalid or non-existent
        """
        if not os.path.exists(self.cache_file):
            print("🔍 No cache file exists")
            return None
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_content = f.read()
            cache_data = eval(cache_content.split('\n\n', 1)[1])  # Skip comments
            print(f"✅ Cache loaded successfully from {os.path.basename(self.cache_file)}")
            if cache_data.get('pioenv') != self.env['PIOENV']:
                print(f"🔄 Environment changed: {cache_data.get('pioenv')} -> {self.env['PIOENV']}")
                return None
            print("🔍 Comparing hashes (showing only differences)...")
            comparison_start = time.time()
            current_hash_details = self.get_project_hash_with_details()
            cached_hash = cache_data.get('project_hash')
            cached_hash_details = cache_data.get('hash_details', {})
            current_hash = current_hash_details['final_hash']
            comparison_elapsed = time.time() - comparison_start
            print(f"\n🔍 Hash comparison completed in {comparison_elapsed:.2f}s:")
            print(f"   Current:  {current_hash}")
            print(f"   Cached:   {cached_hash}")
            print(f"   Match:    {current_hash == cached_hash}")
            if current_hash != cached_hash:
                print("\n🔄 Files with DIFFERENT hashes:")
                self.compare_hash_details(current_hash_details['file_hashes'], cached_hash_details)
                return None
            print("✅ No include-relevant changes - cache usable")
            return cache_data
        except Exception as e:
            print(f"⚠ Cache validation failed: {e}")
            return None

    def apply_ldf_cache(self, cache_data):
        """
        Restore using SCons native deserialization.
        Only restore variables present in the cache.
        """
        try:
            apply_start = time.time()
            scons_dump_str = cache_data.get('scons_dump', '{}')
            scons_vars = eval(scons_dump_str)
            print(f"🔧 Restoring SCons variables from native dump...")
            for var_name in self.LDF_SCONS_VARS:
                if var_name in scons_vars:
                    var_value = scons_vars[var_name]
                    if var_name == 'CPPPATH':
                        self.env.PrependUnique(CPPPATH=var_value)
                    elif var_name == 'LIBPATH':
                        self.env.PrependUnique(LIBPATH=var_value)
                    elif var_name == 'LIBS':
                        self.env.PrependUnique(LIBS=var_value)
                    elif var_name == 'CPPDEFINES':
                        self.env.AppendUnique(CPPDEFINES=var_value)
                    elif var_name == 'SRC_FILTER':
                        self.env.Replace(SRC_FILTER=var_value)
                    elif var_name == 'CCFLAGS':
                        self.env.AppendUnique(CCFLAGS=var_value)
                    elif var_name == 'CXXFLAGS':
                        self.env.AppendUnique(CXXFLAGS=var_value)
                    elif var_name == 'LINKFLAGS':
                        self.env.AppendUnique(LINKFLAGS=var_value)
                    print(f"🔧 Restored {var_name}: {type(var_value)} with {len(var_value) if hasattr(var_value, '__len__') else 'N/A'} items")
            apply_elapsed = time.time() - apply_start
            print(f"📦 LDF cache applied in {apply_elapsed:.3f}s using SCons native format")
            return True
        except Exception as e:
            print(f"✗ Error applying LDF cache: {e}")
            return False

    def save_ldf_cache(self, target=None, source=None, env_arg=None, **kwargs):
        """
        Save using SCons native serialization - preserves everything.
        Only save variables present in the environment.
        """
        if self.env.get("LIB_LDF_MODE") == "off":
            return
        try:
            save_start = time.time()
            print("💾 Saving LDF cache using SCons native Dump...")
            hash_details = self.get_project_hash_with_details()
            # Only include SCons vars that exist in the environment
            dump_vars = [var for var in self.LDF_SCONS_VARS if var in self.env]
            scons_vars_dump = self.env.Dump(*dump_vars, format='pretty')
            cache_data = {
                'project_hash': hash_details['final_hash'],
                'hash_details': hash_details['file_hashes'],
                'pioenv': str(self.env['PIOENV']),
                'timestamp': datetime.datetime.now().isoformat(),
                'performance': {
                    'scan_time': hash_details.get('scan_time', 0),
                    'total_time': hash_details.get('total_time', 0),
                    'files_scanned': hash_details.get('files_scanned', 0),
                    'files_relevant': hash_details.get('files_relevant', 0)
                },
                'scons_dump': scons_vars_dump
            }
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                f.write("# LDF Cache - SCons Native Format\n")
                f.write("# Generated automatically\n\n")
                f.write(repr(cache_data))
            save_elapsed = time.time() - save_start
            print(f"💾 LDF cache saved in {save_elapsed:.3f}s using SCons native serialization")
        except Exception as e:
            print(f"✗ Error saving LDF cache: {e}")

    def compare_hash_details(self, current_hashes, cached_hashes):
        """
        Compare hash details and show only differences.
        """
        differences_found = 0
        for file_path, current_hash in current_hashes.items():
            if file_path not in cached_hashes:
                print(f"   ➕ NEW: {file_path} -> {current_hash}")
                differences_found += 1
        for file_path, current_hash in current_hashes.items():
            if file_path in cached_hashes:
                cached_hash = cached_hashes[file_path]
                if current_hash != cached_hash:
                    print(f"   🔄 CHANGED: {file_path}")
                    print(f"      Old: {cached_hash}")
                    print(f"      New: {current_hash}")
                    differences_found += 1
        for file_path in cached_hashes:
            if file_path not in current_hashes:
                print(f"   ➖ DELETED: {file_path}")
                differences_found += 1
        print(f"\n   Total differences: {differences_found}")
        print(f"   Current files: {len(current_hashes)}")
        print(f"   Cached files: {len(cached_hashes)}")

    def setup_ldf_caching(self):
        """
        Main logic for intelligent LDF caching with platformio.ini modification.
        Orchestrates the entire caching process: validates existing cache,
        and if valid, modifies platformio.ini to disable LDF before PlatformIO
        reads the configuration. Uses SCons native serialization.
        """
        setup_start = time.time()
        print("\n=== LDF Cache Optimizer (SCons Dump, robust) ===")
        cache_data = self.load_and_validate_cache()
        if cache_data:
            print("🚀 Cache available - disabling LDF via platformio.ini modification")
            success = self.modify_platformio_ini("off")
            if success:
                self.apply_ldf_cache(cache_data)
                restore_action = self.env.Action(lambda t, s, e: self.restore_platformio_ini())
                restore_action.strfunction = lambda target, source, env: ''
                self.env.AddPostAction("checkprogsize", restore_action)
            else:
                print("✗ Failed to modify platformio.ini - proceeding with normal LDF")
        else:
            print("🔄 No cache available - LDF will run normally")
            silent_action = self.env.Action(self.save_ldf_cache)
            silent_action.strfunction = lambda target, source, env: ''
            self.env.AddPostAction("checkprogsize", silent_action)
        setup_elapsed = time.time() - setup_start
        print(f"⏱️ LDF Cache setup completed in {setup_elapsed:.3f}s")
        print("=" * 60)

def clear_ldf_cache():
    """
    Delete LDF cache file.
    """
    cache_file = os.path.join(env.subst("$BUILD_DIR"), "ldf_cache_sconsdump.py")
    if os.path.exists(cache_file):
        try:
            os.remove(cache_file)
            print("✓ LDF Cache deleted")
        except (IOError, OSError, PermissionError) as e:
            print(f"✗ Error deleting cache: {e}")
    else:
        print("ℹ No LDF Cache present")

def show_ldf_cache_info():
    """
    Display cache information.
    """
    cache_file = os.path.join(env.subst("$BUILD_DIR"), "ldf_cache_sconsdump.py")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                content = f.read()
                cache_data = eval(content.split('\n\n', 1)[1])
            print(f"\n=== LDF Cache Info ===")
            print(f"Created:      {cache_data.get('timestamp', 'unknown')}")
            print(f"Environment:  {cache_data.get('pioenv', 'unknown')}")
            print(f"Hash:         {cache_data.get('project_hash', 'unknown')}")
            print(f"File size:    {os.path.getsize(cache_file)} bytes")
            perf = cache_data.get('performance', {})
            if perf:
                print(f"\n--- Performance Metrics ---")
                print(f"Scan time:    {perf.get('scan_time', 0):.2f}s")
                print(f"Total time:   {perf.get('total_time', 0):.2f}s")
                print(f"Files scanned: {perf.get('files_scanned', 0)}")
                print(f"Files relevant: {perf.get('files_relevant', 0)}")
                if perf.get('files_scanned', 0) > 0:
                    relevance = (perf.get('files_relevant', 0) / perf.get('files_scanned', 1)) * 100
                    print(f"Relevance:    {relevance:.1f}%")
            print("=" * 25)
        except Exception as e:
            print(f"Error reading cache info: {e}")
    else:
        print("No LDF Cache present")

def force_ldf_rebuild():
    """
    Force LDF recalculation.
    """
    clear_ldf_cache()
    print("LDF will be recalculated on next build")

# Register custom targets for cache management
env.AlwaysBuild(env.Alias("clear_ldf_cache", None, clear_ldf_cache))
env.AlwaysBuild(env.Alias("ldf_cache_info", None, show_ldf_cache_info))
env.AlwaysBuild(env.Alias("force_ldf_rebuild", None, force_ldf_rebuild))

# Initialize and run LDF Cache Optimizer
ldf_optimizer = LDFCacheOptimizer(env)
ldf_optimizer.setup_ldf_caching()
