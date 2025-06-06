"""
PlatformIO Advanced Script for intelligent LDF caching.

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

def smart_build_integrated():
    """
    Ensure idedata.json is generated for the current environment.
    """
    env_name = env.get("PIOENV")
    ldf_dat_dir = os.path.join(env.subst("$PROJECT_DIR"), ".ldf_dat")
    idedata_path = os.path.join(ldf_dat_dir, f"idedata_{env_name}.json")
    original_idedata_path = os.path.join(env.subst("$BUILD_DIR"), "idedata.json")

    if os.path.exists(original_idedata_path):
        os.makedirs(ldf_dat_dir, exist_ok=True)
        shutil.copy2(original_idedata_path, idedata_path)
        print(f"idedata.json copied to {idedata_path}")

    if os.environ.get("SMART_BUILD_RUNNING"):
        return

    if not os.path.exists(idedata_path) and not os.path.exists(original_idedata_path):
        print(f"idedata.json for {env_name} missing - running idedata build")
        env_copy = os.environ.copy()
        env_copy["SMART_BUILD_RUNNING"] = "1"
        try:
            subprocess.run([
                sys.executable, "-m", "platformio",
                "run", "-e", env_name, "-t", "idedata"
            ], cwd=env.subst("$PROJECT_DIR"), env=env_copy, check=True)
            if os.path.exists(original_idedata_path):
                os.makedirs(ldf_dat_dir, exist_ok=True)
                shutil.copy2(original_idedata_path, idedata_path)
                print(f"idedata.json copied to {idedata_path}")
            print("idedata build successful")
            Exit(0)
        except subprocess.CalledProcessError as e:
            print(f"idedata build failed: {e}")
            Exit(1)

smart_build_integrated()

class LDFCacheOptimizer:
    """
    PlatformIO LDF (Library Dependency Finder) cache optimizer.
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
        self.env = environment
        self.project_dir = self.env.subst("$PROJECT_DIR")
        self.src_dir = self.env.subst("$PROJECT_SRC_DIR")
        self.cache_file = os.path.join(self.project_dir, ".pio", "ldf_cache", f"ldf_cache_{self.env['PIOENV']}.py")
        self.ldf_cache_ini = os.path.join(self.project_dir, "ldf_cache.ini")
        self.platformio_ini = os.path.join(self.project_dir, "platformio.ini")
        self.platformio_ini_backup = os.path.join(self.project_dir, ".pio", f"platformio_backup_{self.env['PIOENV']}.ini")
        self.idedata_file = os.path.join(self.project_dir, ".ldf_dat", f"idedata_{self.env['PIOENV']}.json")
        self.ALL_RELEVANT_EXTENSIONS = self.HEADER_EXTENSIONS | self.SOURCE_EXTENSIONS | self.CONFIG_EXTENSIONS
        self.real_packages_dir = self.env.subst("$PLATFORMIO_PACKAGES_DIR")

    def create_ini_backup(self):
        """
        Create a backup of platformio.ini.
        """
        try:
            if os.path.exists(self.platformio_ini):
                os.makedirs(os.path.dirname(self.platformio_ini_backup), exist_ok=True)
                shutil.copy2(self.platformio_ini, self.platformio_ini_backup)
                print("🔒 platformio.ini backup created")
                return True
        except Exception as e:
            print(f"❌ Error creating backup: {e}")
        return False

    def restore_ini_from_backup(self):
        """
        Restore platformio.ini from backup.
        """
        try:
            if os.path.exists(self.platformio_ini_backup):
                shutil.copy2(self.platformio_ini_backup, self.platformio_ini)
                os.remove(self.platformio_ini_backup)
                print("🔓 platformio.ini restored from backup")
                return True
        except Exception as e:
            print(f"❌ Error restoring from backup: {e}")
        return False

    def modify_platformio_ini_simple(self, new_ldf_mode):
        """
        Modify lib_ldf_mode in platformio.ini
        """
        if not self.create_ini_backup():
            return False
        try:
            with open(self.platformio_ini, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            found = False
            for i, line in enumerate(lines):
                if 'lib_ldf_mode' in line.lower() and '=' in line:
                    # Replace only the value after '='
                    parts = line.split('=', 1)
                    lines[i] = parts[0] + '= ' + new_ldf_mode + '\n'
                    found = True
                    print(f"🔧 Modified lib_ldf_mode = {new_ldf_mode}")
                    break
            if not found:
                # Add to [platformio] section or create it
                section_found = False
                for i, line in enumerate(lines):
                    if line.strip().lower() == '[platformio]':
                        lines.insert(i + 1, f'lib_ldf_mode = {new_ldf_mode}\n')
                        section_found = True
                        print(f"🔧 Added lib_ldf_mode = {new_ldf_mode} to [platformio]")
                        break
                if not section_found:
                    # Add at the beginning if section doesn't exist
                    lines = [f'[platformio]\nlib_ldf_mode = {new_ldf_mode}\n\n'] + lines
                    print(f"🔧 Created [platformio] section with lib_ldf_mode = {new_ldf_mode}")
            with open(self.platformio_ini, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            return True
        except Exception as e:
            print(f"❌ Error modifying platformio.ini: {e}")
            self.restore_ini_from_backup()
            return False

    def resolve_pio_placeholders(self, path):
        """
        Replace '${platformio.packages_dir}' with the actual PlatformIO packages directory.
        """
        if not isinstance(path, str):
            return path
        return path.replace("${platformio.packages_dir}", self.real_packages_dir)

    def is_platformio_path(self, path):
        """
        Check if a path is within PlatformIO's own directories.
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
        Return a truncated SHA256 hash of a file's contents.
        """
        try:
            with open(file_path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()[:16]
        except (IOError, OSError, PermissionError):
            return "unreadable"

    def get_include_relevant_hash(self, file_path):
        """
        Calculate a hash based on relevant #include and #define lines in a source file.
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
        Scan all relevant project, library, and include files to produce a hash and metadata.
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
                        if file_ext in self.SOURCE_EXTENSIONS:
                            file_hash = self.get_include_relevant_hash(file_path)
                        elif file_ext in self.HEADER_EXTENSIONS:
                            file_hash = self._get_file_hash(file_path)
                        elif file_ext in self.CONFIG_EXTENSIONS:
                            file_hash = self._get_file_hash(file_path)
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

    def read_existing_idedata(self):
        """
        Read idedata.json and process its structure.
        """
        try:
            if not os.path.exists(self.idedata_file):
                print(f"❌ idedata.json not found: {self.idedata_file}")
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
        Process idedata.json structure and resolve all package placeholders.
        """
        ldf_cache = {
            'libraries': [],
            'include_paths': [],
            'defines': [],
            'build_flags': [],
            'lib_deps_entries': [],
            'libsource_dirs': [],
            'compiled_libraries': [],
            'compiled_objects': []
        }
        if not idedata:
            return ldf_cache
        libsource_dirs = idedata.get('libsource_dirs', [])
        for lib_dir in libsource_dirs:
            resolved_lib_dir = self.resolve_pio_placeholders(lib_dir)
            ldf_cache['libsource_dirs'].append(resolved_lib_dir)
            if 'lib/' in lib_dir and self.project_dir in lib_dir:
                lib_name = os.path.basename(lib_dir)
                lib_deps_entry = f"./lib/{lib_name}"
            elif 'framework-' in lib_dir:
                lib_deps_entry = lib_dir.replace(os.path.expanduser('~/.platformio/packages'), self.real_packages_dir)
            else:
                lib_deps_entry = resolved_lib_dir
            ldf_cache['lib_deps_entries'].append(lib_deps_entry)
            ldf_cache['libraries'].append({
                'name': os.path.basename(lib_dir),
                'path': resolved_lib_dir,
                'lib_deps_entry': lib_deps_entry
            })
        includes_build = idedata.get('includes', {}).get('build', [])
        for include_path in includes_build:
            ldf_cache['include_paths'].append(self.resolve_pio_placeholders(include_path))
        defines = idedata.get('defines', [])
        for define in defines:
            ldf_cache['defines'].append(define)
        cc_flags = idedata.get('cc_flags', [])
        cxx_flags = idedata.get('cxx_flags', [])
        all_flags = cc_flags + cxx_flags
        for flag in all_flags:
            resolved_flag = self.resolve_pio_placeholders(flag)
            if resolved_flag not in ldf_cache['build_flags']:
                ldf_cache['build_flags'].append(resolved_flag)
        build_dir = idedata.get('build_dir', '')
        if build_dir and os.path.exists(build_dir):
            lib_build_dir = os.path.join(build_dir, 'lib')
            if os.path.exists(lib_build_dir):
                for root, dirs, files in os.walk(lib_build_dir):
                    for file in files:
                        if file.endswith('.a'):
                            lib_path = os.path.join(root, file)
                            ldf_cache['compiled_libraries'].append(self.resolve_pio_placeholders(lib_path))
            for root, dirs, files in os.walk(build_dir):
                if '/src' in root.replace('\\', '/') or root.endswith('src'):
                    continue
                for file in files:
                    if file.endswith('.o'):
                        obj_path = os.path.join(root, file)
                        ldf_cache['compiled_objects'].append(self.resolve_pio_placeholders(obj_path))
        print(f"📦 Found {len(ldf_cache['compiled_libraries'])} .a files")
        print(f"📦 Found {len(ldf_cache['compiled_objects'])} .o files (excluding src)")
        return ldf_cache

    def compute_signature(self, cache_data):
        """
        Compute a hash signature for the cache data.
        """
        data = dict(cache_data)
        data.pop('signature', None)
        try:
            raw = json.dumps(data, sort_keys=True, ensure_ascii=True, default=str)
        except Exception:
            raw = repr(data)
        return hashlib.sha256(raw.encode()).hexdigest()

    def save_ldf_cache(self, target=None, source=None, env_arg=None, **kwargs):
        """
        Save the current LDF cache to disk after a successful build.
        """
        try:
            hash_details = self.get_project_hash_with_details()
            ldf_results = self.read_existing_idedata()
            if ldf_results and ldf_results.get('lib_deps_entries'):
                self.write_ldf_cache_ini(ldf_results)
                pio_version = getattr(self.env, "PioVersion", lambda: "unknown")()
                cache_data = {
                    'ldf_results': ldf_results,
                    'project_hash': hash_details['final_hash'],
                    'hash_details': hash_details['file_hashes'],
                    'pioenv': str(self.env['PIOENV']),
                    'timestamp': datetime.datetime.now().isoformat(),
                    'pio_version': pio_version,
                    'ldf_cache_ini': self.ldf_cache_ini
                }
                cache_data['signature'] = self.compute_signature(cache_data)
                os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    f.write("# LDF Cache - Complete Build Environment with .a/.o tracking\n")
                    f.write("# Generated as Python dict\n\n")
                    f.write("cache_data = \\\n")
                    f.write(pprint.pformat(cache_data, indent=2, width=120))
                    f.write("\n")
                print(f"💾 LDF Cache saved successfully!")
                print(f"   Libraries: {len(ldf_results.get('compiled_libraries', []))}")
                print(f"   Objects: {len(ldf_results.get('compiled_objects', []))}")
            else:
                print("❌ No valid LDF results found in idedata.json")
        except Exception as e:
            print(f"✗ Error saving LDF cache: {e}")
            import traceback
            traceback.print_exc()

    def load_and_validate_cache(self):
        """
        Load and validate the LDF cache. If invalid, clear it.
        """
        if not os.path.exists(self.cache_file):
            print("🔍 No cache file exists")
            return None
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_content = f.read()
            local_vars = {}
            exec(cache_content, {}, local_vars)
            cache_data = local_vars.get('cache_data')
            current_pio_version = getattr(self.env, "PioVersion", lambda: "unknown")()
            if cache_data.get('pio_version') != current_pio_version:
                print(f"⚠ Cache invalid: PlatformIO version changed from {cache_data.get('pio_version')} to {current_pio_version}")
                clear_ldf_cache()
                return None
            expected_signature = cache_data.get('signature')
            actual_signature = self.compute_signature(cache_data)
            if expected_signature != actual_signature:
                print("⚠ Cache invalid: Signature mismatch. Possible file tampering or corruption.")
                clear_ldf_cache()
                return None
            if cache_data.get('pioenv') != self.env['PIOENV']:
                print(f"🔄 Environment changed: {cache_data.get('pioenv')} -> {self.env['PIOENV']}")
                clear_ldf_cache()
                return None
            ldf_results = cache_data.get('ldf_results', {})
            missing_artifacts = []
            for lib_path in ldf_results.get('compiled_libraries', []):
                resolved_lib_path = self.resolve_pio_placeholders(lib_path)
                if not os.path.exists(resolved_lib_path):
                    missing_artifacts.append(resolved_lib_path)
            for obj_path in ldf_results.get('compiled_objects', []):
                resolved_obj_path = self.resolve_pio_placeholders(obj_path)
                if not os.path.exists(resolved_obj_path):
                    missing_artifacts.append(resolved_obj_path)
            if missing_artifacts:
                print(f"⚠ Cache invalid: {len(missing_artifacts)} build artifacts missing")
                print(f"   First missing: {missing_artifacts[0]}")
                clear_ldf_cache()
                return None
            print("✅ Cache valid - all build artifacts present")
            print(f"   Libraries: {len(ldf_results.get('compiled_libraries', []))}")
            print(f"   Objects: {len(ldf_results.get('compiled_objects', []))}")
            return cache_data
        except Exception as e:
            print(f"⚠ Cache validation failed: {e}")
            clear_ldf_cache()
            return None

    def write_ldf_cache_ini(self, ldf_results):
        """
        Write LDF cache configuration to ldf_cache.ini for PlatformIO extra_configs.
        """
        ini_lines = [
            f"[env:{self.env['PIOENV']}]",
            "lib_deps ="
        ]
        for lib_dep in ldf_results['lib_deps_entries']:
            ini_lines.append(f"    {lib_dep}")
        ini_lines.append("")
        ini_lines.append("build_flags =")
        for flag in ldf_results['build_flags']:
            ini_lines.append(f"    {flag}")
        for include_path in ldf_results['include_paths']:
            ini_lines.append(f"    -I\"{include_path}\"")
        for define in ldf_results['defines']:
            ini_lines.append(f"    -D{define}")
        ini_content = "\n".join(ini_lines)
        with open(self.ldf_cache_ini, "w", encoding="utf-8") as f:
            f.write(ini_content)
        print(f"📝 Wrote LDF cache config to {self.ldf_cache_ini}")

    def apply_ldf_cache_complete(self, cache_data):
        """
        Apply all cached LDF results to the SCons environment, resolving all placeholders.
        """
        try:
            ldf_results = cache_data.get('ldf_results', {})
            if not ldf_results:
                return False
            print("🔧 Restoring complete SCons environment from cache...")
            self._apply_library_paths(ldf_results)
            self._apply_static_libraries(ldf_results)
            self._apply_object_files_as_static_library(ldf_results)
            self._apply_include_paths_and_defines(ldf_results)
            self._apply_build_flags_systematically(ldf_results)
            print("✅ Complete SCons environment restored from cache")
            return True
        except Exception as e:
            print(f"✗ Error in complete cache restoration: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _apply_library_paths(self, ldf_results):
        """
        Add all library directories to LIBPATH, resolving any placeholders.
        """
        libsource_dirs = [self.resolve_pio_placeholders(p) for p in ldf_results.get('libsource_dirs', [])]
        compiled_libraries = [self.resolve_pio_placeholders(p) for p in ldf_results.get('compiled_libraries', [])]
        lib_dirs_from_files = set()
        for lib_path in compiled_libraries:
            if os.path.exists(lib_path):
                lib_dirs_from_files.add(os.path.dirname(lib_path))
        all_lib_paths = set(libsource_dirs) | lib_dirs_from_files
        valid_libpaths = [path for path in all_lib_paths if os.path.exists(path)]
        if valid_libpaths:
            existing_libpaths = [str(p) for p in self.env.get('LIBPATH', [])]
            new_libpaths = [p for p in valid_libpaths if p not in existing_libpaths]
            if new_libpaths:
                self.env.Append(LIBPATH=new_libpaths)
                print(f"   Added {len(new_libpaths)} library paths to LIBPATH")
                for path in new_libpaths[:3]:
                    print(f"     -> {path}")
            else:
                print("   All library paths already present in LIBPATH")

    def _apply_static_libraries(self, ldf_results):
        """
        Add all static libraries (.a) to LIBS, resolving any placeholders.
        """
        compiled_libraries = [self.resolve_pio_placeholders(p) for p in ldf_results.get('compiled_libraries', [])]
        valid_libs = []
        for lib_path in compiled_libraries:
            if os.path.exists(lib_path):
                lib_name = os.path.basename(lib_path)
                if lib_name.startswith('lib') and lib_name.endswith('.a'):
                    clean_name = lib_name[3:-2]
                    valid_libs.append(clean_name)
                else:
                    valid_libs.append(lib_path)
        if valid_libs:
            self.env.Append(LIBS=valid_libs)
            print(f"   Added {len(valid_libs)} static libraries to LIBS")

    def _apply_object_files_as_static_library(self, ldf_results):
        """
        Bundle all object files into a temporary static library and add to LIBS.
        """
        compiled_objects = [self.resolve_pio_placeholders(p) for p in ldf_results.get('compiled_objects', [])]
        valid_objects = [obj for obj in compiled_objects if os.path.exists(obj)]
        if not valid_objects:
            print("   No valid object files found")
            return
        content_hash = hashlib.md5()
        for obj_path in sorted(valid_objects):
            try:
                content_hash.update(obj_path.encode())
                content_hash.update(str(os.path.getmtime(obj_path)).encode())
                content_hash.update(str(os.path.getsize(obj_path)).encode())
            except OSError:
                continue
        lib_hash = content_hash.hexdigest()[:12]
        temp_lib_name = f"ldf_cache_{self.env['PIOENV']}_{lib_hash}"
        temp_lib_dir = os.path.join(self.env.subst("$BUILD_DIR"), "lib_cache")
        temp_lib_target = os.path.join(temp_lib_dir, temp_lib_name)
        os.makedirs(temp_lib_dir, exist_ok=True)
        temp_lib_file = temp_lib_target + ".a"
        if os.path.exists(temp_lib_file):
            lib_mtime = os.path.getmtime(temp_lib_file)
            objects_newer = any(os.path.getmtime(obj) > lib_mtime
                               for obj in valid_objects if os.path.exists(obj))
            if not objects_newer:
                self.env.Append(LIBS=[os.path.basename(temp_lib_name)])
                if temp_lib_dir not in [str(p) for p in self.env.get('LIBPATH', [])]:
                    self.env.Append(LIBPATH=[temp_lib_dir])
                print(f"   Reused cached object library: {temp_lib_name}.a")
                return
        print(f"   Creating static library from {len(valid_objects)} object files: {temp_lib_name}.a")
        try:
            temp_lib = self.env.StaticLibrary(
                target=temp_lib_target,
                source=valid_objects
            )
            self.env.Append(LIBS=[temp_lib_name])
            if temp_lib_dir not in [str(p) for p in self.env.get('LIBPATH', [])]:
                self.env.Append(LIBPATH=[temp_lib_dir])
            print(f"   Successfully created and linked object library")
        except Exception as e:
            print(f"   Warning: StaticLibrary creation failed: {e}")
            self.env.Append(OBJECTS=valid_objects)
            print(f"   Fallback: Added {len(valid_objects)} objects directly")

    def _apply_build_flags_systematically(self, ldf_results):
        """
        Systematically apply build flags to the SCons environment, resolving any placeholders.
        """
        build_flags = [self.resolve_pio_placeholders(flag) for flag in ldf_results.get('build_flags', [])]
        if not build_flags:
            return
        cc_flags = []
        cxx_flags = []
        link_flags = []
        cpp_defines = []
        cpp_paths = []
        lib_paths = []
        for flag in build_flags:
            flag = flag.strip()
            if not flag:
                continue
            if flag.startswith('-I'):
                inc_path = flag[2:].strip('"\'')
                if os.path.exists(inc_path):
                    cpp_paths.append(inc_path)
            elif flag.startswith('-D'):
                define = flag[2:]
                cpp_defines.append(define)
            elif flag.startswith('-L'):
                lib_path = flag[2:].strip('"\'')
                if os.path.exists(lib_path):
                    lib_paths.append(lib_path)
            elif flag.startswith('-l'):
                lib_name = flag[2:]
                existing_libs = self.env.get('LIBS', [])
                if lib_name not in existing_libs:
                    self.env.Append(LIBS=[lib_name])
            elif flag in ['-shared', '-static', '-Wl,', '-T'] or flag.startswith('-Wl,'):
                link_flags.append(flag)
            elif flag.startswith('-f') or flag.startswith('-m') or flag in ['-g', '-O0', '-O1', '-O2', '-O3', '-Os']:
                cc_flags.append(flag)
                cxx_flags.append(flag)
            elif flag.startswith('-W'):
                cc_flags.append(flag)
                cxx_flags.append(flag)
            else:
                cc_flags.append(flag)
        if cpp_paths:
            existing_paths = [str(p) for p in self.env.get('CPPPATH', [])]
            new_paths = [p for p in cpp_paths if p not in existing_paths]
            if new_paths:
                self.env.Append(CPPPATH=new_paths)
                print(f"   Added {len(new_paths)} include paths from build flags")
        if cpp_defines:
            self.env.Append(CPPDEFINES=cpp_defines)
            print(f"   Added {len(cpp_defines)} defines from build flags")
        if lib_paths:
            existing_libpaths = [str(p) for p in self.env.get('LIBPATH', [])]
            new_libpaths = [p for p in lib_paths if p not in existing_libpaths]
            if new_libpaths:
                self.env.Append(LIBPATH=new_libpaths)
                print(f"   Added {len(new_libpaths)} library paths from build flags")
        if cc_flags:
            self.env.Append(CCFLAGS=cc_flags)
            print(f"   Added {len(cc_flags)} C compiler flags")
        if cxx_flags:
            self.env.Append(CXXFLAGS=cxx_flags)
            print(f"   Added {len(cxx_flags)} C++ compiler flags")
        if link_flags:
            self.env.Append(LINKFLAGS=link_flags)
            print(f"   Added {len(link_flags)} linker flags")

    def _apply_include_paths_and_defines(self, ldf_results):
        """
        Add all include paths and defines to the SCons environment, resolving any placeholders.
        """
        include_paths = [self.resolve_pio_placeholders(p) for p in ldf_results.get('include_paths', [])]
        if include_paths:
            existing_includes = [str(path) for path in self.env.get('CPPPATH', [])]
            new_includes = [inc for inc in include_paths
                           if os.path.exists(inc) and inc not in existing_includes]
            if new_includes:
                self.env.Append(CPPPATH=new_includes)
                print(f"   Added {len(new_includes)} include paths")
        defines = ldf_results.get('defines', [])
        if defines:
            existing_defines = [str(d) for d in self.env.get('CPPDEFINES', [])]
            new_defines = [d for d in defines if str(d) not in existing_defines]
            if new_defines:
                self.env.Append(CPPDEFINES=new_defines)
                print(f"   Added {len(new_defines)} preprocessor defines")

    def setup_ldf_caching(self):
        """
        Main entry point using backup/restore for platformio.ini.
        """
        print("\n=== LDF Cache Optimizer ===")
        cache_data = self.load_and_validate_cache()
        if cache_data:
            print("🚀 Valid cache found - disabling LDF with backup/restore")
            if self.modify_platformio_ini_simple("off") and self.apply_ldf_cache_complete(cache_data):
                print("✅ SCons environment restored from cache")
                # Restore platformio.ini after build
                self.env.AddPostAction("checkprogsize", lambda *args: self.restore_ini_from_backup())
            else:
                print("❌ Cache application failed - falling back to full LDF")
                self.restore_ini_from_backup()
                self.env.AddPostAction("checkprogsize", self.save_ldf_cache)
        else:
            print("🔄 No valid cache - running full LDF")
            self.env.AddPostAction("checkprogsize", self.save_ldf_cache)
        print("=" * 80)

def clear_ldf_cache():
    """
    Delete the LDF cache file for the current environment.
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
    Print information about the current LDF cache.
    """
    project_dir = env.subst("$PROJECT_DIR")
    cache_file = os.path.join(project_dir, ".pio", "ldf_cache", f"ldf_cache_{env['PIOENV']}.py")
    if os.path.exists(cache_file):
        try:
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
            print(f"Compiled .a:  {len(ldf_results.get('compiled_libraries', []))}")
            print(f"Compiled .o:  {len(ldf_results.get('compiled_objects', []))}")
            print("===")
        except Exception as e:
            print(f"✗ Error reading cache info: {e}")
    else:
        print("ℹ No LDF Cache present")

ldf_optimizer = LDFCacheOptimizer(env)
ldf_optimizer.setup_ldf_caching()
