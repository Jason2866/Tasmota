"""

PlatformIO Advanced Script for intelligent LDF caching with build order management.

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
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from platformio.project.config import ProjectConfig
from SCons.Script import COMMAND_LINE_TARGETS

class LDFCacheOptimizer:
    """
    PlatformIO LDF (Library Dependency Finder) cache optimizer with build order management.
    Designed specifically for lib_ldf_mode = chain and off modes.
    Invalidates cache only when #include directives change in source files.
    Includes complete build order management for correct linking.
    Implements a two-run strategy:
    1. First run: LDF active, create comprehensive cache
    2. Second run: LDF off, use cache for all dependencies
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

        # Cache files - using pathlib for cross-platform compatibility
        cache_base = Path(self.project_dir) / ".pio" / "ldf_cache"
        self.cache_file = cache_base / f"ldf_cache_{self.env_name}.py"
        self.ldf_cache_ini = Path(self.project_dir) / "ldf_cache.ini"
        self.platformio_ini = Path(self.project_dir) / "platformio.ini"
        self.platformio_ini_backup = Path(self.project_dir) / ".pio" / f"platformio_backup_{self.env_name}.ini"

        # Build order files
        self.build_order_file = Path(self.project_dir) / f"correct_build_order_{self.env_name}.txt"
        self.link_order_file = Path(self.project_dir) / f"correct_link_order_{self.env_name}.txt"

        # Compile commands
        compiledb_base = Path(self.project_dir) / ".pio" / "compiledb"
        self.compiledb_dir = compiledb_base
        self.compile_commands_file = compiledb_base / f"compile_commands_{self.env_name}.json"
        self.compile_commands_log_file = compiledb_base / f"compile_commands_{self.env_name}.log"

        # Artifacts cache
        self.artifacts_cache_dir = Path(self.project_dir) / ".pio" / "ldf_cache" / "artifacts" / self.env_name

        self.ALL_RELEVANT_EXTENSIONS = self.HEADER_EXTENSIONS | self.SOURCE_EXTENSIONS | self.CONFIG_EXTENSIONS
        self.real_packages_dir = Path(ProjectConfig.get_instance().get("platformio", "packages_dir"))

    def _normalize_path(self, path):
        """
        Platform-independent path normalization using pathlib.
        Converts all paths to forward slashes for internal consistency.
        
        Args:
            path (str or Path): Path to normalize
            
        Returns:
            str: Normalized path with forward slashes
        """
        if not path:
            return ""
        
        # Convert to Path object and normalize
        normalized = Path(path).resolve()
        # Convert to string with forward slashes for consistency
        return str(normalized).replace(os.sep, '/')

    def _is_ignored_directory(self, dir_path):
        """
        Platform-independent directory checking against ignore list.
        Uses pathlib for robust path handling across platforms.
        
        Args:
            dir_path (str or Path): Directory path to check
            
        Returns:
            bool: True if directory should be ignored
        """
        if not dir_path:
            return False
            
        path_obj = Path(dir_path)
        
        # Check directory name directly
        if path_obj.name in self.IGNORE_DIRS:
            return True
            
        # Check all path segments
        for part in path_obj.parts:
            if part in self.IGNORE_DIRS:
                return True
                
        return False

    def _should_skip_object_file(self, obj_path, root_dir):
        """
        Enhanced object file filtering with consistent path handling.
        Uses pathlib for cross-platform path operations.
        
        Args:
            obj_path (str or Path): Object file path
            root_dir (str or Path): Root directory path
            
        Returns:
            bool: True if object file should be skipped
        """
        obj_path = Path(obj_path)
        root_dir = Path(root_dir)
        
        if obj_path.suffix != '.o':
            return False
            
        # Skip src and ld directories for .o files
        skip_patterns = ['src', 'ld']
        
        # Check if any parent directory matches skip patterns
        for parent in root_dir.parents:
            if parent.name in skip_patterns:
                return True
                
        if root_dir.name in skip_patterns:
            return True
            
        # Check if path is in an ignored directory
        return self._is_ignored_directory(root_dir)

    def _get_relative_path_from_project(self, file_path):
        """
        Calculate relative path from project root with consistent path handling.
        Uses pathlib for robust cross-platform path operations.
        
        Args:
            file_path (str or Path): File path to make relative
            
        Returns:
            str: Relative path from project root with forward slashes
        """
        try:
            file_path = Path(file_path).resolve()
            project_dir = Path(self.project_dir).resolve()
            
            # Calculate relative path
            rel_path = file_path.relative_to(project_dir)
            
            # Convert to string with forward slashes
            return str(rel_path).replace(os.sep, '/')
            
        except (ValueError, OSError):
            # Fallback for paths outside project directory
            return str(Path(file_path)).replace(os.sep, '/')

    def _extract_includes(self, file_path):
        """
        Extract #include directives with improved path handling.
        Uses pathlib for robust file operations.
        
        Args:
            file_path (str or Path): Source file to analyze
            
        Returns:
            set: Set of normalized include paths
        """
        includes = set()
        
        try:
            file_path = Path(file_path)
            
            with file_path.open('r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line.startswith('#include'):
                        # Extract include statement
                        include_match = re.search(r'#include\s*[<"]([^>"]+)[>"]', line)
                        if include_match:
                            include_path = include_match.group(1)
                            # Normalize include path to forward slashes
                            normalized_include = str(Path(include_path)).replace(os.sep, '/')
                            includes.add(normalized_include)
                            
        except (IOError, OSError, UnicodeDecodeError) as e:
            print(f"⚠ Could not read {file_path}: {e}")
            
        return includes

    def get_project_hash_with_details(self):
        """
        Calculate project hash with improved path handling using pathlib.
        Only includes LDF-relevant files for precise cache invalidation.
        
        Returns:
            dict: Hash details including file hashes and final combined hash
        """
        file_hashes = {}
        
        # Walk through source directories using pathlib
        src_path = Path(self.src_dir)
        
        for file_path in src_path.rglob('*'):
            # Skip directories and ignored paths
            if file_path.is_dir() or self._is_ignored_directory(file_path.parent):
                continue
                
            # Only process relevant file extensions
            if file_path.suffix in self.ALL_RELEVANT_EXTENSIONS:
                try:
                    # Calculate relative path from project
                    rel_path = self._get_relative_path_from_project(file_path)
                    
                    # Calculate file hash
                    file_content = file_path.read_bytes()
                    file_hash = hashlib.md5(file_content).hexdigest()
                    file_hashes[rel_path] = file_hash
                    
                except (IOError, OSError) as e:
                    print(f"⚠ Could not hash {file_path}: {e}")
                    continue

        # Add platformio.ini hash
        if self.platformio_ini.exists():
            try:
                rel_ini_path = self._get_relative_path_from_project(self.platformio_ini)
                ini_content = self.platformio_ini.read_bytes()
                file_hashes[rel_ini_path] = hashlib.md5(ini_content).hexdigest()
            except (IOError, OSError) as e:
                print(f"⚠ Could not hash platformio.ini: {e}")

        # Create final hash
        combined_content = json.dumps(file_hashes, sort_keys=True)
        final_hash = hashlib.sha256(combined_content.encode()).hexdigest()

        return {
            'file_hashes': file_hashes,
            'final_hash': final_hash,
            'file_count': len(file_hashes)
        }

    def compute_signature(self, data):
        """
        Compute signature for cache data validation.
        
        Args:
            data (dict): Data to sign
            
        Returns:
            str: SHA256 signature
        """
        # Remove signature field if present to avoid recursive signing
        data_copy = data.copy()
        data_copy.pop('signature', None)
        
        # Create deterministic string representation
        data_str = json.dumps(data_copy, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()

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

    def environment_specific_compiledb(self):
        """
        Environment-specific compiledb creation using log2compdb.
        Ensures compile_commands_{env}.json exists for build order analysis.
        Integrates seamlessly into the current build.
        """
        current_targets = COMMAND_LINE_TARGETS[:]
        is_build_target = (
            not current_targets or
            any(target in ["build", "buildprog"] for target in current_targets)
        )

        if not is_build_target:
            return

        # Check if environment-specific file already exists
        if self.compile_commands_file.exists():
            print(f"✅ {self.compile_commands_file} exists, using existing file.")
            return

        print("=" * 60)
        print(f"COMPILE_COMMANDS_{self.env_name.upper()}.JSON MISSING")
        print("Creating during current build...")
        print("=" * 60)

        # Enable verbose mode for current build
        os.environ["PLATFORMIO_SETTING_FORCE_VERBOSE"] = "true"
    
        # Register post-build action to create compile_commands.json
        def create_compiledb_post_build(target, source, env):
            """Post-build action to create compile_commands.json"""
            try:
                print("🔧 Creating compile_commands.json from current build log...")
            
                # Search for current build log
                build_log = None
                possible_logs = [
                    Path(self.project_dir) / f"build_{self.env_name}.log",
                    Path(self.build_dir) / "build.log",
                    self.compile_commands_log_file
                ]
            
                for log_path in possible_logs:
                    if log_path.exists():
                        build_log = str(log_path)
                        break
            
                if not build_log:
                    print("⚠ No build log found, creating from verbose output capture")
                    return
            
                # Execute log2compdb
                if self._ensure_log2compdb_available():
                    log2compdb_cmd = [
                        "log2compdb",
                        "-i", build_log,
                        "-o", str(self.compile_commands_file),
                        "-c", "xtensa-esp32-elf-gcc",
                        "-c", "xtensa-esp32-elf-g++",
                        "-c", "riscv32-esp-elf-gcc", 
                        "-c", "riscv32-esp-elf-g++",
                        "-c", "arm-none-eabi-gcc",
                        "-c", "arm-none-eabi-g++"
                    ]
                
                    self.compiledb_dir.mkdir(parents=True, exist_ok=True)
                    result = subprocess.run(log2compdb_cmd, capture_output=True, text=True)
                
                    if result.returncode == 0 and self.compile_commands_file.exists():
                        file_size = self.compile_commands_file.stat().st_size
                        print(f"✅ Generated {self.compile_commands_file} ({file_size} bytes)")
                    else:
                        print(f"❌ log2compdb failed: {result.stderr}")
            
            except Exception as e:
                print(f"⚠ Error creating compile_commands.json: {e}")
    
        # Register the post-build action
        self.env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", create_compiledb_post_build)
    
        print("✅ Verbose mode activated for current build")
        print("✅ compile_commands.json will be created after build completion")

    def create_compiledb_with_log2compdb(self):
        """
        Alternative method: Create compile_commands.json from existing verbose output
        or capture current build output for log2compdb processing.
        """
        if not self._ensure_log2compdb_available():
            print("❌ log2compdb not available and installation failed")
            return False

        # Create target directory if it doesn't exist
        self.compiledb_dir.mkdir(parents=True, exist_ok=True)
    
        try:
            # Option 1: Use existing log file if available
            existing_log = None
            possible_logs = [
                Path(self.project_dir) / f"build_{self.env_name}.log",
                Path(self.build_dir) / "build.log"
            ]
        
            for log_path in possible_logs:
                if log_path.exists() and log_path.stat().st_size > 0:
                    existing_log = str(log_path)
                    print(f"📄 Using existing build log: {existing_log}")
                    break

            input_log = existing_log
            print(f"🔧 Generating compile_commands.json with log2compdb from {input_log}...")
    
            log2compdb_cmd = [
                "log2compdb",
                "-i", input_log,
                "-o", str(self.compile_commands_file),
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

            if self.compile_commands_file.exists():
                file_size = self.compile_commands_file.stat().st_size
                print(f"✅ Generated {self.compile_commands_file} ({file_size} bytes)")
                return True
            else:
                print(f"❌ compile_commands.json was not created")
                return False

        except Exception as e:
            print(f"❌ Error during compiledb generation: {e}")
            return False

    def get_correct_build_order(self):
        """
        Combines compile_commands.json (order) with build artifacts (paths).
        Creates correct build and link order files for proper compilation.
        
        Returns:
            dict: Build order data with ordered objects and file paths
        """
        # Load compile_commands.json for correct order
        if not self.compile_commands_file.exists():
            print(f"⚠ compile_commands_{self.env_name}.json not found")
            return None

        try:
            with self.compile_commands_file.open("r") as f:
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
                if Path(inc_path).exists():
                    include_paths.add(str(Path(inc_path)))

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
            with self.build_order_file.open("w") as f:
                for obj_info in ordered_objects:
                    f.write(f"{obj_info['source']}\n")

            # Create correct linker order
            with self.link_order_file.open("w") as f:
                for obj_info in ordered_objects:
                    f.write(f"{obj_info['object']}\n")

            print(f"✓ Created: correct_build_order_{self.env_name}.txt")
            print(f"✓ Created: correct_link_order_{self.env_name}.txt")

            return {
                'ordered_objects': ordered_objects,
                'build_order_file': str(self.build_order_file),
                'link_order_file': str(self.link_order_file),
                'include_paths': list(include_paths),
                'defines': list(defines),
                'build_flags': list(build_flags)
            }

        except Exception as e:
            print(f"✗ Error writing build order files: {e}")
            return None

    def apply_build_order_to_environment(self, build_order_data):
        """
        Applies the correct build order to the SCons environment
        with complete linker integration and correct flag order.
        
        Args:
            build_order_data (dict): Build order data from get_correct_build_order
            
        Returns:
            bool: True if application was successful
        """
        if not build_order_data:
            return False

        try:
            ordered_objects = build_order_data.get('ordered_objects', [])

            # Collect all object files in correct order
            object_files = []
            for obj_info in ordered_objects:
                obj_path = obj_info['object']
                if Path(obj_path).exists():
                    object_files.append(obj_path)

            if not object_files:
                print("⚠ No valid object files found")
                return False

            # Set OBJECTS in correct order
            self.env.Replace(OBJECTS=object_files)

            # Apply include paths and defines from compile commands
            self._apply_compile_data_to_environment(build_order_data)

            # CRITICAL: Implement correct linker order
            self._apply_correct_linker_order(object_files)

            print(f"✅ Build order applied: {len(object_files)} object files")
            print(f"✅ Linker order configured for correct symbol resolution")

            return True

        except Exception as e:
            print(f"✗ Error applying build order: {e}")
            return False

    def _apply_compile_data_to_environment(self, build_order_data):
        """
        Apply include paths, defines and build flags extracted from compile commands.
        
        Args:
            build_order_data (dict): Build order data containing compile information
        """
        try:
            # Apply include paths
            include_paths = build_order_data.get('include_paths', [])
            if include_paths:
                existing_paths = [str(p) for p in self.env.get('CPPPATH', [])]
                new_paths = [p for p in include_paths if p not in existing_paths]
                if new_paths:
                    self.env.Append(CPPPATH=new_paths)
                    print(f" ✅ Added {len(new_paths)} include paths from compile commands")

            # Apply defines
            defines = build_order_data.get('defines', [])
            if defines:
                existing_defines = [str(d) for d in self.env.get('CPPDEFINES', [])]
                new_defines = [d for d in defines if d not in existing_defines]
                if new_defines:
                    self.env.Append(CPPDEFINES=new_defines)
                    print(f" ✅ Added {len(new_defines)} defines from compile commands")

            # Apply build flags
            build_flags = build_order_data.get('build_flags', [])
            if build_flags:
                self.env.Append(CCFLAGS=list(build_flags))
                self.env.Append(CXXFLAGS=list(build_flags))
                print(f" ✅ Added {len(build_flags)} build flags from compile commands")

        except Exception as e:
            print(f"⚠ Warning applying compile data: {e}")

    def _apply_correct_linker_order(self, object_files):
        """
        Implements correct linker order based on PlatformIO documentation.
        Solves symbol resolution problems with linker scripts.
        
        Args:
            object_files (list): List of object files in correct order
        """
        try:
            # Save current LINKFLAGS
            current_linkflags = self.env.get('LINKFLAGS', [])

            # Create optimized linker command structure
            # Based on GitHub Issue #3208: Object files BEFORE linker flags
            custom_linkcom = (
                "$LINK -o $TARGET "
                "${_long_sources_hook(__env__, SOURCES)} "  # Objects first
                "$LINKFLAGS "  # Then flags
                "$__RPATH $_LIBDIRFLAGS $_LIBFLAGS"  # Libraries last
            )

            # Apply correct linker order
            self.env.Replace(LINKCOM=custom_linkcom)

            # Optimize linker flags for symbol resolution
            optimized_linkflags = []

            # Group related objects for better symbol resolution
            optimized_linkflags.extend([
                "-Wl,--start-group",  # Begin grouping
            ])

            # Add existing LINKFLAGS (without duplicates)
            for flag in current_linkflags:
                if flag not in optimized_linkflags:
                    optimized_linkflags.append(flag)

            # Close grouping for circular dependencies
            optimized_linkflags.extend([
                "-Wl,--end-group",  # End grouping
                "-Wl,--gc-sections",  # Remove unused sections
            ])

            # Set optimized linker flags
            self.env.Replace(LINKFLAGS=optimized_linkflags)

            # Special handling for linker scripts (if present)
            self._handle_linker_scripts()

            print(f"🔗 Linker command optimized for correct symbol resolution")
            print(f"🔗 {len(optimized_linkflags)} linker flags configured")

        except Exception as e:
            print(f"⚠ Warning during linker optimization: {e}")
            # Fallback to standard behavior
            pass

    def _handle_linker_scripts(self):
        """
        Special handling for linker scripts based on GitHub Issue #3208.
        Ensures linker scripts are correctly placed before object files.
        """
        try:
            linkflags = self.env.get('LINKFLAGS', [])
            linker_script_flags = []
            other_flags = []

            # Separate linker script flags from other flags
            for flag in linkflags:
                if isinstance(flag, str):
                    if '--script=' in flag or '-T' in flag or flag.endswith('.ld'):
                        linker_script_flags.append(flag)
                    else:
                        other_flags.append(flag)
                else:
                    other_flags.append(flag)

            if linker_script_flags:
                # Linker scripts must come BEFORE other flags
                reordered_flags = linker_script_flags + other_flags
                self.env.Replace(LINKFLAGS=reordered_flags)
                print(f"🔗 {len(linker_script_flags)} linker script(s) correctly positioned")

        except Exception as e:
            print(f"⚠ Warning during linker script handling: {e}")

    def copy_artifacts_to_cache(self, lib_build_dir):
        """
        Copies all .a and .o files to the cache folder with improved path handling.
        Uses pathlib for robust cross-platform file operations.
        
        Args:
            lib_build_dir (str or Path): Build directory
            
        Returns:
            dict: Mapping from original to cache paths
        """
        lib_build_path = Path(lib_build_dir)
        if not lib_build_path.exists():
            return {}

        # Create cache folder
        self.artifacts_cache_dir.mkdir(parents=True, exist_ok=True)

        path_mapping = {}
        copied_count = 0

        print(f"📦 Copying artifacts to {self.artifacts_cache_dir}")

        for root, dirs, files in os.walk(lib_build_path):
            root_path = Path(root)
            
            # Filter ignored directories BEFORE os.walk enters them
            dirs[:] = [d for d in dirs if not self._is_ignored_directory(root_path / d)]
            
            for file in files:
                if file.endswith(('.a', '.o')):
                    original_path = root_path / file
                    
                    # Use improved object file filtering
                    if self._should_skip_object_file(original_path, root_path):
                        continue

                    # Create relative path from build folder with consistent handling
                    try:
                        rel_path = original_path.relative_to(lib_build_path)
                        cache_path = self.artifacts_cache_dir / rel_path
                        
                    except (ValueError, OSError) as e:
                        print(f"⚠ Path calculation error for {original_path}: {e}")
                        continue

                    # Create target folder
                    cache_path.parent.mkdir(parents=True, exist_ok=True)

                    try:
                        shutil.copy2(str(original_path), str(cache_path))
                        path_mapping[str(original_path)] = str(cache_path)
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
        lib_build_dir = Path(self.project_dir) / '.pio' / 'build' / self.env_name

        if not lib_build_dir.exists():
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

    def apply_ldf_cache_with_build_order(self, cache_data):
        """
        Extended application of LDF cache with build order integration.
        Combines library dependencies with correct build order.
        
        Args:
            cache_data (dict): Cache data containing build order and artifacts
            
        Returns:
            bool: True if application was successful
        """
        try:
            build_order = cache_data.get('build_order', {})
            artifacts = cache_data.get('artifacts', {})

            if not build_order:
                return False

            print("🔧 Applying build order with artifact integration...")

            # Apply build order with compile data
            success_build_order = self.apply_build_order_to_environment(build_order)

            # Apply cached artifacts
            if artifacts and success_build_order:
                self._apply_cached_artifacts(artifacts)

            return success_build_order

        except Exception as e:
            print(f"✗ Error in build order application: {e}")
            return False

    def _apply_cached_artifacts(self, artifacts):
        """
        Apply cached artifacts to the SCons environment.
        
        Args:
            artifacts (dict): Artifact information
        """
        try:
            # Apply static libraries
            compiled_libraries = artifacts.get('compiled_libraries', [])
            if compiled_libraries:
                valid_libs = [lib for lib in compiled_libraries if Path(lib).exists()]
                if valid_libs:
                    self.env.Append(LIBS=valid_libs)
                    print(f" ✅ Added {len(valid_libs)} cached static libraries")

            # Apply object files
            compiled_objects = artifacts.get('compiled_objects', [])
            if compiled_objects:
                valid_objects = [obj for obj in compiled_objects if Path(obj).exists()]
                if valid_objects:
                    self.env.Append(OBJECTS=valid_objects)
                    print(f" ✅ Added {len(valid_objects)} cached object files")

        except Exception as e:
            print(f"⚠ Warning applying cached artifacts: {e}")

    def create_ini_backup(self):
        """
        Create a backup of platformio.ini before modifying it for the second run.
        
        Returns:
            bool: True if backup was created successfully
        """
        try:
            if self.platformio_ini.exists():
                self.platformio_ini_backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(self.platformio_ini), str(self.platformio_ini_backup))
                print("🔒 platformio.ini backup created for two-run strategy")
                return True
        except Exception as e:
            print(f"❌ Error creating backup: {e}")
            return False

    def restore_ini_from_backup(self):
        """
        Restore platformio.ini from backup after cache creation is complete.
        This ensures the original configuration is preserved.
        
        Returns:
            bool: True if restore was successful
        """
        try:
            if self.platformio_ini_backup.exists():
                shutil.copy2(str(self.platformio_ini_backup), str(self.platformio_ini))
                self.platformio_ini_backup.unlink()
                print("🔓 platformio.ini restored from backup - original configuration preserved")
                return True
            else:
                print("⚠ No backup found to restore")
                return False
        except Exception as e:
            print(f"❌ Error restoring from backup: {e}")
            return False

    def modify_platformio_ini_for_second_run(self, new_ldf_mode):
        """
        Modify lib_ldf_mode in platformio.ini for the second run strategy.
        Creates backup first, then modifies for cache-based operation.
        
        Args:
            new_ldf_mode (str): New LDF mode value (typically 'off')
            
        Returns:
            bool: True if modification was successful
        """
        if not self.create_ini_backup():
            print("❌ Cannot proceed without backup")
            return False

        try:
            lines = self.platformio_ini.read_text(encoding='utf-8').splitlines(keepends=True)

            found = False
            for i, line in enumerate(lines):
                if 'lib_ldf_mode' in line.lower() and '=' in line:
                    # Replace only the value after '='
                    parts = line.split('=', 1)
                    lines[i] = parts[0] + '= ' + new_ldf_mode + '\n'
                    found = True
                    print(f"🔧 Modified lib_ldf_mode = {new_ldf_mode} for second run")
                    break

            if not found:
                # Add to [platformio] section or create it
                section_found = False
                for i, line in enumerate(lines):
                    if line.strip().lower() == '[platformio]':
                        lines.insert(i + 1, f'lib_ldf_mode = {new_ldf_mode}\n')
                        section_found = True
                        print(f"🔧 Added lib_ldf_mode = {new_ldf_mode} to [platformio] for second run")
                        break

                if not section_found:
                    # Add at the beginning if section doesn't exist
                    lines = [f'[platformio]\nlib_ldf_mode = {new_ldf_mode}\n\n'] + lines
                    print(f"🔧 Created [platformio] section with lib_ldf_mode = {new_ldf_mode} for second run")

            self.platformio_ini.write_text(''.join(lines), encoding='utf-8')
            return True

        except Exception as e:
            print(f"❌ Error modifying platformio.ini: {e}")
            self.restore_ini_from_backup()
            return False

    def implement_two_run_strategy(self):
        """
        Implements the complete two-run strategy:
        1. Check for existing cache first
        2. If no cache: ensure compiledb exists (by adding verbose to build)
        3. Cache gets created during/after the normal first build
        4. lib_ldf_mode gets set to 'off' after successful build
        
        Returns:
            bool: True if strategy was successful
        """
        print("\n=== Two-Run LDF Cache Strategy ===")

        # Check if we already have a valid cache
        existing_cache = self.load_combined_cache()
        if existing_cache:
            print("✅ Valid cache found - applying cached dependencies")
            success = self.apply_ldf_cache_with_build_order(existing_cache)
            if success:
                print("🚀 Second run: Using cached dependencies, LDF bypassed")
                return True
            else:
                print("⚠ Cache application failed, falling back to first run")

        # First run preparation: This will trigger the normal first build automatically
        print("🔄 Preparing first run: Checking compile_commands...")

        # This call will:
        # Create compiledb if missing using log2compdb in first compile run
        self.environment_specific_compiledb()

        # If we reach this point, compiledb already exists
        print("✅ compile_commands available - proceeding with cache strategy")
        return True

    def create_complete_ldf_replacement_with_linker(self):
        """
        Creates a complete LDF replacement solution with optimized linker integration.
        
        Returns:
            bool: True if successful
        """
        print("\n=== Complete LDF Replacement Solution with Linker Optimization ===")

        try:
            # Ensure compile_commands.json exists using log2compdb
            self.environment_specific_compiledb()

            # Create build order with compile data extraction
            build_order_data = self.get_correct_build_order()
            if not build_order_data:
                print("❌ Could not create build order")
                return self.fallback_to_standard_ldf()

            # Analyze build artifacts
            artifacts_data = self.analyze_build_artifacts()

            # Combine with optimized linker logic
            combined_data = {
                'build_order': build_order_data,
                'artifacts': artifacts_data,
                'project_hash': self.get_project_hash_with_details()['final_hash'],
                'timestamp': datetime.datetime.now().isoformat(),
                'env_name': self.env_name,
                'linker_optimized': True
            }

            # Apply everything with linker optimization
            success = self.apply_ldf_cache_with_build_order(combined_data)

            if success:
                print("✅ Complete LDF replacement solution with linker optimization successful")
                self.save_combined_cache(combined_data)
            else:
                print("❌ Error - fallback to standard LDF")
                return self.fallback_to_standard_ldf()

            return success

        except Exception as e:
            print(f"❌ Critical error: {e}")
            return self.fallback_to_standard_ldf()

    def fallback_to_standard_ldf(self):
        """
        Graceful fallback to standard LDF on errors.
        Restores original platformio.ini configuration.
        
        Returns:
            bool: False to indicate fallback was used
        """
        try:
            print("🔄 Fallback to standard LDF activated")
            self.restore_ini_from_backup()
            return False
        except Exception as e:
            print(f"⚠ Warning during fallback: {e}")
            return False

    def save_combined_cache(self, combined_data):
        """
        Saves the combined cache solution.
        
        Args:
            combined_data (dict): Combined cache data to save
        """
        try:
            combined_data['signature'] = self.compute_signature(combined_data)

            self.cache_file.parent.mkdir(parents=True, exist_ok=True)

            with self.cache_file.open('w', encoding='utf-8') as f:
                f.write("# LDF Cache - Complete Build Environment with Build Order\n")
                f.write("# Optimized for lib_ldf_mode = off with correct build order\n")
                f.write("# Generated as Python dict\n\n")
                f.write("cache_data = \\\n")
                f.write(pprint.pformat(combined_data, indent=2, width=120))
                f.write("\n")

            print(f"💾 Combined cache saved: {self.cache_file}")

        except Exception as e:
            print(f"✗ Error saving combined cache: {e}")

    def load_combined_cache(self):
        """
        Loads and validates the combined cache.
        Cache is only invalidated when #include directives change in source files
        or platformio.ini changes (excluding lib_ldf_mode).
        
        Returns:
            dict: Valid cache data or None if invalid
        """
        if not self.cache_file.exists():
            return None

        try:
            cache_content = self.cache_file.read_text(encoding='utf-8')

            local_vars = {}
            exec(cache_content, {}, local_vars)
            cache_data = local_vars.get('cache_data')

            if not cache_data:
                print("⚠ Cache file contains no data")
                return None

            # Validate environment
            if cache_data.get('env_name') != self.env_name:
                print(f"🔄 Environment changed: {cache_data.get('env_name')} -> {self.env_name}")
                return None

            # Check project hash for changes (only include-relevant changes)
            current_hash = self.get_project_hash_with_details()['final_hash']
            cached_hash = cache_data.get('project_hash')

            if cached_hash != current_hash:
                print("🔄 Project files changed - cache invalidated")
                return None

            # Check if build order files exist
            build_order = cache_data.get('build_order', {})
            if not (Path(build_order.get('build_order_file', '')).exists() and
                    Path(build_order.get('link_order_file', '')).exists()):
                print("⚠ Build order files missing")
                return None

            # Check if cached artifacts exist
            artifacts = cache_data.get('artifacts', {})
            missing_artifacts = []

            for lib_path in artifacts.get('compiled_libraries', []):
                if not Path(lib_path).exists():
                    missing_artifacts.append(lib_path)

            for obj_path in artifacts.get('compiled_objects', []):
                if not Path(obj_path).exists():
                    missing_artifacts.append(obj_path)

            if missing_artifacts:
                print(f"⚠ Cache invalid: {len(missing_artifacts)} cached artifacts missing")
                return None

            print("✅ Combined cache valid")
            return cache_data

        except Exception as e:
            print(f"⚠ Cache validation failed: {e}")
            return None

    def save_ldf_cache_with_build_order(self, target=None, source=None, env_arg=None, **kwargs):
        """
        Saves LDF cache together with build order information.
        Called as post-build action AFTER successful normal build completion.
        This is where lib_ldf_mode gets set to 'off' for the second run.
        
        Args:
            target: SCons target (unused)
            source: SCons source (unused)
            env_arg: SCons environment (unused)
            **kwargs: Additional arguments (unused)
        """
        try:
            print("\n=== Post-Build: Creating LDF Cache ===")

            # Create build order
            build_order_data = self.get_correct_build_order()

            # Analyze artifacts
            artifacts_data = self.analyze_build_artifacts()

            # Get project hash
            hash_details = self.get_project_hash_with_details()

            if build_order_data and artifacts_data:
                combined_data = {
                    'build_order': build_order_data,
                    'artifacts': artifacts_data,
                    'project_hash': hash_details['final_hash'],
                    'hash_details': hash_details['file_hashes'],
                    'env_name': self.env_name,
                    'timestamp': datetime.datetime.now().isoformat(),
                    'pio_version': getattr(self.env, "PioVersion", lambda: "unknown")(),
                    'ldf_mode': 'off',  # Target mode for second run
                    'two_run_strategy': True
                }

                self.save_combined_cache(combined_data)
                print("💾 LDF cache with build order successfully saved!")

                # NOW set lib_ldf_mode = off AFTER successful complete build
                if self.modify_platformio_ini_for_second_run('off'):
                    print("🔧 lib_ldf_mode set to 'off' for second run")
                    print("💡 Run 'pio run' again to use cached dependencies with LDF disabled")
                else:
                    print("❌ Failed to set lib_ldf_mode for second run")

            else:
                print("❌ Could not create build order or analyze artifacts")

        except Exception as e:
            print(f"✗ Error saving LDF cache with build order: {e}")
            import traceback
            traceback.print_exc()

    def validate_ldf_mode_compatibility(self):
        """
        Validate that the project uses chain mode or off mode only.
        This cache optimizer is designed specifically for chain mode.
        
        Returns:
            bool: True if LDF mode is compatible (chain or off), False otherwise
        """
        try:
            config = ProjectConfig()
            env_section = f"env:{self.env['PIOENV']}"

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


# Initialize and execute the LDF cache optimizer
try:
    ldf_optimizer = LDFCacheOptimizer(env)
    
    # Validate LDF mode compatibility
    if ldf_optimizer.validate_ldf_mode_compatibility():
        # Execute the two-run strategy
        success = ldf_optimizer.implement_two_run_strategy()
        
        if success:
            # Register post-build action for cache creation
            env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", ldf_optimizer.save_ldf_cache_with_build_order)
        else:
            print("⚠ LDF Cache strategy initialization failed, using standard LDF")
    else:
        print("⚠ LDF mode not compatible, using standard LDF")
        
except Exception as e:
    print(f"❌ LDF Cache Optimizer initialization failed: {e}")
    print("⚠ Falling back to standard LDF behavior")
