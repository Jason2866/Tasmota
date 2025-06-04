# ldf_cache_env.py
"""
PlatformIO Advanced Script for full SCons Environment Caching.
This module optimizes build performance by saving and restoring the
entire SCons environment using SCons' native Dump/Restore methods.

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
    Full SCons Environment Cache for PlatformIO.

    This class dumps the entire SCons environment to a file after a successful build,
    and can restore all variables for future builds, enabling maximum reproducibility
    and performance for dependency-heavy projects.
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
        self.platformio_ini = os.path.join(self.project_dir, "platformio.ini")
        self.original_ldf_mode = None

    def save_env_cache(self, target=None, source=None, env_arg=None, **kwargs):
        """
        Save the full SCons environment to a file using SCons' native Dump().

        Args:
            target: SCons target (unused)
            source: SCons source (unused)
            env_arg: SCons environment (unused, uses self.env)
        """
        try:
            print("💾 Saving full SCons environment cache...")
            # Dump the entire environment in pretty Python dict format
            env_dump = self.env.Dump(format='pretty')
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                f.write("# SCons Environment Cache - Do not edit manually\n")
                f.write("# Generated automatically\n\n")
                f.write(env_dump)
            print(f"💾 SCons environment cache saved to {self.cache_file}")
        except Exception as e:
            print(f"✗ Error saving environment cache: {e}")

    def load_env_cache(self):
        """
        Load and restore the full SCons environment from cache if available.

        Returns:
            bool: True if cache was loaded and applied, False otherwise
        """
        if not os.path.exists(self.cache_file):
            print("🔍 No environment cache file exists")
            return False
        try:
            print(f"🔍 Loading SCons environment cache from {self.cache_file} ...")
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                env_dict = eval(f.read())
            # Restore all variables from the cached environment
            for k, v in env_dict.items():
                self.env[k] = v
            print("✅ SCons environment restored from cache.")
            return True
        except Exception as e:
            print(f"⚠ Error loading environment cache: {e}")
            return False

    def setup_env_caching(self):
        """
        Main logic for full SCons environment caching.

        On a cache hit, restores the entire environment before build.
        On a cache miss, sets up saving the environment after a successful build.
        """
        print("\n=== SCons Environment Cache Optimizer ===")
        cache_loaded = self.load_env_cache()
        if cache_loaded:
            print("🚀 Using full SCons environment cache for this build.")
        else:
            print("🔄 No environment cache found - will save after build.")
            # Save the environment after a successful build
            save_action = self.env.Action(self.save_env_cache)
            save_action.strfunction = lambda target, source, env: ''
            self.env.AddPostAction("checkprogsize", save_action)
        print("=" * 60)

# Cache management commands
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
                env_dict = eval(content.split('\n\n', 1)[1])
            print(f"\n=== SCons Environment Cache Info ===")
            print(f"Variables cached: {len(env_dict)}")
            print(f"File size: {os.path.getsize(cache_file)} bytes")
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
