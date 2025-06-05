# ldf_cache.py
"""
PlatformIO Advanced Script for intelligent LDF caching using idedata.json.
This script ensures idedata.json is always generated (when a real build is requested)
by adding the 'idedata' target to the build, then reads and caches LDF results
for fast subsequent builds.

Copyright: Jason2866
"""

Import("env")

# --- Ensure idedata.json is generated only when a real build is requested ---

real_targets = {"buildprog", "all", "program", "upload", "checkprogsize", "size"}
if any(t in COMMAND_LINE_TARGETS for t in real_targets):
    if "idedata" not in COMMAND_LINE_TARGETS:
        COMMAND_LINE_TARGETS.append("idedata")
        print("🔧 [LDF-Cache] Added 'idedata' to build targets")
else:
    print("⚠️ [LDF-Cache] No real build target found, not adding 'idedata'")

import os
import hashlib
import datetime
import re
import json
from platformio.project.config import ProjectConfig

class LDFCacheOptimizer:
    """
    PlatformIO LDF (Library Dependency Finder) cache optimizer.

    Reads LDF results from idedata.json and converts them to reusable configuration,
    allowing subsequent builds to bypass LDF entirely.
    """

    def __init__(self, environment):
        """
        Initialize the LDF Cache Optimizer.

        Args:
            environment: PlatformIO SCons environment object
        """
        self.env = environment
        self.project_dir = self.env.subst("$PROJECT_DIR")
        self.cache_file = os.path.join(self.project_dir, ".pio", "ldf_cache", f"ldf_cache_{self.env['PIOENV']}.py")
        self.platformio_ini = os.path.join(self.project_dir, "platformio.ini")
        self.idedata_file = os.path.join(self.project_dir, ".pio", "build", self.env['PIOENV'], "idedata.json")
        self.original_ldf_mode = None

    # --- PlatformIO.ini Modification Methods ---

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

    # --- LDF Results Extraction from idedata.json ---

    def read_existing_idedata(self):
        """
        Read and process idedata.json using the real PlatformIO structure.
        Returns:
            dict: LDF cache data extracted from idedata.json
        """
        try:
            if not os.path.exists(self.idedata_file):
                print(f"❌ idedata.json not found: {self.idedata_file}")
                print("   This should never happen if 'idedata' target is active!")
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
            # Convert to lib_deps entry
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

    def generate_complete_platformio_config(self, ldf_results):
        """
        Generate a complete platformio.ini section based on real LDF results.
        Args:
            ldf_results (dict): LDF cache data
        Returns:
            str: Path to the generated INI file
        """
        config_lines = [
            f"# Complete LDF Cache Configuration for {self.env['PIOENV']}",
            f"# Generated: {datetime.datetime.now().isoformat()}",
            f"# Based on REAL idedata.json structure",
            f"# Copy this to your [env:{self.env['PIOENV']}] section",
            "",
            "lib_ldf_mode = off",
            "lib_deps = "
        ]
        for lib_deps_entry in ldf_results['lib_deps_entries']:
            config_lines.append(f"    {lib_deps_entry}")
        config_lines.append("")
        config_lines.append("build_flags = ")
        for include_path in ldf_results['include_paths']:
            config_lines.append(f"    -I\"{include_path}\"")
        for define in ldf_results['defines']:
            config_lines.append(f"    -D{define}")
        for flag in ldf_results['build_flags']:
            if not flag.startswith('-I'):
                config_lines.append(f"    {flag}")
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
            lib_deps = ldf_results.get('lib_deps_entries', [])
            if lib_deps:
                self.env['LIB_DEPS'] = lib_deps
                print(f"📚 Restored {len(lib_deps)} library dependencies")
            include_paths = ldf_results.get('include_paths', [])
            if include_paths:
                self.env.Append(CPPPATH=include_paths)
                print(f"📂 Restored {len(include_paths)} include paths")
            defines = ldf_results.get('defines', [])
            if defines:
                self.env.Append(CPPDEFINES=defines)
                print(f"🔧 Restored {len(defines)} preprocessor defines")
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
        Read idedata.json and save LDF results for future builds.
        """
        try:
            hash_details = self.get_project_hash_with_details()
            ldf_results = self.read_existing_idedata()
            if ldf_results and ldf_results.get('lib_deps_entries'):
                config_file = self.generate_complete_platformio_config(ldf_results)
                pio_version = getattr(self.env, "PioVersion", lambda: "unknown")()
                cache_data = {
                    'ldf_results': ldf_results,
                    'project_hash': hash_details['final_hash'],
                    'hash_details': hash_details['file_hashes'],
                    'pioenv': str(self.env['PIOENV']),
                    'timestamp': datetime.datetime.now().isoformat(),
                    'pio_version': pio_version,
                    'config_file': config_file
                }
                cache_data['signature'] = self.compute_signature(cache_data)
                os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    f.write("# LDF Cache - Complete Build Environment\n")
                    f.write("# Generated from REAL idedata.json structure\n\n")
                    f.write("import json\n\n")
                    f.write("cache_json = '''\n")
                    f.write(json.dumps(cache_data, ensure_ascii=False, indent=2, default=str))
                    f.write("\n'''\n\n")
                    f.write("cache_data = json.loads(cache_json)\n")
                print(f"💾 LDF Cache saved successfully!")
            else:
                print("❌ No valid LDF results found in idedata.json")
        except Exception as e:
            print(f"✗ Error saving LDF cache: {e}")

    def get_project_hash_with_details(self):
        """
        Generate a hash of the project for cache validation.
        Returns:
            dict: Hash details
        """
        hash_data = []
        if os.path.exists(self.platformio_ini):
            with open(self.platformio_ini, 'rb') as f:
                hash_data.append(hashlib.sha256(f.read()).hexdigest())
        src_dir = self.env.subst("$PROJECT_SRC_DIR")
        for root, dirs, files in os.walk(src_dir):
            for fname in files:
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, 'rb') as f:
                        hash_data.append(hashlib.sha256(f.read()).hexdigest())
                except Exception:
                    pass
        final_hash = hashlib.sha256(''.join(hash_data).encode()).hexdigest()[:16]
        return {'final_hash': final_hash, 'file_hashes': {}}

    def load_and_validate_cache(self):
        """
        Load and validate cache with hash and signature.
        Returns:
            dict or None: Cache data if valid, None if invalid or non-existent
        """
        if not os.path.exists(self.cache_file):
            print("🔍 No cache file exists")
            return None
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_content = f.read()
            if 'cache_json' in cache_content:
                exec(cache_content)
                cache_data = locals()['cache_data']
            else:
                cache_data = eval(cache_content.split('\n\n', 1)[1])
            expected_signature = cache_data.get('signature')
            actual_signature = self.compute_signature(cache_data)
            if expected_signature != actual_signature:
                print("⚠ Cache invalid: Signature mismatch.")
                clear_ldf_cache()
                return None
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
        data = dict(cache_data)
        data.pop('signature', None)
        raw = repr(data).encode()
        return hashlib.sha256(raw).hexdigest()

    # --- Main Logic ---

    def setup_ldf_caching(self):
        """
        Orchestrate caching process with hash validation and LDF disabling.
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

# --- Cache Management Commands ---

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
            print(f"Libsource dirs: {len(ldf_results.get('libsource_dirs', []))}")
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
