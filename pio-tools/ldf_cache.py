"""
PlatformIO Advanced Script for intelligent LDF caching with build order management.
Integrated with PlatformIO Core functions for maximum efficiency.

This script implements a sophisticated two-phase caching system:
1. First run: Performs verbose build, collects dependencies, creates cache
2. Second run: Applies cached dependencies with lib_ldf_mode=off for faster builds

Features:
- Intelligent cache invalidation based on file hashes
- Build order preservation for correct symbol resolution
- Native PlatformIO Core integration
- Automatic compile_commands.json generation
- Zero-configuration operation

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
import shlex
import fnmatch
import atexit
from pathlib import Path
from platformio.project.config import ProjectConfig
from platformio.builder.tools.piobuild import SRC_HEADER_EXT, SRC_C_EXT, SRC_CXX_EXT, SRC_ASM_EXT, SRC_BUILD_EXT
from SCons.Script import COMMAND_LINE_TARGETS, DefaultEnvironment
from SCons.Node import FS
from dataclasses import dataclass
from typing import Optional

# Import PlatformIO Core piolib functions for native functionality
from platformio.builder.tools.piolib import (
    LibBuilderBase, 
    ProjectAsLibBuilder, 
    LibBuilderFactory,
    GetLibBuilders
)

# INFO PlatformIO Core constants
# SRC_HEADER_EXT = ["h", "hpp", "hxx", "h++", "hh", "inc", "tpp", "tcc"]
# SRC_ASM_EXT = ["S", "spp", "SPP", "sx", "s", "asm", "ASM"]
# SRC_C_EXT = ["c"]
# SRC_CXX_EXT = ["cc", "cpp", "cxx", "c++"]
# SRC_BUILD_EXT = SRC_C_EXT + SRC_CXX_EXT + SRC_ASM_EXT

# Global run state management - determine paths and cache locations
project_dir = env.subst("$PROJECT_DIR")
env_name = env.subst("$PIOENV")
compiledb_path = Path(project_dir) / ".pio" / "compiledb" / f"compile_commands_{env_name}.json"
logfile_path = Path(project_dir) / ".pio" / "compiledb" / f"compile_commands_{env_name}.log"
cache_base = Path(project_dir) / ".pio" / "ldf_cache"
cache_file = cache_base / f"ldf_cache_{env_name}.py"
build_dir = Path(env.subst("$BUILD_DIR"))
src_dir = Path(env.subst("$PROJECT_SRC_DIR"))

# Ensure log directory exists
logfile_path.parent.mkdir(parents=True, exist_ok=True)

def is_first_run_needed():
    """
    Determines if the first run (full verbose build) is needed based on file dependencies.
    
    Checks for essential build artifacts and compile database existence.
    
    Returns:
        bool: True if first run is needed, False if cache can be used
    """
    # Check if compile commands database exists and is not empty
    if not compiledb_path.exists() or compiledb_path.stat().st_size == 0:
        return True

    lib_dirs = list(build_dir.glob("lib*"))
    if not lib_dirs:
        return False

    return False

def is_build_environment_ready():
    """
    Checks if the build environment is complete and ready for cache application.
    
    Validates that all necessary build artifacts exist for second run.
    
    Returns:
        bool: True if build environment is ready for cache application
    """
    # Compile database must exist
    if not compiledb_path.exists():
        return False

    # Source build directory must exist
    if not (build_dir / "src").exists():
        return False

    # At least one library directory must exist
    lib_dirs = list(build_dir.glob("lib*"))
    if not lib_dirs:
        return False

    return True

def should_trigger_verbose_build():
    """
    Determines if a verbose build should be triggered for first run.
    
    Considers environment variables, cache existence, and build targets.
    
    Returns:
        bool: True if verbose build should be triggered
    """
    # Prevent recursive calls
    if os.environ.get('_PIO_RECURSIVE_CALL') == 'true':
        return False
    if os.environ.get('PLATFORMIO_SETTING_FORCE_VERBOSE') == 'true':
        return False
    
    # Check for return code from previous recursive call
    if os.environ.get('_PIO_REC_CALL_RETURN_CODE') is not None:
        return False

    # If cache exists, no need for verbose build
    if cache_file.exists():
        return False

    # Only trigger for build-related targets
    current_targets = COMMAND_LINE_TARGETS[:]
    is_build_target = (
        not current_targets or
        any(target in ["build", "buildprog"] for target in current_targets)
    )
    if not is_build_target:
        return False

    return is_first_run_needed()

# Integrated log2compdb components for compile_commands.json generation
DIRCHANGE_PATTERN = re.compile(r"(?P<action>\w+) directory '(?P<path>.+)'")
INFILE_PATTERN = re.compile(r"(?P<path>.+\.(cpp|cxx|cc|c|hpp|hxx|h))", re.IGNORECASE)

@dataclass
class CompileCommand:
    """
    Represents a single compile command extracted from build logs.
    
    Attributes:
        file: Source file path
        output: Output object file path
        directory: Working directory for compilation
        arguments: Complete compiler command line arguments
    """
    file: str
    output: str
    directory: str
    arguments: list

    @classmethod
    def from_cmdline(cls, cc_cmd: Path, cmd_args: list[str], directory=None) -> Optional["CompileCommand"]:
        """
        Create a CompileCommand from a command line.
        
        Parses compiler command line to extract source file, output file, and arguments.
        
        Args:
            cc_cmd: Path to the compiler executable
            cmd_args: List of command line arguments
            directory: Optional working directory
            
        Returns:
            CompileCommand or None if no valid input file found
        """
        if cc_cmd.name not in cmd_args[0]:
            return None

        cmd_args = cmd_args[:]
        cmd_args[0] = str(cc_cmd)

        if directory is None:
            directory = Path.cwd()
        else:
            directory = Path(directory)

        input_path = None

        # Try to find output file (-o flag)
        try:
            output_index = cmd_args.index("-o")
            output_arg = cmd_args[output_index + 1]
            if output_arg == "/dev/null":
                output_path = None
            else:
                output_path = directory / Path(output_arg)
        except (ValueError, IndexError):
            output_index = None
            output_path = None

        # Find input file based on output file stem or pattern matching
        if output_index is not None and output_path is not None:
            stem_matches = [item for item in cmd_args if Path(item).stem == output_path.stem]
            for item in stem_matches:
                if input_file_match := INFILE_PATTERN.search(item):
                    input_path = input_file_match.group("path")
                    break
            if not input_path and stem_matches:
                input_path = stem_matches[0]
            if not input_path:
                return None
            input_path = directory / Path(input_path)
        else:
            # Fallback: search for source file patterns
            match = None
            for item in cmd_args:
                match = INFILE_PATTERN.search(item)
                if match:
                    break
            if not match:
                return None
            input_path = Path(match.group("path"))
            output_path = None

        return cls(
            file=str(input_path),
            arguments=cmd_args,
            directory=str(directory),
            output=str(output_path) if output_path else "",
        )

@dataclass
class Compiler:
    """
    Represents a compiler toolchain.
    
    Attributes:
        name: Compiler name (e.g., 'gcc', 'g++')
        path: Path to compiler executable
    """
    name: str
    path: Path

    @classmethod
    def from_name(cls, compiler_name: str) -> "Compiler":
        """
        Create Compiler from name string.
        
        Args:
            compiler_name: Name of the compiler
            
        Returns:
            Compiler instance
        """
        path = Path(compiler_name)
        return cls(name=compiler_name, path=path)

    def find_invocation_start(self, cmd_args: list[str]) -> int:
        """
        Find compiler invocation in argument list.
        
        Args:
            cmd_args: List of command line arguments
            
        Returns:
            int: Index of compiler invocation
            
        Raises:
            ValueError: If compiler invocation not found
        """
        for index, arg in enumerate(cmd_args):
            if self.name in arg or Path(arg).stem == self.name:
                return index
        raise ValueError(f"compiler invocation for {self.name} not found")

def parse_build_log_to_compile_commands(logfile_path: Path, compiler_names: list[str]) -> list[CompileCommand]:
    """
    Parse build log to extract compile commands for compile_commands.json generation.
    
    Processes verbose build log to extract compiler invocations and create
    compile database entries for IDE integration.
    
    Args:
        logfile_path: Path to build log file
        compiler_names: List of compiler names to look for
        
    Returns:
        List of CompileCommand objects
    """
    if not logfile_path.exists():
        return []

    compilers = [Compiler.from_name(name) for name in compiler_names]
    entries = []
    file_entries = {}
    dirstack = [os.getcwd()]

    try:
        with logfile_path.open('r', encoding='utf-8', errors='ignore') as logfile:
            for line in logfile:
                line = line.strip()
                if not line:
                    continue

                # Handle directory changes (make-style output)
                if dirchange_match := DIRCHANGE_PATTERN.search(line):
                    action = dirchange_match.group("action")
                    path = dirchange_match.group("path")
                    if action == "Leaving":
                        if len(dirstack) > 1:
                            dirstack.pop()
                    elif action == "Entering":
                        dirstack.append(path)
                    continue

                # Parse command line
                try:
                    cmd_args = shlex.split(line)
                except ValueError:
                    continue

                if not cmd_args:
                    continue

                # Try to match against known compilers
                for compiler in compilers:
                    try:
                        compiler_invocation_start = compiler.find_invocation_start(cmd_args)
                        entry = CompileCommand.from_cmdline(
                            compiler.path, 
                            cmd_args[compiler_invocation_start:], 
                            dirstack[-1]
                        )
                        
                        # Avoid duplicate entries for the same file
                        if entry is not None and entry.file not in file_entries:
                            entries.append(entry)
                            file_entries[entry.file] = entry
                            break
                    except ValueError:
                        continue

    except Exception as e:
        print(f"⚠ Error parsing build log: {e}")

    return entries

class LDFCacheOptimizer:
    """
    PlatformIO LDF cache optimizer to avoid unnecessary LDF runs.
    
    This class implements intelligent caching of Library Dependency Finder (LDF)
    results to significantly speed up subsequent builds. It uses PlatformIO's
    native functions for maximum compatibility and integration.
    
    The optimizer works in two phases:
    1. First run: Collects dependencies, creates cache, modifies platformio.ini
    2. Second run: Applies cached dependencies with lib_ldf_mode=off
    
    Attributes:
        env: PlatformIO SCons environment
        env_name: Current environment name
        project_dir: Project root directory
        src_dir: Source directory path
        build_dir: Build output directory
        cache_file: Path to cache file
        _cache_applied_successfully: Flag indicating successful cache application
    """

    # File extensions relevant for LDF processing
    HEADER_EXTENSIONS = set(SRC_HEADER_EXT)
    SOURCE_EXTENSIONS = set(SRC_BUILD_EXT)
    CONFIG_EXTENSIONS = {'.json', '.properties', '.txt', '.ini'}
    ALL_RELEVANT_EXTENSIONS = HEADER_EXTENSIONS | SOURCE_EXTENSIONS | CONFIG_EXTENSIONS

    # Directories to ignore during file scanning (optimized for ESP/Tasmota projects)
    IGNORE_DIRS = frozenset([
        '.git', '.github', '.cache', '.vscode', '.pio', 'boards',
        'data', 'build', 'pio-tools', 'tools', '__pycache__', 'variants',
        'berry', 'berry_tasmota', 'berry_matter', 'berry_custom',
        'berry_animate', 'berry_mapping', 'berry_int64', 'displaydesc',
        'html_compressed', 'html_uncompressed', 'language', 'energy_modbus_configs'
    ])

    def __init__(self, environment):
        """
        Initialize the LDF cache optimizer with lazy initialization.
        
        Sets up paths, initializes PlatformIO integration, and determines
        whether to execute second run logic based on build environment state.
        
        Args:
            environment: PlatformIO SCons environment
        """
        self.env = environment
        self.env_name = self.env.get("PIOENV")
        self.project_dir = self.env.subst("$PROJECT_DIR")
        self.src_dir = self.env.subst("$PROJECT_SRC_DIR")
        self.build_dir = self.env.subst("$BUILD_DIR")

        # Setup cache and backup file paths
        cache_base = Path(self.project_dir) / ".pio" / "ldf_cache"
        self.cache_file = cache_base / f"ldf_cache_{self.env_name}.py"
        self.ldf_cache_ini = Path(self.project_dir) / "ldf_cache.ini"
        self.platformio_ini = Path(self.project_dir) / "platformio.ini"
        self.platformio_ini_backup = Path(self.project_dir) / ".pio" / f"platformio_backup_{self.env_name}.ini"

        # Setup compile database paths
        compiledb_base = Path(self.project_dir) / ".pio" / "compiledb"
        self.compiledb_dir = compiledb_base
        self.compile_commands_file = compiledb_base / f"compile_commands_{self.env_name}.json"
        self.compile_commands_log_file = compiledb_base / f"compile_commands_{self.env_name}.log"

        self.lib_build_dir = Path(self.project_dir) / ".pio" / "build" / self.env_name
        self.ALL_RELEVANT_EXTENSIONS = self.HEADER_EXTENSIONS | self.SOURCE_EXTENSIONS | self.CONFIG_EXTENSIONS

        # Cache application status tracking
        self._cache_applied_successfully = False

        # Initialize PlatformIO Core ProjectAsLibBuilder for native functionality
        self._project_builder = None
        
        build_ready = is_build_environment_ready()
        first_needed = is_first_run_needed()
        
        print(f"DEBUG: is _build_environment_ready() = {build_ready}")
        print(f"DEBUG: is _first_run_needed() = {first_needed}")
        print(f"DEBUG: Codndition for second run: {build_ready and not first_needed}")

        # Determine if second run should be executed (lazy initialization)
        if is_build_environment_ready() and not is_first_run_needed():
            print("🔄 Second run: Cache application mode")
            self.execute_second_run()
        else:
            print("🔄 Cache optimizer initialized (no action needed)")

    def _get_project_builder(self):
        """
        Get or create ProjectAsLibBuilder instance for PlatformIO Core integration.
        
        Returns:
            ProjectAsLibBuilder: Instance for native PlatformIO functionality
        """
        if not self._project_builder:
            self._project_builder = ProjectAsLibBuilder(
                self.env, 
                self.project_dir, 
                export_projenv=False
            )
        return self._project_builder

    def cleanup_final_build_targets(self):
        """Delete final build targets using wildcards"""
        try:
            build_dir = Path(self.build_dir)
            patterns = ['*.elf', '*.bin', '*.hex', '*.map']
        
            deleted_count = 0
            for pattern in patterns:
                targets = list(build_dir.glob(pattern))
                for target in targets:
                    if target.exists():
                        target.unlink()
                        deleted_count += 1
                        print(f"🗑️ Deleted: {target.name}")
        
            if deleted_count > 0:
                print(f"✅ Cleaned up {deleted_count} final build targets")
            else:
                print("ℹ No final build targets found to clean up")
            
        except Exception as e:
            print(f"⚠ Warning during cleanup: {e}")

    def execute_second_run(self):
        """
        Execute second run logic: Apply cached dependencies with LDF disabled.
        
        Loads and validates cache, applies cached dependencies to SCons environment,
        and handles fallback to normal build if cache application fails.
        """
        self._cache_applied_successfully = False

        # Register exit handler for cleanup
        self.register_exit_handler()

        try:
            self.cleanup_final_build_targets()
            # Load and validate cache data
            cache_data = self.load_cache()
            if cache_data and self.validate_cache(cache_data):
                # Integrate with PlatformIO Core functions
                # self.integrate_with_core_functions() # for debugging when uncomment comment next line!
                self.integrate_with_project_deps()
                
                # Apply cached dependencies to build environment
                success = self.apply_ldf_cache_with_build_order(cache_data)
                if success:
                    self._cache_applied_successfully = True
                    print("✅ Cache applied successfully - lib_ldf_mode=off")
                    # ✅ DEBUG: Finale SCons-Umgebung nach Cache-Anwendung
                    print("🔍 DEBUG: Final SCons environment state:")
                    print(f"  CPPPATH: {len(self.env.get('CPPPATH', []))} entries")
                    print(f"  LIBS: {len(self.env.get('LIBS', []))} entries") 
                    print(f"  SOURCES: {len(self.env.get('SOURCES', []))} entries")
                    print(f"  OBJECTS: {len(self.env.get('OBJECTS', []))} objects")
                else:
                    print("❌ Cache application failed")
            else:
                print("⚠ No valid cache found, falling back to normal build")
    
        except Exception as e:
            print(f"❌ Error in second run: {e}")
            self._cache_applied_successfully = False
    
        finally:
            # Handle cleanup based on success/failure
            if not self._cache_applied_successfully:
                print("🔄 Restoring original platformio.ini due to cache failure")
                self.restore_platformio_ini()
            else:
                print("✅ Keeping modified platformio.ini for optimal performance")

    def integrate_with_core_functions(self):
        """
        Integrate with PlatformIO Core functions for build pipeline integration.
        
        Registers middleware and integrates with ProcessProjectDeps for
        comprehensive build system integration.
        """
        self.register_cache_middleware()
        self.integrate_with_project_deps()

    def register_cache_middleware(self):
        """
        Register debug middleware with PlatformIO build pipeline.
        
        Provides file discovery logging for debugging purposes.
        The middleware does not modify build behavior, only provides visibility.
        """
        def cache_debug_middleware(env, node):
            """
            Debug middleware for file discovery logging.
            
            Args:
                env: SCons environment
                node: File node being processed
                
            Returns:
                node: Unmodified node (pass-through)
            """
            if isinstance(node, FS.File):
                file_path = node.srcnode().get_path()
                file_name = Path(file_path).name

                # Log file categorization for debugging
                if file_path.startswith(env.subst("$PROJECT_SRC_DIR")):
                    print(f"📦 Source file: {file_name}")
                elif file_path.startswith(env.subst("$PROJECT_LIBDEPS_DIR")):
                    print(f"📦 Library file: {file_name}")
            
            return node

        # Register middleware with PlatformIO's native system
        self.env.AddBuildMiddleware(cache_debug_middleware)

    def integrate_with_project_deps(self):
        """
        Integrate cache application before ProcessProjectDeps.
        
        Overrides PlatformIO's ProcessProjectDeps method to inject cached
        dependencies before normal dependency processing.
        """
        original_process_deps = getattr(self.env, 'ProcessProjectDeps', None)
    
        def cached_process_deps(orig_self):
            """
            Cached version of ProcessProjectDeps that applies cache first.
            
            Returns:
                Result of original ProcessProjectDeps if available
            """
            # Apply cached dependencies if available
            if hasattr(self, '_current_cache_data') and self._current_cache_data:
                self.provide_cached_dependencies_to_scons(self._current_cache_data)
                print("✅ Applied cached dependencies before ProcessProjectDeps")
        
            # Call original ProcessProjectDeps if it exists
            if original_process_deps:
                return original_process_deps()

        # Replace ProcessProjectDeps with cached version
        self.env.AddMethod(cached_process_deps, 'ProcessProjectDeps')

    def provide_cached_dependencies_to_scons(self, cache_data):
        """
        Provide cached dependency information to SCons.
    
        Args:
        cache_data (dict): Cached dependency information
        """
        try:
            build_order = cache_data.get('artifacts', {})
        
            # Versuche verschiedene mögliche Schlüsselnamen
            object_files = []
            for key in ['artifacts', 'object_paths', 'object_paths_files']:
                if key in build_order:
                    object_files = build_order[key]
                    print(f"✓ Objekt-Dateien unter Schlüssel '{key}' gefunden")
                    break
                
            if not object_files:
                print(f"⚠ Keine Objekt-Dateien im Cache gefunden. Verfügbare Schlüssel: {list(build_order.keys())}")
                return
            
            valid_objects = 0
            for obj_entry in object_files:
                # KRITISCHE ÄNDERUNG: Extrahiere Pfad aus Dictionary oder String
                if isinstance(obj_entry, dict):
                    # Versuche Pfad aus Dictionary zu extrahieren
                    for path_key in ['path', 'file', 'filepath', 'location', 'source']:
                        if path_key in obj_entry:
                            obj_path = obj_entry[path_key]
                            break
                    else:
                        print(f"⚠ Kann Pfad nicht aus Objekt extrahieren: {obj_entry}")
                        continue
                else:
                    # Nimm an, es ist ein String-Pfad
                    obj_path = str(obj_entry)
                
                # Jetzt können wir sicher prüfen, ob der Pfad existiert
                if Path(obj_path).exists():
                    # Füge Objekt zum Build hinzu
                    self.env.Append(LINKFLAGS=[obj_path])
                    valid_objects += 1
                else:
                    print(f"⚠ Objekt-Datei nicht gefunden: {obj_path}")
                
            print(f"✅ {valid_objects} Objekt-Dateien aus Cache zum Build hinzugefügt")
            
        except Exception as e:
            print(f"❌ Error providing dependencies: {e}")
            import traceback
            traceback.print_exc()

    def apply_ldf_cache_with_build_order(self, cache_data):
        """
        Apply cached dependencies with correct build order preservation.

        Coordinates application of build order and SCons variables to ensure
        correct dependency resolution and linking order.
        
        Args:
            cache_data: Dictionary containing cached build data
            
        Returns:
            bool: True if cache application succeeded
        """
        print("🔍 DEBUG: apply_ldf_cache_with_build_order() started")
        try:
            # Store cache data for middleware access
            self._current_cache_data = cache_data
        
            build_order = cache_data.get('build_order', {})
            artifacts = cache_data.get('artifacts', {})
            print(f"🔍 DEBUG: Build order data: {bool(build_order)}")
            print(f"🔍 DEBUG: Artifacts data: {bool(artifacts)}")

            if not build_order:
                print("❌ No build order data in cache")
                return False

            print("🔧 Applying build order with artifact integration...")

            print("🔍 DEBUG: Calling apply_build_order_to_environment...")
            # Apply build order (SOURCES, OBJECTS, linker configuration)
            build_order_success = self.apply_build_order_to_environment(build_order)
            print(f"🔍 DEBUG: Build order success: {build_order_success}")
        
            print("🔍 DEBUG: Calling apply_cache_to_scons_vars...")
            # Apply SCons variables (include paths, libraries)
            scons_vars_success = self.apply_cache_to_scons_vars(cache_data)
            print(f"🔍 DEBUG: SCons vars success: {scons_vars_success}")
        
            if build_order_success and scons_vars_success:
                print("✅ LDF cache applied successfully")
                return True
            else:
                print("❌ Partial cache application failure")
                return False

        except Exception as e:
            print(f"✗ Error applying LDF cache: {e}")
            import traceback
            traceback.print_exc()
            return False

    def register_exit_handler(self):
        """
        Register exit handler for conditional platformio.ini restoration.
        
        Ensures platformio.ini is restored to original state if cache
        application fails or script exits unexpectedly.
        """
        def cleanup_on_exit():
            """
            Cleanup function called on script exit.
            
            Restores platformio.ini if cache was not successfully applied.
            """
            try:
                if hasattr(self, '_cache_applied_successfully'):
                    if not self._cache_applied_successfully:
                        self.restore_platformio_ini()
                else:
                    self.restore_platformio_ini()
            except:
                # Silently handle cleanup errors to avoid exit issues
                pass
        
        atexit.register(cleanup_on_exit)

    def modify_platformio_ini_for_second_run(self):
        """
        Modify platformio.ini for second run by setting lib_ldf_mode = off.
        
        Creates backup and modifies platformio.ini to disable LDF for subsequent
        builds that will use cached dependencies.
        
        Returns:
            bool: True if modification was successful or not needed
        """
        try:
            # Check if platformio.ini exists
            if not self.platformio_ini.exists():
                print("❌ platformio.ini not found")
                return False
                
            # Create backup if it doesn't exist
            if not self.platformio_ini_backup.exists():
                shutil.copy2(self.platformio_ini, self.platformio_ini_backup)
                print(f"✅ Configuration backup created: {self.platformio_ini_backup.name}")
                
            # Read current platformio.ini content
            with self.platformio_ini.open('r', encoding='utf-8') as f:
                lines = f.readlines()
        
            # Find and modify lib_ldf_mode line
            modified = False
            for i, line in enumerate(lines):
                stripped_line = line.strip()
                if stripped_line.startswith('lib_ldf_mode'):
                    lines[i] = 'lib_ldf_mode = off\n'
                    modified = True
                    print(f"✅ Changed line: {stripped_line} -> lib_ldf_mode = off")
                    break

            # Write modified content or report no changes needed
            if modified:
                with self.platformio_ini.open('w', encoding='utf-8') as f:
                    f.writelines(lines)
                print("✅ platformio.ini successfully modified")
                return True
            else:
                print("ℹ No lib_ldf_mode entry found, no changes made")
                return True
                
        except Exception as e:
            print(f"❌ Error modifying platformio.ini: {e}")
            return False

    def restore_platformio_ini(self):
        """
        Restore original platformio.ini from backup.
        
        Restores platformio.ini to its original state using the backup
        created during first run.
        
        Returns:
            bool: True if restoration was successful
        """
        try:
            if self.platformio_ini_backup.exists():
                shutil.copy2(self.platformio_ini_backup, self.platformio_ini)
                print(f"✅ platformio.ini restored from backup")
                return True
            else:
                print("⚠ No backup found to restore")
                return False
        except Exception as e:
            print(f"❌ Error restoring platformio.ini: {e}")
            return False

    def validate_ldf_mode_compatibility(self):
        """
        Validate that the current LDF mode is compatible with caching.
        
        Uses PlatformIO Core's native LDF mode validation to ensure
        compatibility with the caching system.
        
        Returns:
            bool: True if LDF mode is compatible with caching
        """
        try:
            # Get current LDF mode and validate using PlatformIO Core
            current_mode = self.env.GetProjectOption("lib_ldf_mode", "chain")
            validated_mode = LibBuilderBase.validate_ldf_mode(current_mode)
            
            # Check against supported modes
            compatible_modes = ["chain", "off"]
            if validated_mode.lower() in compatible_modes:
                print(f"✅ LDF mode '{validated_mode}' is compatible with caching")
                return True
            else:
                print(f"⚠ LDF mode '{validated_mode}' not optimal for caching")
                print(f"💡 Recommended modes: {', '.join(compatible_modes)}")
                return False
        except Exception as e:
            print(f"⚠ Could not determine LDF mode: {e}")
            return True

    def create_compiledb_integrated(self):
        """
        Create compile_commands.json using integrated log parsing functionality.
        
        Generates compile database from verbose build log for IDE integration
        and IntelliSense support.
        
        Returns:
            bool: True if compile_commands.json was created successfully
        """
        # Check if compile_commands.json already exists
        if self.compile_commands_file.exists():
            print(f"✅ {self.compile_commands_file} exists")
            return True

        # Search for build log files
        build_log = None
        possible_logs = [
            self.compile_commands_log_file,
            Path(self.project_dir) / f"build_{self.env_name}.log",
            Path(self.build_dir) / f"build_{self.env_name}.log",
            Path(self.build_dir) / "build.log"
        ]

        for log_path in possible_logs:
            if log_path.exists() and log_path.stat().st_size > 0:
                build_log = log_path
                break

        if not build_log:
            print("⚠ No build log found for compile_commands.json generation")
            return False

        print(f"🔧 Generating compile_commands.json from {build_log}")

        # Define supported compiler toolchains
        compiler_names = [
            "xtensa-esp32-elf-gcc", "xtensa-esp32-elf-g++", 
            "riscv32-esp-elf-gcc", "riscv32-esp-elf-g++",
            "xtensa-lx106-elf-gcc", "xtensa-lx106-elf-g++",
            "arm-none-eabi-gcc", "arm-none-eabi-g++"
        ]

        try:
            # Parse build log to extract compile commands
            compile_commands = parse_build_log_to_compile_commands(build_log, compiler_names)
            if not compile_commands:
                print("❌ No compiler commands found in build log")
                return False

            # Create output directory
            self.compiledb_dir.mkdir(parents=True, exist_ok=True)
            
            # Convert to JSON format
            json_entries = []
            for cmd in compile_commands:
                json_entries.append({
                    'file': cmd.file,
                    'output': cmd.output,
                    'directory': cmd.directory,
                    'arguments': cmd.arguments
                })
                
            # Write compile_commands.json
            with self.compile_commands_file.open('w') as f:
                json.dump(json_entries, f, indent=2)
                
            file_size = self.compile_commands_file.stat().st_size
            print(f"✅ Generated {self.compile_commands_file} ({file_size} bytes)")
            print(f"✅ Found {len(compile_commands)} compiler invocations")
            return True

        except Exception as e:
            print(f"❌ Error creating compile_commands.json: {e}")
            return False

    def collect_sources_via_piolib(self):
        """
        Use PlatformIO's native LibBuilder functionality to collect source files.
        
        Leverages PlatformIO Core's ProjectAsLibBuilder for consistent
        source file collection that matches PlatformIO's internal logic.
        
        Returns:
            list: List of source file paths
        """
        try:
            project_builder = self._get_project_builder()
            search_files = project_builder.get_search_files()
            print(f"✅ Collected {len(search_files)} source files via PlatformIO LibBuilder")
            return search_files
        except Exception as e:
            print(f"⚠ Error collecting sources via PlatformIO LibBuilder: {e}")
            return []

    def get_include_dirs_via_piolib(self):
        """
        Use PlatformIO's native LibBuilder functionality to get include directories.
        
        Leverages PlatformIO Core's include directory resolution for
        consistency with PlatformIO's internal dependency handling.
        
        Returns:
            list: List of include directory paths
        """
        try:
            project_builder = self._get_project_builder()
            include_dirs = project_builder.get_include_dirs()
            print(f"✅ Found {len(include_dirs)} include directories via LibBuilder")
            return include_dirs
        except Exception as e:
            print(f"⚠ Error getting include dirs via PlatformIO LibBuilder: {e}")
            return []

    def process_library_dependencies_via_piolib(self):
        """
        Use PlatformIO's native Library-Dependency-Processing.
        
        Leverages PlatformIO Core's library builders to collect information
        about built libraries and their dependencies.
        
        Returns:
            list: List of library information dictionaries
        """
        try:
            lib_builders = self.env.GetLibBuilders()
            
            library_info = []
            for lb in lib_builders:
                if lb.is_built:  # Only include libraries that have been built
                    lib_info = {
                        'name': lb.name,
                        'path': lb.path,
                        'include_dirs': lb.get_include_dirs(),
                        'build_dir': lb.build_dir,
                        'src_dir': lb.src_dir
                    }
                    library_info.append(lib_info)
            
            print(f"✅ Processed {len(library_info)} library dependencies via PlatformIO Core")
            return library_info
        except Exception as e:
            print(f"⚠ Error processing library dependencies: {e}")
            return []

    def get_correct_build_order(self):
        """
        Extract build order from compile_commands.json with build artifacts.
        
        Combines compile_commands.json (which preserves compilation order)
        with build artifact paths to create comprehensive build order data.
        
        Returns:
            dict: Build order data with sources, objects, and include paths
            None: If compile_commands.json doesn't exist or is invalid
        """
        if not self.compile_commands_file.exists():
            print(f"⚠ compile_commands_{self.env_name}.json not found")
            return None

        try:
            # Load compile database
            with self.compile_commands_file.open("r", encoding='utf-8') as f:
                compile_db = json.load(f)
        except Exception as e:
            print(f"✗ Error reading compile_commands.json: {e}")
            return None

        # Initialize data structures for build order extraction
        object_paths = []
        include_paths = set()

        # Process each compile command entry
        for i, entry in enumerate(compile_db, 1):
            source_file = entry.get('file', '')
            
            if source_file.endswith(('.elf', '.bin', '.hex', '.map')):
                # not a source file, skip
                continue

            if not source_file.endswith(tuple(SRC_BUILD_EXT + SRC_HEADER_EXT)):
                # not a recognized source file, skip
                continue

            # Handle both 'arguments' and 'command' formats
            if 'arguments' in entry:
                command = ' '.join(entry['arguments'])
            elif 'command' in entry:
                command = entry['command']
            else:
                print(f"⚠ Unsupported entry format in compile_commands.json (index {i})")
                continue

            # Extract object file from -o flag
            obj_match = re.search(r'-o\s+(\S+\.o)', command)
            if obj_match:
                obj_file = obj_match.group(1)
                object_paths.append({
                    'order': i,
                    'source': source_file,
                    'object': obj_file,
                })
            
            # Extract include paths from -I flags
            include_matches = re.findall(r'-I\s*([^\s]+)', command)
            for inc_path in include_matches:
                inc_path = inc_path.strip('"\'')
                if Path(inc_path).exists():
                    include_paths.add(str(Path(inc_path)))

        print(f"✓ Build order extracted directly from {self.compile_commands_file}")

        return {
            'object_paths': object_paths,
            'include_paths': sorted(include_paths)
        }

    def collect_build_artifacts_paths(self):
        """
        Collect paths to build artifacts without copying them.
        
        Scans build directory for library (.a) and object (.o) files,
        collecting their paths for cache storage and later reuse.
        
        Returns:
            dict: Artifact paths organized by type with metadata
        """
        if not self.lib_build_dir.exists():
            print(f"⚠ Build directory not found: {self.lib_build_dir}")
            return {}

        library_paths = []
        object_paths = []

        print(f"📦 Collecting artifact paths from {self.lib_build_dir}")

        # Walk through build directory to find artifacts
        for root, dirs, files in os.walk(self.lib_build_dir):
            root_path = Path(root)
            for file in files:
                if file.endswith('.a'):
                    file_path = root_path / file
                    library_paths.append(str(file_path))
                elif file.endswith('.o'):
                    file_path = root_path / file
                    object_paths.append(str(file_path))

        total_count = len(library_paths) + len(object_paths)
    
        print(f"📦 Collected {len(library_paths)} library paths (*.a)")
        print(f"📦 Collected {len(object_paths)} object paths (*.o)")
        print(f"📦 Total: {total_count} artifact paths collected")

        return {
            'library_paths': library_paths,
            'object_paths': object_paths,
            'total_count': total_count
        }


    def get_project_hash_with_details(self):
        """
        Calculate comprehensive project hash for cache invalidation.
        
        Computes hash based on all LDF-relevant files to detect changes
        that would require cache invalidation. Only includes files that
        can affect dependency resolution.
        
        Returns:
            dict: Hash details including file hashes and final combined hash
        """
        file_hashes = {}
        src_path = Path(self.src_dir)
        
        # Process all files in source directory
        for file_path in src_path.rglob('*'):
            # Skip directories and ignored directories
            if file_path.is_dir() or self._is_ignored_directory(file_path.parent):
                continue
                
            # Only process LDF-relevant file extensions
            if file_path.suffix in self.ALL_RELEVANT_EXTENSIONS:
                try:
                    rel_path = self._get_relative_path_from_project(file_path)
                    
                    # Hash source files based on their include dependencies
                    if file_path.suffix in self.SOURCE_EXTENSIONS:
                        includes = self._extract_includes(file_path)
                        include_hash = hashlib.md5(str(sorted(includes)).encode()).hexdigest()
                        file_hashes[rel_path] = include_hash
                    # Hash header files based on content
                    elif file_path.suffix in self.HEADER_EXTENSIONS:
                        file_content = file_path.read_bytes()
                        file_hash = hashlib.md5(file_content).hexdigest()
                        file_hashes[rel_path] = file_hash
                    # Hash config files based on content
                    elif file_path.suffix in self.CONFIG_EXTENSIONS:
                        file_content = file_path.read_bytes()
                        file_hash = hashlib.md5(file_content).hexdigest()
                        file_hashes[rel_path] = file_hash
                except (IOError, OSError) as e:
                    print(f"⚠ Could not hash {file_path}: {e}")
                    continue
                    
        # Process platformio.ini files
        project_path = Path(self.project_dir)
        print("✅ Hashed platfomio.ini file(s)")
        for ini_path in project_path.glob('platformio*.ini'):
            if ini_path.exists() and ini_path.is_file():
                try:
                    platformio_hash = self._hash_platformio_ini_selective(ini_path)
                    if platformio_hash:
                        rel_ini_path = self._get_relative_path_from_project(ini_path)
                        file_hashes[rel_ini_path] = platformio_hash
                except (IOError, OSError) as e:
                    print(f"⚠ Could not hash {ini_path}: {e}")
                    
        # Compute final combined hash
        combined_content = json.dumps(file_hashes, sort_keys=True)
        final_hash = hashlib.sha256(combined_content.encode()).hexdigest()
        
        return {
            'file_hashes': file_hashes,
            'final_hash': final_hash,
            'file_count': len(file_hashes)
        }

    def create_comprehensive_cache(self):
        """
        Create comprehensive cache data including all build information.
        
        Combines project hash, build order, and artifact information into
        a complete cache that can be used for subsequent builds.
        
        Returns:
            dict: Complete cache data with signature
            None: If cache creation failed
        """
        try:
            print("🔧 Creating comprehensive cache...")

            # Collect all cache components
            project_hash = self.get_project_hash_with_details()
            build_order = self.get_correct_build_order()
            artifacts = self.collect_build_artifacts_paths()

            if not build_order:
                print("⚠ No build order data available")
                return None

            # Create cache data structure
            cache_data = {
                'version': '2.0',
                'env_name': self.env_name,
                'timestamp': datetime.datetime.now().isoformat(),
                'project_hash': project_hash['final_hash'],
                'file_hashes': project_hash['file_hashes'],
                'build_order': build_order,
                'artifacts': artifacts,
                'platformio_version': self.env.get('PLATFORMIO_VERSION', 'unknown')
            }

            # Add signature for integrity verification
            cache_data['signature'] = self.compute_signature(cache_data)

            print(f"✅ Cache created with {project_hash['file_count']} files")
            return cache_data

        except Exception as e:
            print(f"❌ Error creating cache: {e}")
            return None

    def save_cache(self, cache_data):
        """
        Save cache data to file in Python format.
        
        Saves cache as executable Python code for easy loading and
        human-readable format for debugging.
        
        Args:
            cache_data: Dictionary containing cache data
            
        Returns:
            bool: True if cache was saved successfully
        """
        try:
            # Ensure cache directory exists
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)

            # Write cache as Python code
            with self.cache_file.open('w') as f:
                f.write("# LDF Cache Data - Auto-generated\n")
                f.write("# Do not edit manually, this will break the Hash checksum\n\n")
                f.write("cache_data = ")
                f.write(pprint.pformat(cache_data, width=120, depth=None))
                f.write("\n")

            print(f"✅ Cache saved to {self.cache_file}")
            return True

        except Exception as e:
            print(f"❌ Error saving cache: {e}")
            return False

    def compute_signature(self, data):
        """
        Compute SHA256 signature for cache data validation.
        
        Creates tamper-evident signature to ensure cache integrity
        and detect corruption or manual modifications.
        
        Args:
            data: Dictionary to sign
            
        Returns:
            str: SHA256 signature hex string
        """
        # Create copy without signature field to avoid circular reference
        data_copy = data.copy()
        data_copy.pop('signature', None)
        
        # Create deterministic JSON representation
        data_str = json.dumps(data_copy, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()

    def load_cache(self):
        """
        Load cache data from file.
        
        Executes Python cache file to load cache data into memory
        for validation and application.
        
        Returns:
            dict: Cache data if loaded successfully
            None: If cache file doesn't exist or loading failed
        """
        if not self.cache_file.exists():
            return None

        try:
            # Execute Python cache file in isolated namespace
            cache_globals = {}
            with self.cache_file.open('r') as f:
                exec(f.read(), cache_globals)

            # Extract cache data from executed namespace
            cache_data = cache_globals.get('cache_data')
            if cache_data:
                print(f"✅ Cache loaded from {self.cache_file}")
                return cache_data
            else:
                print("⚠ No cache_data found in cache file")
                return None

        except Exception as e:
            print(f"❌ Error loading cache: {e}")
            return None

    def validate_cache(self, cache_data):
        """
        Validate cache integrity and freshness.
        
        Performs comprehensive validation including signature verification
        and project hash comparison to ensure cache is valid and current.
        
        Args:
            cache_data: Cache data to validate
            
        Returns:
            bool: True if cache is valid and current
        """
        if not cache_data:
            return False

        try:
            # Verify signature integrity
            stored_signature = cache_data.get('signature')
            if not stored_signature:
                print("⚠ Cache missing signature")
                return False

            computed_signature = self.compute_signature(cache_data)
            if stored_signature != computed_signature:
                print("⚠ Cache signature mismatch")
                return False

            # Verify project hasn't changed
            current_hash = self.get_project_hash_with_details()
            if cache_data.get('project_hash') != current_hash['final_hash']:
                print("⚠ Project files changed, cache invalid")
                return False

            print("✅ Cache validation successful")
            return True

        except Exception as e:
            print(f"⚠ Cache validation error: {e}")
            return False

    def apply_build_order_to_environment(self, build_order_data):
        """
        Apply correct build order to SCons environment.
        
        Sets SOURCES and OBJECTS variables in correct order and configures
        linker for optimal symbol resolution.
        
        Args:
            build_order_data: Dictionary containing build order information
            
        Returns:
            bool: True if build order was applied successfully
        """
        if not build_order_data:
            return False

        try:
            # Apply object file order
            object_paths = build_order_data.get('object_paths', [])
            print(f"🔍 DEBUG: Object files: {object_paths}")
            if object_paths:
                # Use ALL cached object files
                try:
                    self.env.Replace(OBJECTS=object_paths)
                    print(f"✅ Set OBJECTS: {len(object_paths)} files")
                except Exception as e:
                    print(f"⚠ Could not set OBJECTS: {e}")
                    print(f"✅ Found {len(object_paths)} object files")
            
                self._apply_correct_linker_order(object_paths)

            return True

        except Exception as e:
            print(f"✗ Error applying build order: {e}")
            return False

    def apply_cache_to_scons_vars(self, cache_data):
        """
        Apply cache data to SCons variables using PlatformIO Core methods.
        
        Uses PlatformIO's ParseFlagsExtended for robust flag processing
        and applies cached include paths and library paths to build environment.
        
        Args:
            cache_data: Dictionary containing cached build data
            
        Returns:
            bool: True if cache variables were applied successfully
        """
        try:
            build_order = cache_data.get('build_order', {})

            # Apply include paths using PlatformIO's native flag processing
            if 'include_paths' in build_order:
                include_flags = [f"-I{path}" for path in build_order['include_paths']]
                parsed_flags = self.env.ParseFlagsExtended(include_flags)
                self.env.Append(**parsed_flags)
                print(f"✅ Applied {len(include_flags)} include flags via ParseFlagsExtended")

            # Apply library paths
            artifacts = cache_data.get('artifacts', {})
            if 'library_paths' in artifacts:
                library_paths = artifacts['library_paths']
                if library_paths:
                    self.env.Prepend(LIBS=library_paths)
                    print(f"✅ Applied {len(library_paths)} library paths")

            return True

        except Exception as e:
            print(f"⚠ Warning applying cache to SCons vars: {e}")
            return False

    def _apply_correct_linker_order(self, object_files):
        """
        Apply correct linker order for symbol resolution.
        
        Configures linker with optimized flags and proper grouping
        to ensure correct symbol resolution and garbage collection.
        
        Args:
            object_files: List of object file paths
        """
        try:
            current_linkflags = self.env.get('LINKFLAGS', [])

            # Configure custom linker command for better control
            custom_linkcom = (
                "$LINK -o $TARGET "
                "${_long_sources_hook(__env__, SOURCES)} "
                "$LINKFLAGS "
                "$__RPATH $_LIBDIRFLAGS $_LIBFLAGS"
            )

            self.env.Replace(LINKCOM=custom_linkcom)

            # Build optimized linker flags
            optimized_linkflags = []
            optimized_linkflags.extend(["-Wl,--start-group"])

            # Add existing flags without duplicates
            for flag in current_linkflags:
                if flag not in optimized_linkflags:
                    optimized_linkflags.append(flag)

            # Add optimization flags
            optimized_linkflags.extend([
                "-Wl,--end-group",
                "-Wl,--gc-sections",
            ])

            self.env.Replace(LINKFLAGS=optimized_linkflags)
            print(f"🔗 Linker optimized with {len(optimized_linkflags)} flags")

        except Exception as e:
            print(f"⚠ Warning during linker optimization: {e}")

    def is_file_cached(self, file_path):
        """
        Check if file is present in cache.
        
        Args:
            file_path: Path to file to check
            
        Returns:
            bool: True if file is in cache
        """
        cache_data = self.load_cache()
        if not cache_data:
            return False

        rel_path = self._get_relative_path_from_project(file_path)
        return rel_path in cache_data.get('file_hashes', {})

    def _get_relative_path_from_project(self, file_path):
        """
        Calculate relative path from project root with consistent path handling.
        
        Normalizes paths to use forward slashes for cross-platform compatibility.
        
        Args:
            file_path: File path to make relative
            
        Returns:
            str: Relative path from project root with forward slashes
        """
        try:
            file_path = Path(file_path).resolve()
            project_dir = Path(self.project_dir).resolve()
            rel_path = file_path.relative_to(project_dir)
            return str(rel_path).replace(os.sep, '/')
        except (ValueError, OSError):
            return str(Path(file_path)).replace(os.sep, '/')

    def _extract_includes(self, file_path):
        """
        Extract #include directives from source files.
        
        Parses source files to extract include dependencies for
        hash calculation and dependency tracking.
        
        Args:
            file_path: Source file to analyze
            
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
                        include_match = re.search(r'#include\s*[<"]([^>"]+)[>"]', line)
                        if include_match:
                            include_path = include_match.group(1)
                            normalized_include = str(Path(include_path)).replace(os.sep, '/')
                            includes.add(normalized_include)
        except (IOError, OSError, UnicodeDecodeError) as e:
            print(f"⚠ Could not read {file_path}: {e}")
        return includes

    def _hash_platformio_ini_selective(self, ini_path=None):
        """
        Hash platformio.ini excluding LDF-related lines modified by script.
        
        Creates hash of platformio.ini while excluding lines that are
        modified by this script to avoid cache invalidation loops.
        
        Args:
            ini_path: Path to ini file (defaults to self.platformio_ini)
            
        Returns:
            str: MD5 hash of relevant platformio.ini content
        """
        if ini_path is None:
            ini_path = self.platformio_ini
        if not ini_path.exists():
            return ""
            
        # Lines to exclude from hashing (modified by this script)
        excluded_patterns = ['lib_ldf_mode']
        
        try:
            relevant_lines = []
            with ini_path.open('r', encoding='utf-8') as f:
                for line in f:
                    line_stripped = line.strip()
                    
                    # Skip empty lines and comments
                    if not line_stripped or line_stripped.startswith(';') or line_stripped.startswith('#'):
                        continue
                        
                    # Skip excluded patterns
                    should_exclude = any(
                        pattern.lower() in line_stripped.lower() 
                        for pattern in excluded_patterns
                    )
                    if not should_exclude:
                        relevant_lines.append(line_stripped)
                        
            # Create deterministic hash from sorted lines
            relevant_content = '\n'.join(sorted(relevant_lines))
            return hashlib.md5(relevant_content.encode()).hexdigest()
        except (IOError, OSError) as e:
            print(f"⚠ Could not read {ini_path}: {e}")
            return ""

    def _is_ignored_directory(self, dir_path):
        """
        Check if a directory should be ignored during file scanning.
        
        Uses predefined ignore patterns optimized for ESP/Tasmota projects
        to skip irrelevant directories during cache creation.
        
        Args:
            dir_path: Directory path to check
            
        Returns:
            bool: True if directory should be ignored
        """
        if not dir_path:
            return False
            
        path_obj = Path(dir_path)
        
        # Check if directory name is in ignore list
        if path_obj.name in self.IGNORE_DIRS:
            return True
            
        # Check if any parent directory is in ignore list
        for part in path_obj.parts:
            if part in self.IGNORE_DIRS:
                return True
        return False

def modify_platformio_ini_for_second_run(self):
    """
    Einfache Modifikation: Suche lib_ldf_mode und ersetze durch lib_ldf_mode = off
    Wenn kein Eintrag vorhanden, nichts ändern.
    Returns:
        bool: True if modification was successful or not needed
    """
    try:
        if not self.platformio_ini.exists():
            print("❌ platformio.ini not found")
            return False

        if not self.platformio_ini_backup.exists():
            shutil.copy2(self.platformio_ini, self.platformio_ini_backup)
            print(f"✅ Configuration backup created: {self.platformio_ini_backup.name}")

        with self.platformio_ini.open('r', encoding='utf-8') as f:
            lines = f.readlines()

        modified = False
        for i, line in enumerate(lines):
            if line.strip().startswith('lib_ldf_mode'):
                lines[i] = 'lib_ldf_mode = off\n'
                modified = True
                print(f"✅ Changed line: {line.strip()} -> lib_ldf_mode = off")
                break

        if modified:
            with self.platformio_ini.open('w', encoding='utf-8') as f:
                f.writelines(lines)
            print("✅ platformio.ini successfully modified")
            return True
        else:
            print("ℹ No lib_ldf_mode entry found, no changes made")
            return True

    except Exception as e:
        print(f"❌ Error modifying platformio.ini: {e}")
        return False

def execute_first_run_post_actions():
    """
    Execute post-build actions after successful first run.
    
    Creates cache data, generates compile_commands.json, validates LDF mode,
    and modifies platformio.ini for subsequent cached builds.
    
    Returns:
        bool: True if all post-actions completed successfully
    """
    print("🎯 First run completed successfully - executing post-build actions...")

    try:
        # Initialize optimizer for first run tasks
        optimizer = LDFCacheOptimizer(env)

        # Create compile_commands.json if needed
        if not compiledb_path.exists() or compiledb_path.stat().st_size == 0:
            success_compiledb = optimizer.create_compiledb_integrated()
            if not success_compiledb:
                print("❌ Failed to create compile_commands.json")
                return False
        else:
            print(f"✅ compile_commands.json already exists: {compiledb_path}")

        # Create cache if it doesn't exist
        if not cache_file.exists():
            cache_data = optimizer.create_comprehensive_cache()
            
            if not cache_data:
                print("❌ Failed to create cache data")
                return False

            # Save cache to file
            success_save = optimizer.save_cache(cache_data)
            if not success_save:
                print("❌ Failed to save cache")
                return False

            print(f"✅ LDF cache created: {cache_file}")
            print(f"✅ Artifacts: {cache_data.get('artifacts', {}).get('total_count', 0)} files")
        else:
            print(f"✅ LDF cache already exists: {cache_file}")

        # Validate LDF mode compatibility
        optimizer.validate_ldf_mode_compatibility()

        # Check current LDF mode and modify platformio.ini if needed
        current_ldf_mode = optimizer.env.GetProjectOption("lib_ldf_mode", "chain")
        print(f"🔍 Current lib_ldf_mode: {current_ldf_mode}")
        
        if current_ldf_mode.lower() in ["chain", "off"]:
            print("🔧 Modifying platformio.ini for second run...")
            success_ini_mod = optimizer.modify_platformio_ini_for_second_run()
            if success_ini_mod:
                print("🎉 First run post-build actions completed successfully!")
                print("🔄 platformio.ini configured for cached build (lib_ldf_mode = off)")
                print("🚀 Next build will be significantly faster using cached dependencies")
            else:
                print("⚠ Cache created but platformio.ini modification failed")
                print("💡 Manual setting: lib_ldf_mode = off recommended for next build")
                return False
        else:
            print(f"⚠ lib_ldf_mode '{current_ldf_mode}' not supported for caching")
            print("💡 Supported modes: chain, off")
            return False

        return True

    except Exception as e:
        print(f"❌ Error in first run post-build actions: {e}")
        import traceback
        traceback.print_exc()
        return False
print("🔄 Starting LDF Cache Optimizer...")
# FIRST RUN LOGIC - Execute verbose build and create cache
if should_trigger_verbose_build():
    print(f"🔄 First run needed - starting verbose build for {env_name}...")
    print("📋 Reasons:")

    # Report reasons for first run
    if not compiledb_path.exists():
        print("  - compile_commands.json missing")
    elif compiledb_path.stat().st_size == 0:
        print("  - compile_commands.json is empty")

    if not is_build_environment_ready():
        print("  - Build environment incomplete")

    # Setup environment for verbose build
    env_vars = os.environ.copy()
    env_vars['PLATFORMIO_SETTING_FORCE_VERBOSE'] = 'true'
    env_vars['_PIO_RECURSIVE_CALL'] = 'true'
    
    # Handle recursive call return codes
    if os.environ.get('_PIO_REC_CALL_RETURN_CODE') is not None:
        sys.exit(int(os.environ.get('_PIO_REC_CALL_RETURN_CODE')))

    # Execute verbose build with output capture
    with open(logfile_path, "w") as logfile:
        process = subprocess.Popen(
            ['pio', 'run', '-e', env_name, '--disable-auto-clean'],
            env=env_vars,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        for line in process.stdout:
            print(line, end='')
            logfile.write(line)
            logfile.flush()
        process.wait()

    print(f"🔄 First run completed with return code: {process.returncode}")

    if process.returncode == 0:
        post_actions_success = execute_first_run_post_actions()
        if post_actions_success:
            print("✅ All first run actions completed successfully")
        else:
            print("⚠ Some first run actions failed")
    else:
        print(f"❌ First run failed with return code: {process.returncode}")

    sys.exit(process.returncode)

# SECOND RUN LOGIC (wird nur erreicht wenn First Run nicht stattfand)
try:
    if (not should_trigger_verbose_build() and
        is_build_environment_ready()):
        print("🔄 Second run: Cache application mode")
        optimizer = LDFCacheOptimizer(env)
        print("✅ LDF Cache Optimizer initialized successfully")
except Exception as e:
    print(f"❌ Error initializing LDF Cache Optimizer: {e}")
    import traceback
    traceback.print_exc()
