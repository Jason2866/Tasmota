# ldf_cache.py
"""
PlatformIO Advanced Script for intelligent LDF caching using idedata.json.
This module optimizes build performance by reading LDF results from idedata.json
and reusing them to bypass LDF on subsequent builds.

Copyright: Jason2866
"""

Import("env")
import os
import hashlib
import datetime
import time
import re
import json
from platformio.project.config import ProjectConfig

# ------------------- Ensure idedata.json is created ------------------------

def ensure_idedata_target():
    """
    Füge das Target 'idedata' zum Build hinzu, damit idedata.json erstellt wird.
    """
    current_targets = [str(target) for target in BUILD_TARGETS]
    if "idedata" not in current_targets:
        env.Default("idedata")
        print("🔧 Added 'idedata' target to ensure idedata.json creation")

# Führe die idedata-Target-Sicherstellung aus
ensure_idedata_target()

class LDFCacheOptimizer:
    """
    Intelligent LDF (Library Dependency Finder) cache optimizer for PlatformIO.

    This class reads LDF results from idedata.json and converts them to 
    reusable configuration, allowing subsequent builds to bypass LDF entirely.
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
        self.platformio_ini = os.path.join(self.project_dir, "platformio.ini")
        self.idedata_file = os.path.join(self.project_dir, ".pio", "build", self.env['PIOENV'], "idedata.json")
        self.original_ldf_mode = None
        self.ALL_RELEVANT_EXTENSIONS = self.HEADER_EXTENSIONS | self.SOURCE_EXTENSIONS | self.CONFIG_EXTENSIONS

    # ------------------- PlatformIO.ini Modification Methods -------------------

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

    # ------------------- Smart Hash Generation & Comparison -------------------

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

    # ------------------- Enhanced Cache Validation ----------------------------

    def load_and_validate_cache(self):
        """
        Load and validate cache with smart hash comparison, signature, and PIO version.

        Returns:
            dict or None: Cache data if valid, None if invalid or non-existent
        """
        if not os.path.exists(self.cache_file):
            print("🔍 No cache file exists")
            return None
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_content = f.read()
            
            # Parse JSON cache data
            if 'cache_json' in cache_content:
                exec(cache_content)
                cache_data = locals()['cache_data']
            else:
                # Fallback for old format
                cache_data = eval(cache_content.split('\n\n', 1)[1])

            # PlatformIO version check
            current_pio_version = getattr(self.env, "PioVersion", lambda: "unknown")()
            if cache_data.get('pio_version') != current_pio_version:
                print(f"⚠ Cache invalid: PlatformIO version changed from {cache_data.get('pio_version')} to {current_pio_version}")
                clear_ldf_cache()
                return None

            # Signature check (integrity)
            expected_signature = cache_data.get('signature')
            actual_signature = self.compute_signature(cache_data)
            if expected_signature != actual_signature:
                print("⚠ Cache invalid: Signature mismatch. Possible file tampering or corruption.")
                clear_ldf_cache()
                return None

            # Environment check
            if cache_data.get('pioenv') != self.env['PIOENV']:
                print(f"🔄 Environment changed: {cache_data.get('pioenv')} -> {self.env['PIOENV']}")
                clear_ldf_cache()
                return None

            # Detailed hash comparison
            print("🔍 Comparing hashes (showing only differences)...")
            current_hash_details = self.get_project_hash_with_details()
            if cache_data.get('project_hash') != current_hash_details['final_hash']:
                print("\n🔄 Project files changed:")
                self.compare_hash_details(current_hash_details['file_hashes'], cache_data.get('hash_details', {}))
                clear_ldf_cache()
                return None

            print("✅ No include-relevant changes - cache valid")
            return cache_data

        except Exception as e:
            print(f"⚠ Cache validation failed: {e}")
            clear_ldf_cache()
            return None

    def compute_signature(self, cache_data):
        """
        Compute a signature for the cache to detect tampering.

        Args:
            cache_data (dict): The cache data dictionary

        Returns:
            str: SHA256 signature string
        """
        # Exclude the signature field itself
        data = dict(cache_data)
        data.pop('signature', None)
        raw = repr(data).encode()
        return hashlib.sha256(raw).hexdigest()

    # ------------------- LDF Results Extraction from idedata.json --------------

    def read_existing_idedata(self):
        """
        Lese die idedata.json Datei (die durch das idedata-Target erstellt wurde).
        """
        try:
            if os.path.exists(self.idedata_file):
                print(f"✅ Found idedata.json: {self.idedata_file}")
                with open(self.idedata_file, 'r') as f:
                    idedata = json.loads(f.read())
                    return self._process_idedata_results(idedata)
            else:
                print(f"❌ idedata.json not found: {self.idedata_file}")
                print("   This should not happen with the idedata target!")
                return None
                
        except Exception as e:
            print(f"❌ Error reading idedata.json: {e}")
            return None

    def _process_idedata_results(self, idedata):
        """
        Verarbeite die LDF-Ergebnisse aus idedata.json.
        """
        ldf_cache = {
            'libraries': [],
            'include_paths': [],
            'defines': [],
            'build_flags': [],
            'lib_deps_entries': []
        }
        
        if not idedata:
            return ldf_cache
        
        print("🔍 Processing LDF results from idedata.json...")
        
        # Extrahiere Libraries aus lib_deps
        lib_deps = idedata.get('lib_deps', [])
        print(f"📚 Found {len(lib_deps)} library dependencies")
        
        for lib_path in lib_deps:
            lib_name = os.path.basename(lib_path)
            ldf_cache['libraries'].append({
                'name': lib_name,
                'path': lib_path
            })
            
            # Konvertiere zu lib_deps Format
            if 'framework-' in lib_path:
                platform = self.env.get('PLATFORM', 'esp32')
                lib_deps_entry = f"${{platformio.packages_dir}}/framework-{platform}/libraries/{lib_name}"
            else:
                lib_deps_entry = lib_name
                
            ldf_cache['lib_deps_entries'].append(lib_deps_entry)
            print(f"   - {lib_name} -> {lib_deps_entry}")
        
        # Extrahiere Include-Pfade
        includes = idedata.get('includes', [])
        print(f"📂 Found {len(includes)} include paths")
        
        for include_path in includes:
            if not self.is_platformio_path(include_path):
                ldf_cache['include_paths'].append(include_path)
                print(f"   - {include_path}")
        
        # Extrahiere Defines
        defines = idedata.get('defines', [])
        print(f"🔧 Found {len(defines)} defines")
        
        for define in defines:
            ldf_cache['defines'].append(define)
            print(f"   - {define}")
        
        # Extrahiere Build-Flags
        cxx_flags = idedata.get('cxx_flags', [])
        cc_flags = idedata.get('cc_flags', [])
        all_flags = cxx_flags + cc_flags
        
        print(f"🚩 Found {len(all_flags)} build flags")
        
        for flag in all_flags:
            if flag not in ldf_cache['build_flags']:
                ldf_cache['build_flags'].append(flag)
                print(f"   - {flag}")
        
        return ldf_cache

    def generate_complete_platformio_config(self, ldf_results):
        """
        Generiere vollständige platformio.ini Konfiguration.
        """
        config_lines = [
            f"# Complete LDF Cache Configuration for {self.env['PIOENV']}",
            f"# Generated: {datetime.datetime.now().isoformat()}",
            f"# Copy this to your [env:{self.env['PIOENV']}] section",
            "",
            "lib_ldf_mode = off",
            "lib_deps = "
        ]
        
        # Libraries
        for lib_dep in ldf_results['lib_deps_entries']:
            config_lines.append(f"    {lib_dep}")
        
        config_lines.append("")
        config_lines.append("build_flags = ")
        
        # Include-Pfade
        for include_path in ldf_results['include_paths']:
            config_lines.append(f"    -I\"{include_path}\"")
        
        # Defines
        for define in ldf_results['defines']:
            config_lines.append(f"    -D{define}")
        
        # Zusätzliche Build-Flags
        for flag in ldf_results['build_flags']:
            # Vermeide Duplikate von Include-Pfaden
            if not flag.startswith('-I'):
                config_lines.append(f"    {flag}")
        
        # Speichere Konfiguration
        config_content = '\n'.join(config_lines)
        config_file = os.path.join(self.project_dir, ".pio", "ldf_cache", f"complete_ldf_config_{self.env['PIOENV']}.ini")
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
        
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(config_content)
        
        print(f"\n📁 Complete LDF config saved to: {config_file}")
        print(f"\n📋 Copy this to your platformio.ini [env:{self.env['PIOENV']}] section:")
        print("=" * 60)
        print(config_content)
        print("=" * 60)
        
        return config_file

    def apply_ldf_cache(self, cache_data):
        """
        Restore full build environment from cache.
        """
        try:
            ldf_results = cache_data.get('ldf_results', {})
            
            if not ldf_results:
                print("⚠ No LDF results found in cache")
                return False
            
            print("🔧 Restoring full build environment from cache...")
            
            # Restore lib_deps
            lib_deps = ldf_results.get('lib_deps_entries', [])
            if lib_deps:
                self.env['LIB_DEPS'] = lib_deps
                print(f"📚 Restored {len(lib_deps)} library dependencies")
            
            # Restore include paths
            include_paths = ldf_results.get('include_paths', [])
            if include_paths:
                self.env.Append(CPPPATH=include_paths)
                print(f"📂 Restored {len(include_paths)} include paths")
            
            # Restore defines
            defines = ldf_results.get('defines', [])
            if defines:
                self.env.Append(CPPDEFINES=defines)
                print(f"🔧 Restored {len(defines)} preprocessor defines")
            
            # Restore build flags
            build_flags = ldf_results.get('build_flags', [])
            if build_flags:
                self.env.Append(BUILD_FLAGS=build_flags)
                print(f"🚩 Restored {len(build_flags)} build flags")
            
            return True
            
        except Exception as e:
            print(f"✗ Error restoring environment: {e}")
            return False

    def save_ldf_cache(self, target=None, source=None, env_arg=None, **kwargs):
        """
        Lese idedata.json und speichere LDF-Ergebnisse.
        """
        try:
            hash_details = self.get_project_hash_with_details()
            
            # Lese die idedata.json (sollte durch das idedata-Target erstellt worden sein)
            ldf_results = self.read_existing_idedata()
            
            if ldf_results:
                # Generiere vollständige platformio.ini Konfiguration
                config_file = self.generate_complete_platformio_config(ldf_results)
                
                pio_version = getattr(self.env, "PioVersion", lambda: "unknown")()
                
                # Speichere verwertbare Ergebnisse
                cache_data = {
                    'ldf_results': ldf_results,
                    'project_hash': hash_details['final_hash'],
                    'hash_details': hash_details['file_hashes'],
                    'pioenv': str(self.env['PIOENV']),
                    'timestamp': datetime.datetime.now().isoformat(),
                    'pio_version': pio_version,
                    'config_file': config_file
                }
                
                # Compute and add signature
                cache_data['signature'] = self.compute_signature(cache_data)
                
                os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
                
                # Speichere als JSON
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    f.write("# LDF Cache - Complete Build Environment\n")
                    f.write("# Generated automatically from idedata.json\n\n")
                    f.write("import json\n\n")
                    f.write("cache_json = '''\n")
                    f.write(json.dumps(cache_data, ensure_ascii=False, indent=2, default=str))
                    f.write("\n'''\n\n")
                    f.write("cache_data = json.loads(cache_json)\n")
                
                print(f"💾 LDF Cache saved successfully!")
                print(f"🎯 Captured complete build environment:")
                print(f"   📚 Libraries: {len(ldf_results['libraries'])}")
                print(f"   📂 Include paths: {len(ldf_results['include_paths'])}")
                print(f"   🔧 Defines: {len(ldf_results['defines'])}")
                print(f"   🚩 Build flags: {len(ldf_results['build_flags'])}")
                
            else:
                print("❌ No idedata.json found - LDF cache not created")
                print("   This should not happen with the idedata target!")
                
        except Exception as e:
            print(f"✗ Error saving LDF cache: {e}")

    # ------------------- Main Logic --------------------------------------------

    def setup_ldf_caching(self):
        """
        Orchestrate caching process with smart invalidation, signature, and version check.
        """
        print("\n=== LDF Cache Optimizer (idedata.json Mode) ===")
        cache_data = self.load_and_validate_cache()
        if cache_data:
            print("🚀 Valid cache found - disabling LDF")
            if self.modify_platformio_ini("off"):
                self.apply_ldf_cache(cache_data)
                self.env.AddPostAction("checkprogsize", lambda *args: self.restore_platformio_ini())
        else:
            print("🔄 No valid cache - running full LDF")
            self.env.AddPostAction("checkprogsize", self.save_ldf_cache)
        print("=" * 60)

# ------------------- Cache Management Commands --------------------------------

def clear_ldf_cache():
    """
    Delete LDF cache file.
    """
    project_dir = env.subst("$PROJECT_DIR")
    cache_file = os.path.join(project_dir, ".pio", "ldf_cache", f"ldf_cache_{env['PIOENV']}.py")
    if os.path.exists(cache_file):
        try:
            os.remove(cache_file)
            print("✓ LDF Cache deleted")
        except Exception as e:
            print(f"✗ Error deleting cache: {e}")
    else:
        print("ℹ No LDF Cache present")

def show_ldf_cache_info():
    """
    Display cache information.
    """
    project_dir = env.subst("$PROJECT_DIR")
    cache_file = os.path.join(project_dir, ".pio", "ldf_cache", f"ldf_cache_{env['PIOENV']}.py")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_content = f.read()
            
            # Parse JSON cache data
            if 'cache_json' in cache_content:
                exec(cache_content)
                cache_data = locals()['cache_data']
            else:
                cache_data = eval(cache_content.split('\n\n', 1)[1])
                
            ldf_results = cache_data.get('ldf_results', {})
            
            print("\n=== LDF Cache Info ===")
            print(f"Environment:  {cache_data.get('pioenv', 'unknown')}")
            print(f"Project hash: {cache_data.get('project_hash', 'unknown')}")
            print(f"PlatformIO version: {cache_data.get('pio_version', 'unknown')}")
            print(f"Signature:    {cache_data.get('signature', 'none')}")
            print(f"Created:      {cache_data.get('timestamp', 'unknown')}")
            print(f"File size:    {os.path.getsize(cache_file)} bytes")
            print(f"Libraries:    {len(ldf_results.get('libraries', []))}")
            print(f"Include paths: {len(ldf_results.get('include_paths', []))}")
            print(f"Defines:      {len(ldf_results.get('defines', []))}")
            print(f"Build flags:  {len(ldf_results.get('build_flags', []))}")
            print("=" * 25)
        except Exception as e:
            print(f"Error reading cache: {e}")
    else:
        print("No LDF Cache present")

def show_ldf_config():
    """
    Display the generated LDF configuration.
    """
    project_dir = env.subst("$PROJECT_DIR")
    config_file = os.path.join(project_dir, ".pio", "ldf_cache", f"complete_ldf_config_{env['PIOENV']}.ini")
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_content = f.read()
            print("\n=== Complete LDF Configuration ===")
            print(config_content)
            print("=" * 40)
        except Exception as e:
            print(f"Error reading LDF config: {e}")
    else:
        print("No LDF configuration found")

# Register custom targets
env.AlwaysBuild(env.Alias("clear_ldf_cache", None, clear_ldf_cache))
env.AlwaysBuild(env.Alias("ldf_cache_info", None, show_ldf_cache_info))
env.AlwaysBuild(env.Alias("show_ldf_config", None, show_ldf_config))

# Initialize and run
ldf_optimizer = LDFCacheOptimizer(env)
ldf_optimizer.setup_ldf_caching()
