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
from platformio.project.config import ProjectConfig

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
        self.real_packages_dir = os.path.join(ProjectConfig.get_instance().get("platformio", "packages_dir"))

    def environment_specific_compiledb_restart(self):
        """
        Environment-specific compiledb creation with moving and renaming.
        Ensures compile_commands_{env}.json exists for build order analysis.
        """
        current_targets = COMMAND_LINE_TARGETS[:]
        is_build_target = (
            not current_targets or
            any(target in ["build", "buildprog"] for target in current_targets)
        )

        if not is_build_target:
            return

        # Check if environment-specific file already exists
        if os.path.exists(self.compile_commands_file):
            return

        print("=" * 60)
        print(f"COMPILE_COMMANDS_{self.env_name.upper()}.JSON MISSING")
        print("=" * 60)

        # Reconstruct correct PlatformIO arguments
        pio_args = ["-e", self.env_name]
        
        if current_targets:
            for target in current_targets:
                if target not in ["compiledb"]:
                    pio_args.extend(["-t", target])

        try:
            print(f"Environment: {self.env_name}")
            print("1. Aborting current build...")
            print("2. Creating compile_commands.json...")

            # Create target directory if it doesn't exist
            os.makedirs(self.compiledb_dir, exist_ok=True)

            # Delete potentially existing standard file
            standard_compile_db_path = os.path.join(self.project_dir, "compile_commands.json")
            if os.path.exists(standard_compile_db_path):
                os.remove(standard_compile_db_path)
                print(" Old compile_commands.json deleted")

            # Environment-specific compiledb creation
            compiledb_cmd = ["pio", "run", "-e", self.env_name, "-t", "compiledb"]
            print(f" Executing: {' '.join(compiledb_cmd)}")
            result = subprocess.run(compiledb_cmd, cwd=self.project_dir)

            if result.returncode != 0:
                print(f"✗ Error creating compile_commands.json")
                sys.exit(1)

            # Check if standard file was created
            if not os.path.exists(standard_compile_db_path):
                print(f"✗ compile_commands.json was not created")
                sys.exit(1)

            # Move and rename
            print(f"3. Moving to compile_commands_{self.env_name}.json...")
            shutil.move(standard_compile_db_path, self.compile_commands_file)

            # Check if move was successful
            if os.path.exists(self.compile_commands_file):
                file_size = os.path.getsize(self.compile_commands_file)
                print(f"✓ compile_commands_{self.env_name}.json successfully created ({file_size} bytes)")
            else:
                print(f"✗ Error moving file")
                sys.exit(1)

            # Restart original build
            print("4. Restarting original build...")
            restart_cmd = ["pio", "run"] + pio_args
            print(f" Executing: {' '.join(restart_cmd)}")
            print("=" * 60)
            restart_result = subprocess.run(restart_cmd, cwd=self.project_dir)
            sys.exit(restart_result.returncode)

        except Exception as e:
            print(f"✗ Unexpected error: {e}")
            sys.exit(1)

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
            for obj_info in ordered_objects[:-1]:  # Exclude last element
                obj_path = obj_info['object']
                if os.path.exists(obj_path):
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
                    print(f"  ✅ Added {len(new_paths)} include paths from compile commands")

            # Apply defines
            defines = build_order_data.get('defines', [])
            if defines:
                existing_defines = [str(d) for d in self.env.get('CPPDEFINES', [])]
                new_defines = [d for d in defines if d not in existing_defines]
                if new_defines:
                    self.env.Append(CPPDEFINES=new_defines)
                    print(f"  ✅ Added {len(new_defines)} defines from compile commands")

            # Apply build flags
            build_flags = build_order_data.get('build_flags', [])
            if build_flags:
                self.env.Append(CCFLAGS=list(build_flags))
                self.env.Append(CXXFLAGS=list(build_flags))
                print(f"  ✅ Added {len(build_flags)} build flags from compile commands")

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
                "$LINKFLAGS "                               # Then flags
                "$__RPATH $_LIBDIRFLAGS $_LIBFLAGS"        # Libraries last
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
                "-Wl,--end-group",    # End grouping
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
                valid_libs = [lib for lib in compiled_libraries if os.path.exists(lib)]
                if valid_libs:
                    self.env.Append(LIBS=valid_libs)
                    print(f"  ✅ Added {len(valid_libs)} cached static libraries")

            # Apply object files
            compiled_objects = artifacts.get('compiled_objects', [])
            if compiled_objects:
                valid_objects = [obj for obj in compiled_objects if os.path.exists(obj)]
                if valid_objects:
                    self.env.Append(OBJECTS=valid_objects)
                    print(f"  ✅ Added {len(valid_objects)} cached object files")

        except Exception as e:
            print(f"⚠ Warning applying cached artifacts: {e}")

    def create_ini_backup(self):
        """
        Create a backup of platformio.ini before modifying it for the second run.
        
        Returns:
            bool: True if backup was created successfully
        """
        try:
            if os.path.exists(self.platformio_ini):
                os.makedirs(os.path.dirname(self.platformio_ini_backup), exist_ok=True)
                shutil.copy2(self.platformio_ini, self.platformio_ini_backup)
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
            if os.path.exists(self.platformio_ini_backup):
                shutil.copy2(self.platformio_ini_backup, self.platformio_ini)
                os.remove(self.platformio_ini_backup)
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
            with open(self.platformio_ini, 'r', encoding='utf-8') as f:
                lines = f.readlines()

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

            with open(self.platformio_ini, 'w', encoding='utf-8') as f:
                f.writelines(lines)

            return True

        except Exception as e:
            print(f"❌ Error modifying platformio.ini: {e}")
            self.restore_ini_from_backup()
            return False

    def implement_two_run_strategy(self):
        """
        Implements the complete two-run strategy:
        1. First run: LDF active, create comprehensive cache
        2. Second run: LDF off, use cache for all dependencies
        User manually starts second run when desired.
        
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
        
        # First run: Create cache with LDF active
        print("🔄 First run: Creating comprehensive LDF cache...")
        
        # Ensure we have compile commands for build order
        self.environment_specific_compiledb_restart()
        
        # Create build order and analyze artifacts
        build_order_data = self.get_correct_build_order()
        if not build_order_data:
            print("❌ Could not create build order in first run")
            return False
        
        artifacts_data = self.analyze_build_artifacts()
        hash_details = self.get_project_hash_with_details()
        
        # Create comprehensive cache
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
        
        # Save cache
        self.save_combined_cache(combined_data)
        
        # Prepare for second run by setting lib_ldf_mode = off
        if self.modify_platformio_ini_for_second_run('off'):
            print("✅ First run complete - platformio.ini modified for second run")
            print("💡 Run 'pio run' again to use cached dependencies with LDF disabled")
            return True
        else:
            print("❌ Failed to prepare second run")
            return False

    def create_complete_ldf_replacement_with_linker(self):
        """
        Creates a complete LDF replacement solution with optimized linker integration.
        
        Returns:
            bool: True if successful
        """
        print("\n=== Complete LDF Replacement Solution with Linker Optimization ===")
        
        try:
            # Ensure compile_commands.json exists
            self.environment_specific_compiledb_restart()
            
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

    def load_combined_cache(self):
        """
        Loads and validates the combined cache.
        Cache is only invalidated when #include directives change in source files
        or platformio.ini changes (excluding lib_ldf_mode).
        
        Returns:
            dict: Valid cache data or None if invalid
        """
        if not os.path.exists(self.cache_file):
            return None

        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_content = f.read()
            
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
            if not (os.path.exists(build_order.get('build_order_file', '')) and 
                    os.path.exists(build_order.get('link_order_file', ''))):
                print("⚠ Build order files missing")
                return None

            # Check if cached artifacts exist
            artifacts = cache_data.get('artifacts', {})
            missing_artifacts = []
            
            for lib_path in artifacts.get('compiled_libraries', []):
                if not os.path.exists(lib_path):
                    missing_artifacts.append(lib_path)
            
            for obj_path in artifacts.get('compiled_objects', []):
                if not os.path.exists(obj_path):
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
        
        Args:
            target: SCons target (unused)
            source: SCons source (unused)
            env_arg: SCons environment (unused)
            **kwargs: Additional arguments (unused)
        """
        try:
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
                    'ldf_mode': 'off'  # We work with LDF disabled
                }
                
                self.save_combined_cache(combined_data)
                print("💾 LDF cache with build order successfully saved!")
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
        
        Args:
            file_path (str): Path to the file
            
        Returns:
            str: Truncated SHA256 hash or "unreadable" if file cannot be read
        """
        try:
            with open(file_path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()[:16]
        except (IOError, OSError, PermissionError):
            return "unreadable"

    def get_include_relevant_hash(self, file_path):
        """
        Calculate a hash based on relevant #include and #define lines in a source file.
        This is optimized for chain mode which only follows #include directives.
        Chain mode ignores #ifdef, #if, #elif preprocessor directives.
        Only invalidates cache when #include directives actually change.
        
        Args:
            file_path (str): Path to the source file
            
        Returns:
            str: Hash based on include-relevant content for chain mode
        """
        include_lines = []

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith('//'):
                        continue

                    # For chain mode: only #include and relevant #define directives matter
                    # Chain mode ignores #ifdef, #if, #elif, #else preprocessor evaluation
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
        Scan project files and produce a hash based only on LDF-relevant changes.
        Optimized for chain mode - only invalidates cache when #include directives change.
        Excludes lib_ldf_mode changes from platformio.ini to support two-run strategy.
        
        Returns:
            dict: Hash details and scan metadata
        """
        start_time = time.time()
        file_hashes = {}
        hash_data = []  # Only for LDF-relevant hashes

        generated_cpp = os.path.basename(self.project_dir).lower() + ".ino.cpp"

        # platformio.ini is always relevant for LDF, but exclude lib_ldf_mode changes
        if os.path.exists(self.platformio_ini):
            try:
                with open(self.platformio_ini, 'r', encoding='utf-8') as f:
                    ini_content = f.read()

                # CRITICAL: Remove lib_ldf_mode before hashing to support two-run strategy
                filtered_content = re.sub(r'lib_ldf_mode\s*=\s*\w+\n?', '', ini_content)
                ini_hash = hashlib.sha256(filtered_content.encode()).hexdigest()[:16]
                hash_data.append(ini_hash)  # Relevant for LDF
                file_hashes['platformio.ini'] = ini_hash

            except Exception as e:
                print(f"⚠ Error reading platformio.ini: {e}")

        # Define scan directories
        scan_dirs = []

        if os.path.exists(self.src_dir):
            scan_dirs.append(('source', self.src_dir))

        lib_dir = os.path.join(self.project_dir, "lib")
        if os.path.exists(lib_dir) and not self.is_platformio_path(lib_dir):
            scan_dirs.append(('library', lib_dir))

        include_dir = os.path.join(self.project_dir, "include")
        if os.path.exists(include_dir) and not self.is_platformio_path(include_dir):
            scan_dirs.append(('include', include_dir))

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
                            relevant_files.append(file)

                    if relevant_files:
                        for file in relevant_files:
                            file_path = os.path.join(root, file)
                            file_ext = os.path.splitext(file)[1].lower()

                            if file_ext in self.SOURCE_EXTENSIONS or file_ext in self.HEADER_EXTENSIONS:
                                file_hash = self.get_include_relevant_hash(file_path)
                            else:
                                file_hash = self._get_file_hash(file_path)

                            if file_hash != "unreadable":
                                hash_data.append(file_hash)
                                total_relevant += 1

                            relative_path = os.path.relpath(file_path, self.project_dir)
                            file_hashes[relative_path] = file_hash

            except Exception as e:
                print(f"⚠ Error scanning {scan_dir}: {e}")

        # Calculate final hash
        combined_content = ''.join(sorted(hash_data))
        final_hash = hashlib.sha256(combined_content.encode()).hexdigest()[:32]

        scan_duration = time.time() - scan_start_time
        total_duration = time.time() - start_time

        print(f"📊 Scan completed: {total_scanned} files scanned, {total_relevant} relevant for LDF")
        print(f"⏱ Scan time: {scan_duration:.2f}s, Total time: {total_duration:.2f}s")
        print(f"🔑 Project hash: {final_hash}")

        return {
            'final_hash': final_hash,
            'file_hashes': file_hashes,
            'scan_stats': {
                'total_scanned': total_scanned,
                'total_relevant': total_relevant,
                'scan_duration': scan_duration,
                'total_duration': total_duration
            }
        }

    def compute_signature(self, cache_data):
        """
        Compute a simplified signature for cache validation.
        Simplified to avoid constant cache invalidation.
        
        Args:
            cache_data (dict): Cache data to sign
            
        Returns:
            str: Computed signature based on environment and project hash
        """
        try:
            env_name = cache_data.get('env_name', '')
            project_hash = cache_data.get('project_hash', '')
            return hashlib.sha256(f"{env_name}_{project_hash}".encode()).hexdigest()[:16]
        except Exception:
            return "invalid"


# Initialize the LDF cache optimizer
ldf_optimizer = LDFCacheOptimizer(env)

# Check LDF mode compatibility
if not ldf_optimizer.validate_ldf_mode_compatibility():
    print("❌ Incompatible LDF mode - script disabled")
    exit()

# Implement the two-run strategy
try:
    success = ldf_optimizer.implement_two_run_strategy()
    if success:
        print("✅ Two-run LDF cache strategy completed successfully")
    else:
        print("⚠ Two-run strategy failed, using standard LDF")
except Exception as e:
    print(f"❌ Critical error in two-run strategy: {e}")
    ldf_optimizer.fallback_to_standard_ldf()

# Add post-build hook to save cache after successful build
env.AddPostAction("$BUILD_DIR/${PROGNAME}.elf", ldf_optimizer.save_ldf_cache_with_build_order)
