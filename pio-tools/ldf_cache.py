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
        
        # Idedata and artifacts
        self.idedata_dir = os.path.join(self.project_dir, ".pio", "ldf_cache")
        self.idedata_file = os.path.join(self.project_dir, ".pio", "ldf_cache", f"idedata_{self.env_name}.json")
        self.artifacts_cache_dir = os.path.join(self.project_dir, ".pio", "ldf_cache", "artifacts", self.env_name)
        
        self.ALL_RELEVANT_EXTENSIONS = self.HEADER_EXTENSIONS | self.SOURCE_EXTENSIONS | self.CONFIG_EXTENSIONS
        self.real_packages_dir = os.path.join(ProjectConfig.get_instance().get("platformio", "packages_dir"))

        if not os.path.exists(self.idedata_file):
            self.env.AddPostAction("$BUILD_DIR/${PROGNAME}.elf", self.generate_idedata)

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
        # 1. Load compile_commands.json for correct order
        if not os.path.exists(self.compile_commands_file):
            print(f"⚠ compile_commands_{self.env_name}.json not found")
            return None

        try:
            with open(self.compile_commands_file, "r") as f:
                compile_db = json.load(f)
        except Exception as e:
            print(f"✗ Error reading compile_commands.json: {e}")
            return None

        # 2. Map source files to object files
        ordered_objects = []
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

        # 3. Save build order
        try:
            with open(self.build_order_file, "w") as f:
                for obj_info in ordered_objects[:-1]:  # Exclude last element
                    f.write(f"{obj_info['source']}\n")

            # 4. Create correct linker order
            with open(self.link_order_file, "w") as f:
                for obj_info in ordered_objects[:-1]:  # Exclude last element
                    f.write(f"{obj_info['object']}\n")

            print(f"✓ Created: correct_build_order_{self.env_name}.txt")
            print(f"✓ Created: correct_link_order_{self.env_name}.txt")
            
            return {
                'ordered_objects': ordered_objects,
                'build_order_file': self.build_order_file,
                'link_order_file': self.link_order_file
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
            
            # 1. Collect all object files in correct order
            object_files = []
            for obj_info in ordered_objects[:-1]:  # Exclude last element
                obj_path = obj_info['object']
                if os.path.exists(obj_path):
                    object_files.append(obj_path)

            if not object_files:
                print("⚠ No valid object files found")
                return False

            # 2. Set OBJECTS in correct order
            self.env.Replace(OBJECTS=object_files)
            
            # 3. CRITICAL: Implement correct linker order
            self._apply_correct_linker_order(object_files)
            
            print(f"✅ Build order applied: {len(object_files)} object files")
            print(f"✅ Linker order configured for correct symbol resolution")
            
            return True

        except Exception as e:
            print(f"✗ Error applying build order: {e}")
            return False

    def _apply_correct_linker_order(self, object_files):
        """
        Implements correct linker order based on PlatformIO documentation.
        Solves symbol resolution problems with linker scripts.
        
        Args:
            object_files (list): List of object files in correct order
        """
        try:
            # 1. Save current LINKFLAGS
            current_linkflags = self.env.get('LINKFLAGS', [])
            
            # 2. Create optimized linker command structure
            # Based on GitHub Issue #3208: Object files BEFORE linker flags
            custom_linkcom = (
                "$LINK -o $TARGET "
                "${_long_sources_hook(__env__, SOURCES)} "  # Objects first
                "$LINKFLAGS "                               # Then flags
                "$__RPATH $_LIBDIRFLAGS $_LIBFLAGS"        # Libraries last
            )
            
            # 3. Apply correct linker order
            self.env.Replace(LINKCOM=custom_linkcom)
            
            # 4. Optimize linker flags for symbol resolution
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
            
            # 5. Set optimized linker flags
            self.env.Replace(LINKFLAGS=optimized_linkflags)
            
            # 6. Special handling for linker scripts (if present)
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

    def apply_ldf_cache_with_build_order(self, cache_data):
        """
        Extended application of LDF cache with build order integration.
        Combines library dependencies with correct build order.
        
        Args:
            cache_data (dict): Cache data containing LDF results and build order
            
        Returns:
            bool: True if application was successful
        """
        try:
            ldf_results = cache_data.get('ldf_results', {})
            build_order = cache_data.get('build_order', {})
            
            if not ldf_results or not build_order:
                return False

            print("🔧 Applying LDF cache with build order integration...")
            
            # 1. Apply standard LDF cache
            success_ldf = self.apply_ldf_cache_complete({'ldf_results': ldf_results})
            
            # 2. Apply build order with linker optimization
            success_build_order = self.apply_build_order_to_environment(build_order)
            
            # 3. Integrate library paths with build order
            if success_ldf and success_build_order:
                self._integrate_libraries_with_build_order(ldf_results, build_order)
                
            return success_ldf and success_build_order

        except Exception as e:
            print(f"✗ Error in LDF cache with build order: {e}")
            return False

    def _integrate_libraries_with_build_order(self, ldf_results, build_order):
        """
        Integrates library dependencies with correct build order.
        Ensures libraries are linked in the right order.
        
        Args:
            ldf_results (dict): LDF results containing library information
            build_order (dict): Build order data
        """
        try:
            # 1. Collect all library paths from LDF results
            compiled_libraries = ldf_results.get('compiled_libraries', [])
            
            # 2. Sort libraries based on build order dependencies
            ordered_libraries = self._sort_libraries_by_dependencies(compiled_libraries, build_order)
            
            # 3. Apply sorted libraries
            if ordered_libraries:
                # Replace LIBS with correct order
                current_libs = self.env.get('LIBS', [])
                
                # Remove old library paths
                filtered_libs = [lib for lib in current_libs 
                               if not any(lib_path in str(lib) for lib_path in compiled_libraries)]
                
                # Add sorted libraries
                final_libs = filtered_libs + ordered_libraries
                self.env.Replace(LIBS=final_libs)
                
                print(f"📚 {len(ordered_libraries)} libraries integrated in correct order")
                
        except Exception as e:
            print(f"⚠ Warning during library integration: {e}")

    def _sort_libraries_by_dependencies(self, libraries, build_order):
        """
        Sorts libraries based on dependencies from build order.
        
        Args:
            libraries (list): List of library paths
            build_order (dict): Build order data
            
        Returns:
            list: Sorted list of library paths
        """
        try:
            # Simple sorting based on filename matching
            ordered_objects = build_order.get('ordered_objects', [])
            
            # Create mapping from library names to paths
            lib_mapping = {}
            for lib_path in libraries:
                lib_name = os.path.basename(lib_path).replace('lib', '').replace('.a', '')
                lib_mapping[lib_name.lower()] = lib_path
            
            # Sort based on order in build order
            sorted_libraries = []
            used_libs = set()
            
            for obj_info in ordered_objects:
                source_file = obj_info.get('source', '')
                
                # Try to extract library name from source path
                for lib_name, lib_path in lib_mapping.items():
                    if (lib_name in source_file.lower() and 
                        lib_path not in used_libs):
                        sorted_libraries.append(lib_path)
                        used_libs.add(lib_path)
                        break
            
            # Add remaining libraries
            for lib_path in libraries:
                if lib_path not in used_libs:
                    sorted_libraries.append(lib_path)
            
            return sorted_libraries
            
        except Exception as e:
            print(f"⚠ Fallback to original library order: {e}")
            return libraries

    def create_complete_ldf_replacement_with_linker(self):
        """
        Creates a complete LDF replacement solution with optimized linker integration.
        
        Returns:
            bool: True if successful
        """
        print("\n=== Complete LDF Replacement Solution with Linker Optimization ===")
        
        try:
            # 1. Ensure compile_commands.json exists
            self.environment_specific_compiledb_restart()
            
            # 2. Create build order with linker integration
            build_order_data = self.get_correct_build_order()
            if not build_order_data:
                print("❌ Could not create build order")
                return self.fallback_to_standard_ldf()

            # 3. Load and process idedata.json
            ldf_results = self.read_existing_idedata()
            if not ldf_results:
                print("❌ Could not process idedata.json")
                return self.fallback_to_standard_ldf()

            # 4. Combine with optimized linker logic
            combined_data = {
                'ldf_results': ldf_results,
                'build_order': build_order_data,
                'project_hash': self.get_project_hash_with_details()['final_hash'],
                'timestamp': datetime.datetime.now().isoformat(),
                'env_name': self.env_name,
                'linker_optimized': True  # Flag for linker optimization
            }

            # 5. Apply everything with linker optimization
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

            # Validate signature
            expected_signature = cache_data.get('signature')
            actual_signature = self.compute_signature(cache_data)
            
            if expected_signature != actual_signature:
                print("⚠ Cache invalid: Signature mismatch")
                return None

            # Validate environment
            if cache_data.get('env_name') != self.env_name:
                print(f"🔄 Environment changed: {cache_data.get('env_name')} -> {self.env_name}")
                return None

            # Check if build order files exist
            build_order = cache_data.get('build_order', {})
            if not (os.path.exists(build_order.get('build_order_file', '')) and 
                    os.path.exists(build_order.get('link_order_file', ''))):
                print("⚠ Build order files missing")
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
            
            # Load LDF data
            hash_details = self.get_project_hash_with_details()
            ldf_results = self.read_existing_idedata()

            if ldf_results and build_order_data:
                combined_data = {
                    'ldf_results': ldf_results,
                    'build_order': build_order_data,
                    'project_hash': hash_details['final_hash'],
                    'hash_details': hash_details['file_hashes'],
                    'env_name': self.env_name,
                    'timestamp': datetime.datetime.now().isoformat(),
                    'pio_version': getattr(self.env, "PioVersion", lambda: "unknown")(),
                    'ldf_mode': 'off'  # We work with LDF disabled
                }
                
                self.save_combined_cache(combined_data)
                self.write_ldf_cache_ini(ldf_results)
                print("💾 LDF cache with build order successfully saved!")
            else:
                print("❌ Could not create LDF data or build order")

        except Exception as e:
            print(f"✗ Error saving LDF cache with build order: {e}")
            import traceback
            traceback.print_exc()

    def generate_idedata(self, source, target, env):
        """
        Generate idedata.json directly using PlatformIO's internal method.
        
        Args:
            source: SCons source
            target: SCons target
            env: SCons environment
        """
        if not os.path.exists(self.idedata_dir):
            os.makedirs(self.idedata_dir)

        data = env.DumpIntegrationData(env)
        with open(
            env.subst(self.idedata_file),
            mode="w",
            encoding="utf8",
        ) as fp:
            json.dump(data, fp)

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

    def create_ini_backup(self):
        """
        Create a backup of platformio.ini.
        
        Returns:
            bool: True if backup was created successfully
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
        
        Returns:
            bool: True if restore was successful
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
        Modify lib_ldf_mode in platformio.ini.
        
        Args:
            new_ldf_mode (str): New LDF mode value
            
        Returns:
            bool: True if modification was successful
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
        
        Returns:
            dict: Hash details and scan metadata
        """
        start_time = time.time()
        file_hashes = {}
        hash_data = []  # Only for LDF-relevant hashes

        generated_cpp = os.path.basename(self.project_dir).lower() + ".ino.cpp"

        # platformio.ini is always relevant for LDF
        if os.path.exists(self.platformio_ini):
            try:
                with open(self.platformio_ini, 'r', encoding='utf-8') as f:
                    ini_content = f.read()

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
                            relevant_files.append((file, file_ext))
                            total_relevant += 1

                    for file, file_ext in relevant_files:
                        if file == generated_cpp:
                            continue

                        file_path = os.path.join(root, file)

                        # Selective hash usage - only include LDF-relevant changes for chain mode
                        if file_ext in self.SOURCE_EXTENSIONS:
                            # Source files: Only #include relevant parts (chain mode optimization)
                            file_hash = self.get_include_relevant_hash(file_path)
                            file_hashes[file_path] = file_hash
                            hash_data.append(file_hash)  # Include in final hash

                        elif file_ext in self.HEADER_EXTENSIONS and dir_type == 'source':
                            # Header files: Only from src/ directory (local headers)
                            file_hash = self._get_file_hash(file_path)
                            file_hashes[file_path] = file_hash
                            hash_data.append(file_hash)  # Include in final hash

                        elif file_ext in self.CONFIG_EXTENSIONS and dir_type == 'library':
                            # Config files: Only from lib/ directory (library configs)
                            file_hash = self._get_file_hash(file_path)
                            file_hashes[file_path] = file_hash
                            hash_data.append(file_hash)  # Include in final hash

                        else:
                            # All other files: Store for metadata but don't include in final hash
                            if file_ext in self.HEADER_EXTENSIONS:
                                file_hash = self._get_file_hash(file_path)
                            elif file_ext in self.CONFIG_EXTENSIONS:
                                file_hash = self._get_file_hash(file_path)
                            else:
                                continue

                            file_hashes[file_path] = file_hash
                            # Do NOT add to hash_data - not relevant for cache invalidation in chain mode

            except (IOError, OSError, PermissionError) as e:
                print(f"⚠ Warning: Could not scan directory {scan_dir}: {e}")
                continue

        scan_elapsed = time.time() - scan_start_time
        final_hash = hashlib.sha256(''.join(hash_data).encode()).hexdigest()[:16]
        total_elapsed = time.time() - start_time

        print(f"🔍 Chain mode optimized scanning completed in {total_elapsed:.2f}s")
        print(f"🔍 Scan complete: {total_scanned} files scanned, {total_relevant} relevant and hashed")
        print(f"🔍 Cache hash based on {len(hash_data)} LDF-relevant files for chain mode")

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

    def read_existing_idedata(self):
        """
        Read idedata.json and process its structure.
        
        Returns:
            dict: Processed idedata structure or None if failed
        """
        try:
            if not os.path.exists(self.idedata_file):
                print(f"❌ idedata.json not found: {self.idedata_file}")
                return None

            with open(self.idedata_file, 'r') as f:
                idedata = json.loads(f.read())

            return self._process_real_idedata_structure(idedata)

        except Exception as e:
            print(f"❌ Error reading idedata.json: {e}")
            return None

    def _process_real_idedata_structure(self, idedata):
        """
        Process idedata.json structure and resolve all package placeholders.
        Copies artifacts to cache and adjusts paths.
        
        Args:
            idedata (dict): Raw idedata structure
            
        Returns:
            dict: Processed LDF cache structure
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

        # Process library source directories
        libsource_dirs = idedata.get('libsource_dirs', [])
        for lib_dir in libsource_dirs:
            resolved_lib_dir = self.resolve_pio_placeholders(lib_dir)
            ldf_cache['libsource_dirs'].append(resolved_lib_dir)

            if 'lib/' in lib_dir and self.project_dir in lib_dir:
                lib_deps_entry = f"./lib/{os.path.basename(lib_dir)}"
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

        # Process include paths
        includes_build = idedata.get('includes', {}).get('build', [])
        includes_compatlib = idedata.get('includes', {}).get('compatlib', [])
        all_includes = includes_build + includes_compatlib

        for include_path in all_includes:
            resolved_path = self.resolve_pio_placeholders(include_path)
            if resolved_path not in ldf_cache['include_paths']:
                ldf_cache['include_paths'].append(self.resolve_pio_placeholders(include_path))

        # Process defines
        defines = idedata.get('defines', [])
        for define in defines:
            ldf_cache['defines'].append(define)

        # Process build flags
        cc_flags = idedata.get('cc_flags', [])
        cxx_flags = idedata.get('cxx_flags', [])
        all_flags = cc_flags + cxx_flags

        for flag in all_flags:
            resolved_flag = self.resolve_pio_placeholders(flag)
            if resolved_flag not in ldf_cache['build_flags']:
                ldf_cache['build_flags'].append(resolved_flag)

        # Process compiled artifacts - IMPORTANT CHANGE HERE
        lib_build_dir = os.path.join(self.project_dir, '.pio', 'build', self.env_name)

        if lib_build_dir and os.path.exists(lib_build_dir):
            # Copy artifacts to cache
            path_mapping = self.copy_artifacts_to_cache(lib_build_dir)

            # Collect .a and .o files (from cache paths)
            for original_path, cache_path in path_mapping.items():
                if original_path.endswith('.a'):
                    ldf_cache['compiled_libraries'].append(cache_path)
                elif original_path.endswith('.o'):
                    ldf_cache['compiled_objects'].append(cache_path)

            print(f"📦 Found {len(ldf_cache['compiled_libraries'])} Libraries (*.a) files in cache")
            print(f"📦 Found {len(ldf_cache['compiled_objects'])} Object files (*.o) in cache")

        return ldf_cache

    def compute_signature(self, cache_data):
        """
        Compute a hash signature for the cache data.
        
        Args:
            cache_data (dict): Cache data to sign
            
        Returns:
            str: SHA256 signature
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
        
        Args:
            target: SCons target (unused)
            source: SCons source (unused)
            env_arg: SCons environment (unused)
            **kwargs: Additional arguments (unused)
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
                    'ldf_cache_ini': self.ldf_cache_ini,
                    'ldf_mode': 'chain'  # This cache is designed for chain mode only
                }

                cache_data['signature'] = self.compute_signature(cache_data)

                os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)

                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    f.write("# LDF Cache - Complete Build Environment with .a/.o tracking\n")
                    f.write("# Optimized for lib_ldf_mode = chain\n")
                    f.write("# Generated as Python dict\n\n")
                    f.write("cache_data = \\\n")
                    f.write(pprint.pformat(cache_data, indent=2, width=120))
                    f.write("\n")

                print(f"💾 LDF Cache saved successfully for chain mode!")

            else:
                print("❌ No valid LDF results found in idedata.json")

        except Exception as e:
            print(f"✗ Error saving LDF cache: {e}")
            import traceback
            traceback.print_exc()

    def load_and_validate_cache(self):
        """
        Load and validate the LDF cache. If invalid, clear it.
        
        Returns:
            dict: Valid cache data or None if invalid
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

            # Validate PlatformIO version
            current_pio_version = getattr(self.env, "PioVersion", lambda: "unknown")()
            if cache_data.get('pio_version') != current_pio_version:
                print(f"⚠ Cache invalid: PlatformIO version changed from {cache_data.get('pio_version')} to {current_pio_version}")
                self.clear_ldf_cache()
                return None

            # Validate LDF mode compatibility
            cached_ldf_mode = cache_data.get('ldf_mode', 'chain')
            if cached_ldf_mode != 'chain':
                print(f"⚠ Cache invalid: Cache was created for LDF mode '{cached_ldf_mode}', but this optimizer requires 'chain' mode")
                self.clear_ldf_cache()
                return None

            # Validate signature
            expected_signature = cache_data.get('signature')
            actual_signature = self.compute_signature(cache_data)

            if expected_signature != actual_signature:
                print("⚠ Cache invalid: Signature mismatch. Possible file tampering or corruption.")
                self.clear_ldf_cache()
                return None

            # Validate environment
            if cache_data.get('pioenv') != self.env['PIOENV']:
                print(f"🔄 Environment changed: {cache_data.get('pioenv')} -> {self.env['PIOENV']}")
                self.clear_ldf_cache()
                return None

            # Validate build artifacts exist IN CACHE - IMPORTANT CHANGE
            ldf_results = cache_data.get('ldf_results', {})
            missing_artifacts = []

            # Check cache artifacts instead of build artifacts
            for lib_path in ldf_results.get('compiled_libraries', []):
                if not os.path.exists(lib_path):  # lib_path is already cache path
                    missing_artifacts.append(lib_path)

            for obj_path in ldf_results.get('compiled_objects', []):
                if not os.path.exists(obj_path):  # obj_path is already cache path
                    missing_artifacts.append(obj_path)

            if missing_artifacts:
                print(f"⚠ Cache invalid: {len(missing_artifacts)} cached artifacts missing")
                print(f"  First missing: {missing_artifacts[0]}")
                self.clear_ldf_cache()
                return None

            print("✅ Cache valid - all cached artifacts present")
            print(f"  Libraries: {len(ldf_results.get('compiled_libraries', []))}")
            print(f"  Objects: {len(ldf_results.get('compiled_objects', []))}")

            return cache_data

        except Exception as e:
            print(f"⚠ Cache validation failed: {e}")
            self.clear_ldf_cache()
            return None

    def clear_ldf_cache(self):
        """
        Delete the LDF cache file and artifacts for the current environment.
        """
        deleted_something = False

        # Delete cache file
        if os.path.exists(self.cache_file):
            try:
                os.remove(self.cache_file)
                print("✓ LDF Cache file deleted")
                deleted_something = True
            except Exception as e:
                print(f"✗ Error deleting cache file: {e}")

        # Delete artifacts cache
        if os.path.exists(self.artifacts_cache_dir):
            try:
                shutil.rmtree(self.artifacts_cache_dir)
                print("✓ LDF Cache artifacts deleted")
                deleted_something = True
            except Exception as e:
                print(f"✗ Error deleting cache artifacts: {e}")

        if not deleted_something:
            print("ℹ No LDF Cache present")

    def write_ldf_cache_ini(self, ldf_results):
        """
        Write LDF cache configuration to ldf_cache.ini for PlatformIO extra_configs.
        
        Args:
            ldf_results (dict): LDF results to write
        """
        ini_lines = [
            f"[env:{self.env['PIOENV']}]",
            "lib_deps ="
        ]

        for lib_dep in ldf_results['lib_deps_entries']:
            ini_lines.append(f"  {lib_dep}")

        ini_lines.append("")
        ini_lines.append("build_flags = ${env.build_flags}")

        for include_path in ldf_results['include_paths']:
            ini_lines.append(f"  -I\"{include_path}\"")

        ini_content = "\n".join(ini_lines)

        with open(self.ldf_cache_ini, "w", encoding="utf-8") as f:
            f.write(ini_content)

        print(f"📝 Wrote LDF cache config to {self.ldf_cache_ini}")

    def apply_ldf_cache_complete(self, cache_data):
        """
        Apply all cached LDF results to the SCons environment, resolving all placeholders.
        
        Args:
            cache_data (dict): Cache data containing LDF results
            
        Returns:
            bool: True if application was successful
        """
        try:
            ldf_results = cache_data.get('ldf_results', {})

            if not ldf_results:
                return False

            print("🔧 Restoring complete SCons environment from chain mode cache...")

            self._apply_static_libraries(ldf_results)
            self._apply_object_files(ldf_results)
            self._apply_include_paths_and_defines(ldf_results)
            self._apply_build_flags_systematically(ldf_results)

            print("✅ Complete SCons environment restored from chain mode cache")
            return True

        except Exception as e:
            print(f"✗ Error in complete cache restoration: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _apply_static_libraries(self, ldf_results):
        """
        Add all static libraries (.a) to LIBS, resolving any placeholders.
        
        Args:
            ldf_results (dict): LDF results containing compiled libraries
        """
        compiled_libraries = [self.resolve_pio_placeholders(p) for p in ldf_results.get('compiled_libraries', [])]

        valid_libs = []
        for lib_path in compiled_libraries:
            if os.path.exists(lib_path):
                lib_name = os.path.basename(lib_path)
                if lib_name.startswith('lib') and lib_name.endswith('.a'):
                    valid_libs.append(lib_path)

        if valid_libs:
            self.env.Append(LIBS=valid_libs)
            print(f"  ✅ Added {len(valid_libs)} static libraries to LIBS")

    def _apply_object_files(self, ldf_results):
        """
        Add all object files to the SCons OBJECTS environment.
        
        Args:
            ldf_results (dict): LDF results containing compiled objects
        """
        compiled_objects = [self.resolve_pio_placeholders(p) for p in ldf_results.get('compiled_objects', [])]
        valid_objects = [obj for obj in compiled_objects if os.path.exists(obj)]

        if not valid_objects:
            print("  No valid object files found")
            return

        self.env.Append(OBJECTS=valid_objects)
        print(f"  ✅ Added {len(valid_objects)} object files to OBJECTS")

        # Debug output of first few object files
        for obj_path in valid_objects[:3]:
            print(f"  -> {os.path.basename(obj_path)}")

        if len(valid_objects) > 3:
            print(f"  ... and {len(valid_objects) - 3} more object files")

    def _apply_build_flags_systematically(self, ldf_results):
        """
        Systematically apply build flags to the SCons environment, resolving any placeholders.
        
        Args:
            ldf_results (dict): LDF results containing build flags
        """
        build_flags = [self.resolve_pio_placeholders(flag) for flag in ldf_results.get('build_flags', [])]

        if not build_flags:
            return

        # Categorize flags
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

        # Apply categorized flags
        if cpp_paths:
            existing_paths = [str(p) for p in self.env.get('CPPPATH', [])]
            new_paths = [p for p in cpp_paths if p not in existing_paths]
            if new_paths:
                self.env.Append(CPPPATH=new_paths)
                print(f"  Added {len(new_paths)} include paths from build flags")

        if lib_paths:
            existing_libpaths = [str(p) for p in self.env.get('LIBPATH', [])]
            new_libpaths = [p for p in lib_paths if p not in existing_libpaths]
            if new_libpaths:
                self.env.Append(LIBPATH=new_libpaths)
                print(f"   Added {len(new_libpaths)} library paths from build flags")
#        if cc_flags:
#            self.env.Append(CCFLAGS=cc_flags)
#            print(f"   Added {len(cc_flags)} C compiler flags")
#        if cxx_flags:
#            self.env.Append(CXXFLAGS=cxx_flags)
#            print(f"   Added {len(cxx_flags)} C++ compiler flags")
#        if link_flags:
#            self.env.Append(LINKFLAGS=link_flags)
#            print(f"   Added {len(link_flags)} linker flags")

    def _apply_include_paths_and_defines(self, ldf_results):
        """
        Add all include paths and defines to the SCons environment, resolving any placeholders.
        
        Args:
            ldf_results (dict): LDF results containing include paths and defines
        """
        # Apply include paths
        include_paths = [self.resolve_pio_placeholders(p) for p in ldf_results.get('include_paths', [])]
        if include_paths:
            existing_includes = [str(path) for path in self.env.get('CPPPATH', [])]
            new_includes = [inc for inc in include_paths
                           if os.path.exists(inc) and inc not in existing_includes]
            if new_includes:
                self.env.Append(CPPPATH=new_includes)
                print(f"   Added {len(new_includes)} include paths")

        # Apply defines
        defines = ldf_results.get('defines', [])
        if defines:
            existing_defines = [str(d) for d in self.env.get('CPPDEFINES', [])]
            new_defines = [d for d in defines if str(d) not in existing_defines]
            if new_defines:
                self.env.Append(CPPDEFINES=new_defines)
                print(f"   Added {len(new_defines)} preprocessor defines")

def setup_ldf_caching(self):
    """
    Main entry point for LDF caching with build order management.
    """
    print("\n=== LDF Cache Optimizer with Build Order Management ===")

    # Validate LDF mode compatibility
    if not self.validate_ldf_mode_compatibility():
        print("❌ LDF mode incompatible - aborting")
        return

    # Always use the complete replacement function with linker optimization
    print("🔧 Using complete LDF replacement with linker optimization")
    
    # Switch to off mode and apply complete solution
    if self.modify_platformio_ini_simple("off"):
        success = self.create_complete_ldf_replacement_with_linker()
        
        if success:
            self.env.AddPostAction("checkprogsize", lambda *args: self.restore_ini_from_backup())
        else:
            self.restore_ini_from_backup()
            self.env.AddPostAction("checkprogsize", self.save_ldf_cache_with_build_order)
    else:
        print("❌ Could not modify platformio.ini")
        self.env.AddPostAction("checkprogsize", self.save_ldf_cache_with_build_order)

    print("=" * 80)


def clear_ldf_cache():
    """
    Delete the LDF cache file and artifacts for the current environment.
    """
    project_dir = env.subst("$PROJECT_DIR")
    env_name = env.get("PIOENV")
    cache_file = os.path.join(project_dir, ".pio", "ldf_cache", f"ldf_cache_{env_name}.py")
    artifacts_cache_dir = os.path.join(project_dir, ".pio", "ldf_cache", "artifacts", env_name)

    deleted_something = False

    if os.path.exists(cache_file):
        try:
            os.remove(cache_file)
            print("✓ LDF Cache file deleted")
            deleted_something = True
        except Exception as e:
            print(f"✗ Error deleting cache file: {e}")

    if os.path.exists(artifacts_cache_dir):
        try:
            shutil.rmtree(artifacts_cache_dir)
            print("✓ LDF Cache artifacts deleted")
            deleted_something = True
        except Exception as e:
            print(f"✗ Error deleting cache artifacts: {e}")

    if not deleted_something:
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
            print(f"LDF Mode:     {cache_data.get('ldf_mode', 'unknown')}")
            print(f"Created:      {cache_data.get('timestamp', 'unknown')}")
            print(f"PIO Version:  {cache_data.get('pio_version', 'unknown')}")
            print(f"Project Hash: {cache_data.get('project_hash', 'unknown')}")
            print(f"Libraries:    {len(ldf_results.get('compiled_libraries', []))}")
            print(f"Objects:      {len(ldf_results.get('compiled_objects', []))}")
            print(f"Include Paths: {len(ldf_results.get('include_paths', []))}")
            print(f"Defines:      {len(ldf_results.get('defines', []))}")
            print("=" * 40)
        except Exception as e:
            print(f"✗ Error reading cache info: {e}")
    else:
        print("ℹ No LDF Cache present")

# Initialize and setup LDF caching
ldf_optimizer = LDFCacheOptimizer(env)
ldf_optimizer.setup_ldf_caching()
