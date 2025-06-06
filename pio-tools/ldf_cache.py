# ldf_cache.py
"""
PlatformIO Advanced Script for intelligent LDF caching using idedata.json.
All LDF-cached build options (except lib_ldf_mode) are written to ldf_cache.ini,
which must be included in platformio.ini via 'extra_configs = ldf_cache.ini'.
Framework and toolchain files are excluded from the project hash.
idedata.json is always generated together with the build using a smart pre-action.
idedata.json is stored in .pio directory with environment name extension.

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
import subprocess
import sys
import shutil
from platformio.project.config import ProjectConfig

def smart_build_integrated(source, target, env):
    """
    Ensure idedata.json is generated together with the build for the current environment.
    If missing, re-invoke PlatformIO for this environment with buildprog and idedata targets.
    idedata.json is stored in .pio directory with environment name extension.
    """
    # Prevent recursion during smart build execution
    if os.environ.get("SMART_BUILD_RUNNING"):
        return

    env_name = env.get("PIOENV")
    
    # Store idedata.json in .pio path with env extension
    pio_dir = os.path.join(env.get("PROJECT_DIR"), ".pio")
    idedata_path = os.path.join(pio_dir, f"idedata_{env_name}.json")
    
    # Original path for fallback check
    original_idedata_path = os.path.join(env.get("BUILD_DIR"), "idedata.json")

    if not os.path.exists(idedata_path) and not os.path.exists(original_idedata_path):
        print(f"idedata.json for {env_name} missing - running Smart Build")

        env_copy = os.environ.copy()
        env_copy["SMART_BUILD_RUNNING"] = "1"

        try:
            subprocess.run([
                sys.executable, "-m", "platformio",
                "run", "-e", env_name, "-t", "buildprog", "-t", "idedata"
            ], cwd=env.get("PROJECT_DIR"), env=env_copy, check=True)

            # Copy idedata.json from build directory to .pio path with env name
            if os.path.exists(original_idedata_path):
                os.makedirs(pio_dir, exist_ok=True)
                shutil.copy2(original_idedata_path, idedata_path)
                print(f"idedata.json copied to {idedata_path}")

            print("Smart Build successful - skipping further build steps")
            Exit(0)

        except subprocess.CalledProcessError as e:
            print(f"Smart Build failed: {e}")
            Exit(1)

# Register PreAction for buildprog to ensure early execution and idedata.json presence
env.AddPreAction("buildprog", smart_build_integrated)

class LDFCacheOptimizer:
    """
    PlatformIO LDF (Library Dependency Finder) cache optimizer.

    Reads LDF results from idedata.json, writes all build options to ldf_cache.ini,
    and stores the cache as a Python dict for robust validation.
    Framework and toolchain files are excluded from the project hash.
    idedata.json is stored in .pio directory with environment name extension.
    """

    # File extensions for different types of source files
    HEADER_EXTENSIONS = frozenset(['.h', '.hpp', '.hxx', '.h++', '.hh', '.inc', '.tpp', '.tcc'])
    SOURCE_EXTENSIONS = frozenset(['.c', '.cpp', '.cxx', '.c++', '.cc', '.ino'])
    CONFIG_EXTENSIONS = frozenset(['.json', '.properties', '.txt', '.ini'])

    # Directories to ignore during project scanning
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
        
        # Changed: idedata.json in .pio path with env name extension
        self.idedata_file = os.path.join(self.project_dir, ".pio", f"idedata_{self.env['PIOENV']}.json")
        
        self.original_ldf_mode = None
        self.ALL_RELEVANT_EXTENSIONS = self.HEADER_EXTENSIONS | self.SOURCE_EXTENSIONS | self.CONFIG_EXTENSIONS

    def is_platformio_path(self, path):
        """
        Check if path belongs to PlatformIO installation (including .pio, .platformio, etc).

        Args:
            path (str): Path to check

        Returns:
            bool: True if path is part of PlatformIO installation
        """
        platformio_paths = set()
        
        # Add PlatformIO core directory if available
        if 'PLATFORMIO_CORE_DIR' in os.environ:
            platformio_paths.add(os.path.normpath(os.environ['PLATFORMIO_CORE_DIR']))
        
        # Add PlatformIO home directory
        pio_home = os.path.join(ProjectConfig.get_instance().get("platformio", "platforms_dir"))
        platformio_paths.add(os.path.normpath(pio_home))
        
        # Add project .pio directory
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
        This optimizes cache invalidation by only considering changes that affect dependencies.

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
                    # Skip comment lines
                    if stripped.startswith('//'):
                        continue
                    # Include #include directives and relevant #define statements
                    if (stripped.startswith('#include') or 
                        (stripped.startswith('#define') and 
                         any(keyword in stripped.upper() for keyword in ['INCLUDE', 'PATH', 'CONFIG']))):
                        include_lines.append(stripped)
            
            content = '\n'.join(include_lines)
            return hashlib.sha256(content.encode()).hexdigest()[:16]
        except (IOError, OSError, PermissionError, UnicodeDecodeError):
            # Fallback to full file hash if include parsing fails
            return self._get_file_hash(file_path)

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
        
        # Skip generated .ino.cpp file
        generated_cpp = os.path.basename(self.project_dir).lower() + ".ino.cpp"
        
        # Hash platformio.ini excluding lib_ldf_mode settings
        if os.path.exists(self.platformio_ini):
            try:
                with open(self.platformio_ini, 'r', encoding='utf-8') as f:
                    ini_content = f.read()
                # Remove lib_ldf_mode lines to avoid cache invalidation when toggling LDF
                filtered_content = re.sub(r'lib_ldf_mode\s*=\s*\w+\n?', '', ini_content)
                ini_hash = hashlib.sha256(filtered_content.encode()).hexdigest()[:16]
                hash_data.append(ini_hash)
                file_hashes['platformio.ini'] = ini_hash
            except Exception as e:
                print(f"⚠ Error reading platformio.ini: {e}")

        # Define directories to scan
        scan_dirs = []
        
        # Add source directory
        if os.path.exists(self.src_dir):
            scan_dirs.append(('source', self.src_dir))
        
        # Add lib directory if it exists and is not a PlatformIO path
        lib_dir = os.path.join(self.project_dir, "lib")
        if os.path.exists(lib_dir) and not self.is_platformio_path(lib_dir):
            scan_dirs.append(('library', lib_dir))
        
        # Add include paths from environment
        for inc_path in self.env.get('CPPPATH', []):
            inc_dir = str(inc_path)
            # Skip PlatformIO paths and known system directories
            if self.is_platformio_path(inc_dir):
                continue
            if any(skip_dir in inc_dir for skip_dir in ['variants', '.platformio', '.pio']):
                continue
            if os.path.exists(inc_dir) and inc_dir != self.src_dir:
                scan_dirs.append(('include', inc_dir))

        total_scanned = 0
        total_relevant = 0
        scan_start_time = time.time()

        # Scan all relevant directories
        for dir_type, scan_dir in scan_dirs:
            print(f"🔍 Scanning {dir_type} directory: {scan_dir}")
            try:
                for root, dirs, files in os.walk(scan_dir):
                    # Skip PlatformIO paths
                    if self.is_platformio_path(root):
                        continue
                    
                    # Filter out ignored directories
                    dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]
                    
                    # Pre-filter files by extension for performance
                    relevant_files = []
                    for file in files:
                        total_scanned += 1
                        file_ext = os.path.splitext(file)[1].lower()
                        if file_ext in self.ALL_RELEVANT_EXTENSIONS:
                            relevant_files.append((file, file_ext))
                            total_relevant += 1

                    # Process relevant files
                    for file, file_ext in relevant_files:
                        # Skip generated Arduino .cpp file
                        if file == generated_cpp:
                            continue
                        
                        file_path = os.path.join(root, file)
                        
                        # Different hashing strategies based on file type
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
        
        # Generate final project hash
        final_hash = hashlib.sha256(''.join(hash_data).encode()).hexdigest()[:16]
        total_elapsed = time.time() - start_time

        # Performance reporting
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
                        # Find the section this line belongs to
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
                # Modify existing lib_ldf_mode entry
                first_entry = ldf_entries[0]
                with open(self.platformio_ini, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # Extract current LDF mode for restoration
                current_line = lines[first_entry['line_index']]
                match = re.search(r'lib_ldf_mode\s*=\s*(\w+)', current_line)
                if match:
                    self.original_ldf_mode = match.group(1)
                else:
                    self.original_ldf_mode = "chain"
                
                # Replace with new LDF mode
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
                # Add new lib_ldf_mode entry
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
            
            self.original_ldf_mode = "chain"  # Default PlatformIO LDF mode
            
            # Find [platformio] section
            platformio_section = re.search(r'\[platformio\]', content)
            if platformio_section:
                # Add after [platformio] section header
                insert_pos = platformio_section.end()
                new_content = (content[:insert_pos] + 
                             f'\nlib_ldf_mode = {new_ldf_mode}' + 
                             content[insert_pos:])
            else:
                # Create [platformio] section at the beginning
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
                    # Remove the line if original mode was default
                    lines.pop(first_entry['line_index'])
                else:
                    # Restore original mode
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

    def read_existing_idedata(self):
        """
        Read and process idedata.json using the real PlatformIO structure.
        
        Returns:
            dict: LDF cache data extracted from idedata.json
        """
        try:
            if not os.path.exists(self.idedata_file):
                print(f"❌ idedata.json not found: {self.idedata_file}")
                print("   This should never happen if idedata is a dependency!")
                return None
            
            print(f"✅ Reading idedata.json: {self.idedata_file}")
            with open(self.idedata_file, 'r') as f:
                idedata = json.loads(f.read())
                return self._process_real_idedata_structure(idedata)
                
        except Exception as e:
            print(f"❌ Error reading idedata.json: {e}")
            return None

    def _process_real_idedata_structure(self, idedata):
        """
        Process the real idedata.json structure as generated by PlatformIO.
        
        Args:
            idedata (dict): Parsed idedata.json content
        Returns:
            dict: LDF cache data
        """
        ldf_cache = {
            'libraries': [],
            'include_paths': [],
            'defines': [],
            'build_flags': [],
            'lib_deps_entries': [],
            'libsource_dirs': []
        }
        
        if not idedata:
            return ldf_cache

        # 1. Library source directories (libsource_dirs)
        libsource_dirs = idedata.get('libsource_dirs', [])
        for lib_dir in libsource_dirs:
            ldf_cache['libsource_dirs'].append(lib_dir)
            
            # Convert to lib_deps entry format
            if 'lib/' in lib_dir and self.project_dir in lib_dir:
                lib_name = os.path.basename(lib_dir)
                lib_deps_entry = f"./lib/{lib_name}"
            elif 'framework-' in lib_dir:
                lib_deps_entry = lib_dir.replace(os.path.expanduser('~/.platformio/packages'), '${platformio.packages_dir}')
            else:
                lib_deps_entry = lib_dir
            
            ldf_cache['lib_deps_entries'].append(lib_deps_entry)
            ldf_cache['libraries'].append({
                'name': os.path.basename(lib_dir),
                'path': lib_dir,
                'lib_deps_entry': lib_deps_entry
            })

        # 2. Include paths from includes.build
        includes_build = idedata.get('includes', {}).get('build', [])
        for include_path in includes_build:
            ldf_cache['include_paths'].append(include_path)

        # 3. Preprocessor defines
        defines = idedata.get('defines', [])
        for define in defines:
            ldf_cache['defines'].append(define)

        # 4. Build flags
        cc_flags = idedata.get('cc_flags', [])
        cxx_flags = idedata.get('cxx_flags', [])
        all_flags = cc_flags + cxx_flags
        for flag in all_flags:
            if flag not in ldf_cache['build_flags']:
                ldf_cache['build_flags'].append(flag)

        return ldf_cache

    def write_ldf_cache_ini(self, ldf_results):
        """
        Write all LDF-cached build options to ldf_cache.ini.
        
        Args:
            ldf_results (dict): LDF results containing libraries, includes, defines, and flags
        """
        ini_lines = [
            f"[env:{self.env['PIOENV']}]",
            "lib_deps ="
        ]
        
        # Add library dependencies
        for lib_dep in ldf_results['lib_deps_entries']:
            ini_lines.append(f"    {lib_dep}")
        
        ini_lines.append("")
        ini_lines.append("build_flags =")
        
        # Add build flags
        for flag in ldf_results['build_flags']:
            ini_lines.append(f"    {flag}")
        
        # Add include paths
        for include_path in ldf_results['include_paths']:
            ini_lines.append(f"    -I\"{include_path}\"")
        
        # Add preprocessor defines
        for define in ldf_results['defines']:
            ini_lines.append(f"    -D{define}")

        ini_content = "\n".join(ini_lines)
        
        with open(self.ldf_cache_ini, "w", encoding="utf-8") as f:
            f.write(ini_content)
        
        print(f"📝 Wrote LDF cache config to {self.ldf_cache_ini}")

    def apply_ldf_cache(self, cache_data):
        """
        Restore full build environment from cache using real idedata.json structure.
        
        Args:
            cache_data (dict): LDF cache data from previous build
        Returns:
            bool: True if environment was restored, False otherwise
        """
        try:
            ldf_results = cache_data.get('ldf_results', {})
            if not ldf_results:
                print("⚠ No LDF results found in cache")
                return False
            
            print("🔧 Restoring full build environment from cache...")
            # No need to set env variables, as ldf_cache.ini will be included by PlatformIO
            # Only lib_ldf_mode will be set in platformio.ini by modify_platformio_ini()
            return True
            
        except Exception as e:
            print(f"✗ Error restoring environment: {e}")
            return False

    def save_ldf_cache(self, target=None, source=None, env_arg=None, **kwargs):
        """
        Read idedata.json and save LDF results for future builds as a Python dict,
        and write build options to ldf_cache.ini.
        
        Args:
            target: Build target (unused)
            source: Build source (unused) 
            env_arg: Environment argument (unused)
            **kwargs: Additional keyword arguments
        """
        try:
            # Generate project hash with detailed file tracking
            hash_details = self.get_project_hash_with_details()
            
            # Read LDF results from idedata.json
            ldf_results = self.read_existing_idedata()
            
            if ldf_results and ldf_results.get('lib_deps_entries'):
                # Write build configuration to ldf_cache.ini
                self.write_ldf_cache_ini(ldf_results)
                
                # Get PlatformIO version for cache validation
                pio_version = getattr(self.env, "PioVersion", lambda: "unknown")()
                
                # Prepare cache data structure
                cache_data = {
                    'ldf_results': ldf_results,
                    'project_hash': hash_details['final_hash'],
                    'hash_details': hash_details['file_hashes'],
                    'pioenv': str(self.env['PIOENV']),
                    'timestamp': datetime.datetime.now().isoformat(),
                    'pio_version': pio_version,
                    'ldf_cache_ini': self.ldf_cache_ini
                }
                
                # Add signature for integrity validation
                cache_data['signature'] = self.compute_signature(cache_data)
                
                # Ensure cache directory exists
                os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
                
                # Write cache as Python dict file
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    f.write("# LDF Cache - Complete Build Environment\n")
                    f.write("# Generated as Python dict\n\n")
                    f.write("cache_data = \\\n")
                    f.write(pprint.pformat(cache_data, indent=2, width=120))
                    f.write("\n")
                
                print(f"💾 LDF Cache saved successfully!")
            else:
                print("❌ No valid LDF results found in idedata.json")
                
        except Exception as e:
            print(f"✗ Error saving LDF cache: {e}")

    def load_and_validate_cache(self):
        """
        Load and validate cache with hash and signature from Python dict file.
        
        Returns:
            dict or None: Cache data if valid, None if invalid or non-existent
        """
        if not os.path.exists(self.cache_file):
            print("🔍 No cache file exists")
            return None
        
        try:
            # Load cache data from Python dict file
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_content = f.read()
            
            local_vars = {}
            exec(cache_content, {}, local_vars)
            cache_data = local_vars.get('cache_data')
            
            # Validate PlatformIO version
            current_pio_version = getattr(self.env, "PioVersion", lambda: "unknown")()
            if cache_data.get('pio_version') != current_pio_version:
                print(f"⚠ Cache invalid: PlatformIO version changed from {cache_data.get('pio_version')} to {current_pio_version}")
                clear_ldf_cache()
                return None
            
            # Validate cache signature
            expected_signature = cache_data.get('signature')
            actual_signature = self.compute_signature(cache_data)
            if expected_signature != actual_signature:
                print("⚠ Cache invalid: Signature mismatch. Possible file tampering or corruption.")
                clear_ldf_cache()
                return None
            
            # Validate environment name
            if cache_data.get('pioenv') != self.env['PIOENV']:
                print(f"🔄 Environment changed: {cache_data.get('pioenv')} -> {self.env['PIOENV']}")
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
        # Create a copy without the signature field
        data = dict(cache_data)
        data.pop('signature', None)
        
        try:
            # Try JSON serialization for consistent ordering
            raw = json.dumps(data, sort_keys=True, ensure_ascii=True, default=str)
        except Exception:
            # Fallback to repr if JSON fails
            raw = repr(data)
        
        return hashlib.sha256(raw.encode()).hexdigest()

    def setup_ldf_caching(self):
        """
        Orchestrate caching process with hash validation and LDF disabling.
        Main entry point for the LDF cache optimization system.
        """
        print("\n=== LDF Cache Optimizer (idedata.json Mode, Python dict cache, ldf_cache.ini) ===")
        
        # Try to load and validate existing cache
        cache_data = self.load_and_validate_cache()
        
        if cache_data:
            # Valid cache found - disable LDF and use cached results
            print("🚀 Valid cache found - disabling LDF")
            if self.modify_platformio_ini("off"):
                self.apply_ldf_cache(cache_data)
                # Schedule restoration of original LDF mode after build
                self.env.AddPostAction("checkprogsize", lambda *args: self.restore_platformio_ini())
        else:
            # No valid cache - run full LDF and save results
            print("🔄 No valid cache - running full LDF")
            # Schedule cache saving after build completion
            self.env.AddPostAction("checkprogsize", self.save_ldf_cache)
        
        print("=" * 60)

def clear_ldf_cache():
    """
    Delete LDF cache file for the current environment.
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
    Display cache information for the current environment.
    """
    project_dir = env.subst("$PROJECT_DIR")
    cache_file = os.path.join(project_dir, ".pio", "ldf_cache", f"ldf_cache_{env['PIOENV']}.py")
    
    if os.path.exists(cache_file):
        try:
            # Load and display cache information
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_content = f.read()
            
            local_vars = {}
            exec(cache_content, {}, local_vars)
            cache_data = local_vars.get('cache_data')
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
            print(f"Libsource dirs: {len(ldf_results.get('libsource_dirs', []))}")
            print("=" * 25)
            
        except Exception as e:
            print(f"Error reading cache: {e}")
    else:
        print("No LDF Cache present")

def show_ldf_config():
    """
    Display the generated LDF configuration (ldf_cache.ini).
    """
    project_dir = env.subst("$PROJECT_DIR")
    config_file = os.path.join(project_dir, "ldf_cache.ini")
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_content = f.read()
            
            print("\n=== ldf_cache.ini (LDF Cache Configuration) ===")
            print(config_content)
            print("=" * 40)
            
        except Exception as e:
            print(f"Error reading ldf_cache.ini: {e}")
    else:
        print("No ldf_cache.ini configuration found")

# Register PlatformIO aliases for cache management
env.AlwaysBuild(env.Alias("clear_ldf_cache", None, clear_ldf_cache))
env.AlwaysBuild(env.Alias("ldf_cache_info", None, show_ldf_cache_info))
env.AlwaysBuild(env.Alias("show_ldf_config", None, show_ldf_config))

# Initialize and setup LDF cache optimization
ldf_optimizer = LDFCacheOptimizer(env)
ldf_optimizer.setup_ldf_caching()
