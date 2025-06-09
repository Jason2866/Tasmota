"""
PlatformIO Advanced Script for intelligent LDF caching with build order management.

This script ensures compile_commands.json exists before the main build starts.
If not, it creates it using log2compdb, saves the LDF cache, and exits.
The user must then rerun the build manually.
"""

import os
import hashlib
import time
import datetime
import re
import pprint
import json
import shutil
import subprocess
import sys
import tempfile
from platformio.project.config import ProjectConfig

class LDFCacheOptimizer:
    """
    PlatformIO LDF (Library Dependency Finder) cache optimizer with build order management.
    Designed specifically for lib_ldf_mode = chain and off modes.
    Invalidates cache only when #include directives change in source files.
    Includes complete build order management for correct linking.
    Implements a two-run strategy:
    1. First run: LDF active, create comprehensive cache
    2. Second run: LDF off, use cache for all dependencies (user-initiated)
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
        Initialize the LDF cache optimizer with build order management.
        
        Args:
            environment: PlatformIO SCons environment
        """
        self.env = environment
        self.env_name = self.env.get("PIOENV")
        self.project_dir = self.env.subst("$PROJECT_DIR")
        self.src_dir = self.env.subst("$PROJECT_SRC_DIR")
        self.build_dir = self.env.subst("$BUILD_DIR")

        # Cache files
        self.cache_file = os.path.join(self.project_dir, ".pio", "ldf_cache", f"ldf_cache_{self.env_name}.py")
        self.ldf_cache_ini = os.path.join(self.project_dir, "ldf_cache.ini")
        self.platformio_ini = os.path.join(self.project_dir, "platformio.ini")
        self.platformio_ini_backup = os.path.join(self.project_dir, ".pio", f"platformio_backup_{self.env_name}.ini")

        # Build order files
        self.build_order_file = os.path.join(self.project_dir, f"correct_build_order_{self.env_name}.txt")
        self.link_order_file = os.path.join(self.project_dir, f"correct_link_order_{self.env_name}.txt")

        # Compile commands
        self.compiledb_dir = os.path.join(self.project_dir, ".pio", "compiledb")
        self.compile_commands_file = os.path.join(self.compiledb_dir, f"compile_commands_{self.env_name}.json")

        # Artifacts cache
        self.artifacts_cache_dir = os.path.join(self.project_dir, ".pio", "ldf_cache", "artifacts", self.env_name)

        self.ALL_RELEVANT_EXTENSIONS = self.HEADER_EXTENSIONS | self.SOURCE_EXTENSIONS | self.CONFIG_EXTENSIONS
        self.real_packages_dir = os.path.join(ProjectConfig.get1_instance().get("platformio", "packages_dir"))

    def _is_log2compdb_available(self):
        """Check if log2compdb is available."""
        try:
            subprocess.run(["log2compdb", "--help"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _install_log2compdb(self):
        """Install log2compdb using pip."""
        print("Installing log2compdb...")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "log2compdb"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print("✅ log2compdb installed successfully")
                return True
            else:
                print(f"❌ Failed to install log2compdb: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ Error installing log2compdb: {e}")
            return False

    def _ensure_log2compdb_available(self):
        """Ensure log2compdb is available, install if necessary."""
        if self._is_log2compdb_available():
            return True
        print("log2compdb not found, attempting to install...")
        return self._install_log2compdb()

    def create_compiledb_with_log2compdb(self):
        """
        Build the project and generate compile_commands.json using log2compdb.
        Replaces the traditional compiledb creation logic.
        """
        if not self._ensure_log2compdb_available():
            print("❌ log2compdb not available and installation failed")
            return False

        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as log_file:
            log_path = log_file.name

        try:
            print(f"🔨 Building project and capturing verbose output...")
            build_cmd = ["pio", "run", "-e", self.env_name, "-v"]
            
            with open(log_path, 'w') as log_file:
                process = subprocess.run(
                    build_cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=self.project_dir
                )

            if process.returncode != 0:
                print(f"❌ Build failed with return code {process.returncode}")
                return False

            print(f"🔧 Generating compile_commands.json with log2compdb...")
            
            # Create target directory if it doesn't exist
            os.makedirs(self.compiledb_dir, exist_ok=True)

            log2compdb_cmd = [
                "log2compdb",
                "-i", log_path,
                "-o", self.compile_commands_file,
                "-c", "xtensa-esp32-elf-gcc",
                "-c", "xtensa-esp32-elf-g++",
                "-c", "riscv32-esp-elf-gcc",
                "-c", "riscv32-esp-elf-g++",
                "-c", "arm-none-eabi-gcc",
                "-c", "arm-none-eabi-g++"
            ]

            result = subprocess.run(log2compdb_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"❌ log2compdb failed: {result.stderr}")
                return False

            if os.path.exists(self.compile_commands_file):
                file_size = os.path.getsize(self.compile_commands_file)
                print(f"✅ Generated {self.compile_commands_file} ({file_size} bytes)")
                return True
            else:
                print(f"❌ compile_commands.json was not created")
                return False

        except Exception as e:
            print(f"❌ Error during build or compiledb generation: {e}")
            return False
        finally:
            if os.path.exists(log_path):
                os.unlink(log_path)

    def environment_specific_compiledb_restart(self):
        """
        Ensure compile_commands.json exists. If not, create it with log2compdb,
        save the LDF cache, and exit. The user must then rerun the build manually.
        """
        # Check if environment-specific file already exists
        if os.path.exists(self.compile_commands_file):
            print("✅ compile_commands.json exists, proceeding with build.")
            return

        print("=" * 60)
        print(f"COMPILE_COMMANDS_{self.env_name.upper()}.JSON MISSING")
        print("=" * 60)

        print(f"Environment: {self.env_name}")
        print("1. Creating compile_commands.json with log2compdb...")

        # Use log2compdb to create compile_commands.json
        if not self.create_compiledb_with_log2compdb():
            print(f"✗ Error creating compile_commands.json with log2compdb")
            sys.exit(1)

        # Create build order and cache
        print("2. Creating build order and saving LDF cache...")
        build_order_data = self.get_correct_build_order()
        artifacts_data = self.analyze_build_artifacts()
        combined_data = {
            'build_order': build_order_data,
            'artifacts': artifacts_data,
            'project_hash': self.get_project_hash_with_details()['final_hash'],
            'timestamp': datetime.datetime.now().isoformat(),
            'env_name': self.env_name
        }
        self.save_combined_cache(combined_data)

        print("=" * 60)
        print("LDF cache saved. Please rerun 'pio run' to use the new cache.")
        print("=" * 60)
        sys.exit(0)

    def get_correct_build_order(self):
        """
        Combines compile_commands.json (order) with build artifacts (paths).
        Creates correct build and link order files for proper compilation.
        
        Returns:
            dict: Build order data with ordered objects and file paths
        """
        # Load compile_commands.json for correct order
        if not os.path.exists(self.compile_commands_file):
            print(f"⚠ compile_commands_{self.env_name}.json not found")
            return None

        try:
            with open(self.compile_commands_file, "r") as f:
                compile_db = json.load(f)
        except Exception as e:
            print(f"✗ Error reading compile_commands.json: {e}")
            return None

        # Map source files to object files and extract build information
        ordered_objects = []
        include_paths = set()
        defines = set()
        build_flags = set()

        for i, entry in enumerate(compile_db, 1):
            source_file = entry.get('file', '')
            command = entry.get('command', '')

            # Extract object file from command
            obj_match = re.search(r'-o\s+(\S+\.o)', command)
            if obj_match:
                obj_file = obj_match.group(1)
                ordered_objects.append({
                    'order': i,
                    'source': source_file,
                    'object': obj_file,
                })

            # Extract include paths from compile commands
            include_matches = re.findall(r'-I\s*([^\s]+)', command)
            for inc_path in include_matches:
                inc_path = inc_path.strip('"\'')
                if os.path.exists(inc_path):
                    include_paths.add(inc_path)

            # Extract defines from compile commands
            define_matches = re.findall(r'-D\s*([^\s]+)', command)
            for define in define_matches:
                defines.add(define)

            # Extract other build flags
            flag_matches = re.findall(r'(-[fmWO][^\s]*)', command)
            for flag in flag_matches:
                build_flags.add(flag)

        # Save build order
        try:
            with open(self.build_order_file, "w") as f:
                for obj_info in ordered_objects[:-1]:  # Exclude last element
                    f.write(f"{obj_info['source']}\n")

            # Create correct linker order
            with open(self.link_order_file, "w") as f:
                for obj_info in ordered_objects[:-1]:  # Exclude last element
                    f.write(f"{obj_info['object']}\n")

            print(f"✓ Created: correct_build_order_{self.env_name}.txt")
            print(f"✓ Created: correct_link_order_{self.env_name}.txt")

            return {
                'ordered_objects': ordered_objects,
                'build_order_file': self.build_order_file,
                'link_order_file': self.link_order_file,
                'include_paths': list(include_paths),
                'defines': list(defines),
                'build_flags': list(build_flags)
            }

        except Exception as e:
            print(f"✗ Error writing build order files: {e}")
            return None

    def copy_artifacts_to_cache(self, lib_build_dir):
        """
        Copies all .a and .o files to the cache folder.
        
        Args:
            lib_build_dir (str): Build directory
            
        Returns:
            dict: Mapping from original to cache paths
        """
        if not os.path.exists(lib_build_dir):
            return {}

        # Create cache folder
        os.makedirs(self.artifacts_cache_dir, exist_ok=True)

        path_mapping = {}
        copied_count = 0

        print(f"📦 Copying artifacts to {self.artifacts_cache_dir}")

        for root, dirs, files in os.walk(lib_build_dir):
            for file in files:
                if file.endswith(('.a', '.o')):
                    # Skip src and ld folders for .o files
                    if file.endswith('.o'):
                        if '/src' in root.replace('\\', '/') or root.endswith('src'):
                            continue
                        if '/ld' in root.replace('\\', '/') or root.endswith('ld'):
                            continue

                    original_path = os.path.join(root, file)

                    # Create relative path from build folder
                    rel_path = os.path.relpath(original_path, lib_build_dir)
                    cache_path = os.path.join(self.artifacts_cache_dir, rel_path)

                    # Create target folder
                    os.makedirs(os.path.dirname(cache_path), exist_ok=True)

                    try:
                        shutil.copy2(original_path, cache_path)
                        path_mapping[original_path] = cache_path
                        copied_count += 1
                    except Exception as e:
                        print(f"⚠ Error copying {original_path}: {e}")

        print(f"📦 {copied_count} artifacts copied to cache")
        return path_mapping

    def analyze_build_artifacts(self):
        """
        Analyze build artifacts and collect library information.
        
        Returns:
            dict: Artifact analysis results
        """
        lib_build_dir = os.path.join(self.project_dir, '.pio', 'build', self.env_name)

        if not os.path.exists(lib_build_dir):
            print(f"⚠ Build directory not found: {lib_build_dir}")
            return {}

        # Copy artifacts to cache
        path_mapping = self.copy_artifacts_to_cache(lib_build_dir)

        # Collect library and object information
        compiled_libraries = []
        compiled_objects = []

        for original_path, cache_path in path_mapping.items():
            if original_path.endswith('.a'):
                compiled_libraries.append(cache_path)
            elif original_path.endswith('.o'):
                compiled_objects.append(cache_path)

        print(f"📦 Found {len(compiled_libraries)} library files (*.a) in cache")
        print(f"📦 Found {len(compiled_objects)} object files (*.o) in cache")

        return {
            'compiled_libraries': compiled_libraries,
            'compiled_objects': compiled_objects,
            'path_mapping': path_mapping
        }

    def save_combined_cache(self, combined_data):
        """
        Saves the combined cache solution.
        
        Args:
            combined_data (dict): Combined cache data to save
        """
        try:
            combined_data['signature'] = self.compute_signature(combined_data)

            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)

            with open(self.cache_file, 'w', encoding='utf-8') as f:
                f.write("# LDF Cache - Complete Build Environment with Build Order\n")
                f.write("# Optimized for lib_ldf_mode = off with correct build order\n")
                f.write("# Generated as Python dict\n\n")
                f.write("cache_data = \\\n")
                f.write(pprint.pformat(combined_data, indent=2, width=120))
                f.write("\n")

            print(f"💾 Combined cache saved: {self.cache_file}")

        except Exception as e:
            print(f"✗ Error saving combined cache: {e}")

    def compute_signature(self, data):
        """
        Compute a signature for the cache data.
        
        Args:
            data (dict): Cache data
            
        Returns:
            str: Signature string
        """
        return hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()

    def get_project_hash_with_details(self):
        """
        Compute a hash of all relevant project files for cache invalidation.
        
        Returns:
            dict: {'final_hash': str, 'file_hashes': dict}
        """
        def hash_file(path):
            with open(path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()

        file_hashes = {}
        final_hash = hashlib.md5()

        for root, dirs, files in os.walk(self.project_dir):
            # Skip ignored directories
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]

            for file in files:
                if any(file.endswith(ext) for ext in self.ALL_RELEVANT_EXTENSIONS):
                    file_path = os.path.join(root, file)
                    file_hash = hash_file(file_path)
                    file_hashes[file_path] = file_hash
                    final_hash.update(file_hash.encode())

        return {
            'final_hash': final_hash.hexdigest(),
            'file_hashes': file_hashes
        }

    def validate_ldf_mode_compatibility(self):
        """
        Validate that the project uses chain mode or off mode only.
        This cache optimizer is designed specifically for chain mode.
        
        Returns:
            bool: True if LDF mode is compatible (chain or off), False otherwise
        """
        try:
            config = ProjectConfig.get_instance()
            env_section = f"env:{self.env_name}"

            # Check environment-specific setting first
            if config.has_option(env_section, "lib_ldf_mode"):
                ldf_mode = config.get(env_section, "lib_ldf_mode")
            # Check global platformio section
            elif config.has_option("platformio", "lib_ldf_mode"):
                ldf_mode = config.get("platformio", "lib_ldf_mode")
            else:
                # Default is chain mode
                ldf_mode = "chain"

            ldf_mode = ldf_mode.strip().lower()

            if ldf_mode in ['chain', 'off']:
                print(f"✅ LDF mode '{ldf_mode}' is compatible with cache optimizer")
                return True
            else:
                print(f"❌ LDF Cache optimizer only supports 'chain' mode! Current mode: '{ldf_mode}'")
                print("   Modes 'deep', 'chain+', 'deep+' require full LDF analysis")
                return False

        except Exception as e:
            print(f"⚠ Warning: Could not determine LDF mode: {e}")
            print("   Assuming 'chain' mode (default)")
            return True

    def resolve_pio_placeholders(self, path):
        """
        Replace '${platformio.packages_dir}' with the actual PlatformIO packages directory.
        
        Args:
            path (str): Path potentially containing placeholders
            
        Returns:
            str: Path with resolved placeholders
        """
        if not isinstance(path, str):
            return path

        return path.replace("${platformio.packages_dir}", self.real_packages_dir)

    def is_platformio_path(self, path):
        """
        Check if a path is within PlatformIO's own directories.
        
        Args:
            path (str): Path to check
            
        Returns:
            bool: True if path is within PlatformIO directories
        """
        return self.real_packages_dir and path.startswith(self.real_packages_dir)

# --- Main execution ---

def main(env):
    """
    Main function to be called from PlatformIO.
    """
    optimizer = LDFCacheOptimizer(env)
    if not optimizer.validate_ldf_mode_compatibility():
        return

    # Early check for compile_commands.json
    optimizer.environment_specific_compiledb_restart()

    # If we get here, compile_commands.json exists and we can proceed with the build
    # ... (your normal build logic here)

# Call main when this script is executed
if __name__ == "__main__":
    print("This script is intended to be used as a PlatformIO extra script.")
    sys.exit(1)
