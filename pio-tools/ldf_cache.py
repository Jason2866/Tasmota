# ldf_cache_env.py
"""
PlatformIO Advanced Script for full SCons Environment Caching with Cache Invalidation.
This module optimizes build performance by saving and restoring the
entire SCons environment, disables LDF when using the cache, and
automatically invalidates the cache if the project or environment changes.

Copyright: Jason2866
"""

Import("env")
import os
import hashlib
import datetime
import time
import re
from platformio.project.config import ProjectConfig

class SConsEnvCache:
    """
    Full SCons Environment Cache for PlatformIO with automatic cache invalidation.

    This class dumps the entire SCons environment to a file after a successful build,
    and can restore all variables for future builds, enabling maximum reproducibility
    and performance for dependency-heavy projects. It also manages lib_ldf_mode and
    automatically invalidates the cache if the project or environment changes.
    """

    def __init__(self, environment):
        """
        Initialize the SConsEnvCache.

        Args:
            environment: PlatformIO SCons environment object
        """
        self.env = environment
        self.cache_file = os.path.join(self.env.subst("$BUILD_DIR"), "ldf_env_cache.py")
        self.project_dir = self.env.subst("$PROJECT_DIR")
        self.src_dir = self.env.subst("$PROJECT_SRC_DIR")
        self.platformio_ini = os.path.join(self.project_dir, "platformio.ini")
        self.original_ldf_mode = None

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

    def get_project_hash(self):
        """
        Compute a hash of the project that reflects all include-relevant files.

        Returns:
            str: SHA256 hash (first 16 chars) of project state
        """
        hash_data = []
        # Hash platformio.ini (excluding lib_ldf_mode)
        if os.path.exists(self.platformio_ini):
            try:
                with open(self.platformio_ini, 'r', encoding='utf-8') as f:
                    ini_content = f.read()
                filtered_content = re.sub(r'lib_ldf_mode\s*=\s*\w+\n?', '', ini_content)
                hash_data.append(filtered_content)
            except Exception as e:
                print(f"⚠ Error reading platformio.ini: {e}")
        # Hash all source and config files (recursively)
        for root, dirs, files in os.walk(self.project_dir):
            dirs[:] = [d for d in dirs if d not in ['.pio', '.git', 'build', 'data', '__pycache__']]
            for file in files:
                if file.endswith(('.c', '.cpp', '.h', '.hpp', '.ino', '.json', '.ini')):
                    try:
                        with open(os.path.join(root, file), 'rb') as f:
                            hash_data.append(f.read())
                    except Exception:
                        continue
        return hashlib.sha256(b''.join(hash_data)).hexdigest()[:16]

    def save_env_cache(self, target=None, source=None, env_arg=None, **kwargs):
        """
        Save the full SCons environment to a file using SCons' native Dump().
        Also save the current project hash and environment for cache validation.
        """
        try:
            print("💾 Saving full SCons environment cache...")
            env_dump = self.env.Dump(format='pretty')
            project_hash = self.get_project_hash()
            cache_data = {
                'env_dump': env_dump,
                'project_hash': project_hash,
                'pioenv': str(self.env['PIOENV']),
                'timestamp': datetime.datetime.now().isoformat(),
            }
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                f.write("# SCons Environment Cache - Do not edit manually\n")
                f.write("# Generated automatically\n\n")
                f.write(repr(cache_data))
            print(f"💾 SCons environment cache saved to {self.cache_file}")
        except Exception as e:
            print(f"✗ Error saving environment cache: {e}")

    def load_env_cache(self):
        """
        Load and restore the full SCons environment from cache if available and valid.

        Returns:
            bool: True if cache was loaded and applied, False otherwise
        """
        if not os.path.exists(self.cache_file):
            print("🔍 No environment cache file exists")
            return False
        try:
            print(f"🔍 Loading SCons environment cache from {self.cache_file} ...")
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = eval(f.read())
            # Validate cache
            current_hash = self.get_project_hash()
            current_env = str(self.env['PIOENV'])
            if not self.is_cache_valid(cache_data, current_env, current_hash):
                print("⚠ Cache invalid, will not use cached environment.")
                return False
            # Restore all variables from the cached environment
            env_dict = eval(cache_data['env_dump'])
            for k, v in env_dict.items():
                self.env[k] = v
            print("✅ SCons environment restored from cache.")
            return True
        except Exception as e:
            print(f"⚠ Error loading environment cache: {e}")
            return False

    def is_cache_valid(self, cache_data, current_env, current_hash):
        """
        Check if the cache is still valid based on environment and project hash.

        Args:
            cache_data (dict): Cached data containing 'pioenv' and 'project_hash'
            current_env (str): Current environment name
            current_hash (str): Current project hash
        Returns:
            bool: True if cache is valid, False otherwise
        """
        if not cache_data:
            return False
        if cache_data.get('pioenv') != current_env:
            print(f"Cache invalid: environment changed from {cache_data.get('pioenv')} to {current_env}")
            return False
        if cache_data.get('project_hash') != current_hash:
            print(f"Cache invalid: project hash changed from {cache_data.get('project_hash')} to {current_hash}")
            return False
        return True

    def setup_env_caching(self):
        """
        Main logic for full SCons environment caching and LDF disabling.

        On a cache hit, disables LDF and restores the environment before build.
        On a cache miss, sets up saving the environment after a successful build.
        """
        print("\n=== SCons Environment Cache Optimizer ===")
        cache_loaded = self.load_env_cache()
        if cache_loaded:
            # Disable LDF for this build (must be done before dependency scan!)
            print("🚀 Using full SCons environment cache for this build. Disabling LDF.")
            self.modify_platformio_ini("off")
            # Restore original ini after build
            restore_action = self.env.Action(lambda t, s, e: self.restore_platformio_ini())
            restore_action.strfunction = lambda target, source, env: ''
            self.env.AddPostAction("checkprogsize", restore_action)
        else:
            print("🔄 No valid environment cache found - will save after build.")
            # Save the environment after a successful build
            save_action = self.env.Action(self.save_env_cache)
            save_action.strfunction = lambda target, source, env: ''
            self.env.AddPostAction("checkprogsize", save_action)
        print("=" * 60)

def clear_env_cache():
    """
    Delete the SCons environment cache file.
    """
    cache_file = os.path.join(env.subst("$BUILD_DIR"), "ldf_env_cache.py")
    if os.path.exists(cache_file):
        try:
            os.remove(cache_file)
            print("✓ SCons environment cache deleted")
        except (IOError, OSError, PermissionError) as e:
            print(f"✗ Error deleting cache: {e}")
    else:
        print("ℹ No environment cache present")

def show_env_cache_info():
    """
    Display information about the cached SCons environment.
    """
    cache_file = os.path.join(env.subst("$BUILD_DIR"), "ldf_env_cache.py")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                content = f.read()
                cache_data = eval(content.split('\n\n', 1)[1])
            print(f"\n=== SCons Environment Cache Info ===")
            print(f"Environment:  {cache_data.get('pioenv', 'unknown')}")
            print(f"Project hash: {cache_data.get('project_hash', 'unknown')}")
            print(f"Timestamp:    {cache_data.get('timestamp', 'unknown')}")
            print(f"File size:    {os.path.getsize(cache_file)} bytes")
            print("=" * 25)
        except Exception as e:
            print(f"Error reading cache info: {e}")
    else:
        print("No environment cache present")

def force_env_rebuild():
    """
    Force a rebuild by clearing the environment cache.
    """
    clear_env_cache()
    print("SCons environment will be rebuilt on next build")

# Register custom targets for cache management
env.AlwaysBuild(env.Alias("clear_env_cache", None, clear_env_cache))
env.AlwaysBuild(env.Alias("env_cache_info", None, show_env_cache_info))
env.AlwaysBuild(env.Alias("force_env_rebuild", None, force_env_rebuild))

# Initialize and run SConsEnvCache
env_cache = SConsEnvCache(env)
env_cache.setup_env_caching()
