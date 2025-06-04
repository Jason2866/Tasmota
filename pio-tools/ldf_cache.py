# ldf_cache.py
"""
PlatformIO Advanced Script for intelligent LDF caching with full environment dump.
This module optimizes build performance through selective LDF caching and restoring
using SCons native serialization and smart cache invalidation.

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
    with smart hash-based cache invalidation.
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
        """Generate SHA256 hash of a file's content."""
        # ... (identical to your original implementation) ...

    def get_include_relevant_hash(self, file_path):
        """Generate hash from include-relevant lines only."""
        # ... (identical to your original implementation) ...

    def is_platformio_path(self, path):
        """Check if path belongs to PlatformIO installation."""
        # ... (identical to your original implementation) ...

    def get_project_hash_with_details(self):
        """Generate detailed project hash with file tracking."""
        # ... (identical to your original implementation) ...

    def compare_hash_details(self, current_hashes, cached_hashes):
        """Show differences between current and cached file hashes."""
        # ... (identical to your original implementation) ...

    # ------------------- Enhanced Cache Validation ----------------------------
    
    def load_and_validate_cache(self):
        """Load and validate cache with smart hash comparison."""
        if not os.path.exists(self.cache_file):
            print("🔍 No cache file exists")
            return None
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_content = f.read()
            cache_data = eval(cache_content.split('\n\n', 1)[1])
            
            # Environment check
            if cache_data.get('pioenv') != self.env['PIOENV']:
                print(f"🔄 Environment changed: {cache_data.get('pioenv')} -> {self.env['PIOENV']}")
                return None

            # Detailed hash comparison
            print("🔍 Comparing hashes (showing only differences)...")
            current_hash_details = self.get_project_hash_with_details()
            
            if cache_data.get('project_hash') != current_hash_details['final_hash']:
                print("\n🔄 Project files changed:")
                self.compare_hash_details(current_hash_details['file_hashes'], cache_data.get('hash_details', {}))
                return None

            print("✅ No include-relevant changes - cache valid")
            return cache_data
            
        except Exception as e:
            print(f"⚠ Cache validation failed: {e}")
            return None

    # ------------------- SCons Environment Handling ---------------------------
    
    def apply_ldf_cache(self, cache_data):
        """Restore full SCons environment from cache."""
        try:
            scons_vars = eval(cache_data['scons_dump'])
            print("🔧 Restoring full SCons environment...")
            
            # Restore all variables from the cached environment
            for var_name, var_value in scons_vars.items():
                self.env[var_name] = var_value
                
            print(f"📦 Restored {len(scons_vars)} SCons variables")
            return True
        except Exception as e:
            print(f"✗ Error restoring environment: {e}")
            return False

    def save_ldf_cache(self, target=None, source=None, env_arg=None, **kwargs):
        """Save full SCons environment with validation data."""
        try:
            hash_details = self.get_project_hash_with_details()
            env_dump = self.env.Dump(format='pretty')
            
            cache_data = {
                'scons_dump': env_dump,
                'project_hash': hash_details['final_hash'],
                'hash_details': hash_details['file_hashes'],
                'pioenv': str(self.env['PIOENV']),
                'timestamp': datetime.datetime.now().isoformat(),
                'performance': hash_details.get('performance', {})
            }
            
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                f.write("# LDF Cache - Full SCons Environment\n")
                f.write("# Generated automatically\n\n")
                f.write(repr(cache_data))
                
            print(f"💾 Saved full environment cache ({len(cache_data['scons_dump'])} bytes)")
        except Exception as e:
            print(f"✗ Error saving cache: {e}")

    # ------------------- Main Logic --------------------------------------------
    
    def setup_ldf_caching(self):
        """Orchestrate caching process with smart invalidation."""
        print("\n=== LDF Cache Optimizer (Enhanced Validation) ===")
        
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
    """Delete LDF cache file."""
    cache_file = os.path.join(env.subst("$BUILD_DIR"), "ldf_cache_sconsdump.py")
    if os.path.exists(cache_file):
        try:
            os.remove(cache_file)
            print("✓ LDF Cache deleted")
        except Exception as e:
            print(f"✗ Error deleting cache: {e}")
    else:
        print("ℹ No LDF Cache present")

def show_ldf_cache_info():
    """Display cache information."""
    cache_file = os.path.join(env.subst("$BUILD_DIR"), "ldf_cache_sconsdump.py")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = eval(f.read().split('\n\n', 1)[1])
            print("\n=== LDF Cache Info ===")
            print(f"Environment:  {cache_data.get('pioenv', 'unknown')}")
            print(f"Project hash: {cache_data.get('project_hash', 'unknown')}")
            print(f"Created:      {cache_data.get('timestamp', 'unknown')}")
            print(f"File size:    {os.path.getsize(cache_file)} bytes")
            print("=" * 25)
        except Exception as e:
            print(f"Error reading cache: {e}")
    else:
        print("No LDF Cache present")

# Register custom targets
env.AlwaysBuild(env.Alias("clear_ldf_cache", None, clear_ldf_cache))
env.AlwaysBuild(env.Alias("ldf_cache_info", None, show_ldf_cache_info))

# Initialize and run
ldf_optimizer = LDFCacheOptimizer(env)
ldf_optimizer.setup_ldf_caching()
