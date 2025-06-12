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
import shlex
from pathlib import Path
from platformio.project.config import ProjectConfig
from SCons.Script import COMMAND_LINE_TARGETS
from dataclasses import dataclass
from typing import Optional

Import("env")

import os
import sys
import subprocess
from pathlib import Path

# generate 1st build in full verbose mode - Platformio and toolchain
project_dir = env.subst("$PROJECT_DIR")
env_name = env.subst("$PIOENV")
compiledb_path = Path(project_dir) / ".pio" / "compiledb" / f"compile_commands_{env_name}.json"
logfile_path = Path(project_dir) / ".pio" / "compiledb" / f"compile_commands_{env_name}.log"
logfile_path.parent.mkdir(parents=True, exist_ok=True)


if (
    os.environ.get('_PIO_RECURSIVE_CALL') != 'true'
    and os.environ.get('PLATFORMIO_SETTING_FORCE_VERBOSE') != 'true'
    and not (compiledb_path.exists() and compiledb_path.stat().st_size > 0)
):
    current_targets = COMMAND_LINE_TARGETS[:]
    is_build_target = (
        not current_targets or
        any(target in ["build", "buildprog"] for target in current_targets)
    )
    if is_build_target:
        print(f"🔄 compile_commands.json not found, start verbose build for {env_name}...")
        env_vars = os.environ.copy()
        env_vars['PLATFORMIO_SETTING_FORCE_VERBOSE'] = 'true'
        env_vars['_PIO_RECURSIVE_CALL'] = 'true'
        with open(logfile_path, "w") as logfile:
            result = subprocess.run(
                ['pio', 'run', '-e', env_name, '--disable-auto-clean'],  # --disable-auto-clean hinzugefügt
                env=env_vars,
                stdout=logfile,
                stderr=subprocess.STDOUT
            )
        sys.exit(result.returncode)

# Integrated log2compdb components
DIRCHANGE_PATTERN = re.compile(r"(?P<action>\w+) directory '(?P<path>.+)'")
INFILE_PATTERN = re.compile(r"(?P<path>.+\.(cpp|cxx|cc|c|hpp|hxx|h))", re.IGNORECASE)

@dataclass
class CompileCommand:
    file: str
    output: str
    directory: str
    arguments: list

    @classmethod
    def from_cmdline(cls, cc_cmd: Path, cmd_args: list[str], directory=None) -> Optional["CompileCommand"]:
        """
        Create a CompileCommand from a command line.
        cmd_args should already be split with shlex.split or similar.
        
        Args:
            cc_cmd: Path to the compiler executable
            cmd_args: List of command line arguments
            directory: Optional working directory
        
        Returns:
            CompileCommand or None if no valid input file
        """
        # If the user-supplied compiler isn't in this supposed argument list, skip
        if cc_cmd.name not in cmd_args[0]:
            return None

        cmd_args = cmd_args[:]
        cmd_args[0] = str(cc_cmd)

        if directory is None:
            directory = Path.cwd()
        else:
            directory = Path(directory)

        input_path = None

        # Heuristic: look for a `-o <name>` and then look for a file matching that pattern
        try:
            output_index = cmd_args.index("-o")
            output_arg = cmd_args[output_index + 1]

            # Special case: if the output path is /dev/null, fallback to normal input path detection
            if output_arg == "/dev/null":
                output_path = None
            else:
                output_path = directory / Path(output_arg)

        except (ValueError, IndexError):
            output_index = None
            output_path = None

        if output_index is not None and output_path is not None:
            # Prefer input files that match the expected pattern
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
            # Fallback to regex
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
    name: str
    path: Path

    @classmethod
    def from_name(cls, compiler_name: str) -> "Compiler":
        """
        Create Compiler from name string.
        
        Args:
            compiler_name: Name of the compiler
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
        """
        for index, arg in enumerate(cmd_args):
            if self.name in arg or Path(arg).stem == self.name:
                return index
        raise ValueError(f"compiler invocation for {self.name} not found")

def parse_build_log_to_compile_commands(logfile_path: Path, compiler_names: list[str]) -> list[CompileCommand]:
    """
    Integrated log2compdb functionality - parse build log to compile commands.
    license = GPL-3.0-or-later  author = Nick Yamane
    
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

                # Handle directory changes
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

                # Look for compiler invocations
                for compiler in compilers:
                    try:
                        compiler_invocation_start = compiler.find_invocation_start(cmd_args)
                        entry = CompileCommand.from_cmdline(
                            compiler.path, 
                            cmd_args[compiler_invocation_start:], 
                            dirstack[-1]
                        )
                        
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
    PlatformIO LDF (Library Dependency Finder) cache optimizer with build order management.
    Designed specifically for lib_ldf_mode = chain and off modes.
    Invalidates cache only when #include directives change in source files.
    Includes complete build order management for correct linking.
    Implements a two-run strategy:
    1. First run: LDF active, create comprehensive cache
    2. Second run: LDF off, use cache for all dependencies
    
    No file copying - uses direct path references for maximum efficiency.
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

        # Compile commands
        compiledb_base = Path(self.project_dir) / ".pio" / "compiledb"
        self.compiledb_dir = compiledb_base
        self.compile_commands_file = compiledb_base / f"compile_commands_{self.env_name}.json"
        self.compile_commands_log_file = compiledb_base / f"compile_commands_{self.env_name}.log"

        # Build directory for direct path references (no copying)
        self.lib_build_dir = Path(self.project_dir) / ".pio" / "build" / self.env_name

        self.ALL_RELEVANT_EXTENSIONS = self.HEADER_EXTENSIONS | self.SOURCE_EXTENSIONS | self.CONFIG_EXTENSIONS
        self.real_packages_dir = Path(ProjectConfig.get_instance().get("platformio", "packages_dir"))
        self.build_log_file = Path(self.project_dir) / f"build_{self.env_name}.log"

    def validate_ldf_mode_compatibility(self):
        """
        Validate that the current LDF mode is compatible with caching.
        Supports 'chain' and 'off' modes for optimal caching.
        
        Returns:
            bool: True if LDF mode is compatible
        """
        try:
            # Get current LDF mode from environment or platformio.ini
            ldf_mode = self.env.GetProjectOption("lib_ldf_mode", "chain")

            compatible_modes = ["chain", "off"]
            
            if ldf_mode.lower() in compatible_modes:
                print(f"✅ LDF mode '{ldf_mode}' is compatible with caching")
                return True
            else:
                print(f"⚠ LDF mode '{ldf_mode}' not optimal for caching")
                print(f"💡 Recommended modes: {', '.join(compatible_modes)}")
                return False
                
        except Exception as e:
            print(f"⚠ Could not determine LDF mode: {e}")
            print("🔄 Assuming 'chain' mode for compatibility")
            return True

    def create_compiledb_integrated(self):
        """
        Create compile_commands.json using integrated log parsing functionality.
        No external dependencies required.
        """
        if self.compile_commands_file.exists():
            print(f"✅ {self.compile_commands_file} exists")
            return True

        # Look for build log
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

        # ESP8266/ESP32/ARM compiler names to look for
        compiler_names = [
            "xtensa-esp32-elf-gcc",
            "xtensa-esp32-elf-g++", 
            "riscv32-esp-elf-gcc",
            "riscv32-esp-elf-g++",
            "xtensa-lx106-elf-gcc",
            "xtensa-lx106-elf-g++",
            "arm-none-eabi-gcc",
            "arm-none-eabi-g++"
        ]

        try:
            # Use integrated parsing functionality
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

    def environment_specific_compiledb(self):
        """
        Environment-specific compiledb creation with integrated parsing.
        Captures build output for compile_commands.json generation.
        """
        current_targets = COMMAND_LINE_TARGETS[:]
        is_build_target = (
            not current_targets or
            any(target in ["build", "buildprog"] for target in current_targets)
        )

        if not is_build_target:
            return

        if self.compile_commands_file.exists():
            print(f"✅ {self.compile_commands_file} exists, using existing file")
            return

        print(f"COMPILE_COMMANDS_{self.env_name.upper()}.JSON MISSING")
        print("Creating after current build with integrated parser...")

        # Register post-build action to create compile_commands.json
        def create_compiledb_post_build(target, source, env):
            """Post-build action using integrated compile_commands generation"""
            try:
                print("🔧 Creating compile_commands.json with integrated parser...")
                success = self.create_compiledb_integrated()
                if success:
                    print("✅ compile_commands.json created successfully")
                else:
                    print("⚠ Failed to create compile_commands.json")
            except Exception as e:
                print(f"⚠ Error in post-build compile_commands generation: {e}")

        # Register the post-build action only for first run
        self.env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", create_compiledb_post_build)
        print("✅ Verbose mode activated for current build")
        print("✅ Integrated compile_commands.json generation configured")

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

    def _hash_platformio_ini_selective(self, ini_path=None):
        """
        Hash platformio*.ini but exclude LDF-related lines that are modified by the script.
    
        Args:
            ini_path (Path, optional): Path to specific ini file. Defaults to self.platformio_ini.
    
        Returns:
            str: MD5 hash of relevant platformio*.ini content
        """
        if ini_path is None:
            ini_path = self.platformio_ini
        
        if not ini_path.exists():
            return ""

        # Lines to exclude from hashing (case-insensitive)
        excluded_patterns = [
            'lib_ldf_mode',
            # Weitere LDF-relevante Optionen falls nötig:
            # 'lib_compat_mode',
            # 'lib_ignore'
        ]

        try:
            relevant_lines = []
            with ini_path.open('r', encoding='utf-8') as f:
                for line in f:
                    line_stripped = line.strip()
                    # Skip empty lines and comments
                    if not line_stripped or line_stripped.startswith(';') or line_stripped.startswith('#'):
                        continue
            
                    # Check if line contains excluded patterns
                    should_exclude = any(
                        pattern.lower() in line_stripped.lower() 
                        for pattern in excluded_patterns
                    )
            
                    if not should_exclude:
                        relevant_lines.append(line_stripped)
    
            # Hash only relevant content
            relevant_content = '\n'.join(sorted(relevant_lines))
            return hashlib.md5(relevant_content.encode()).hexdigest()
    
        except (IOError, OSError) as e:
            print(f"⚠ Could not read {ini_path}: {e}")
            return ""

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
                    if file_path.suffix in self.SOURCE_EXTENSIONS:
                        # Nur Include-Direktiven hashen
                        includes = self._extract_includes(file_path)
                        include_hash = hashlib.md5(str(sorted(includes)).encode()).hexdigest()
                        file_hashes[rel_path] = include_hash
                    elif file_path.suffix in self.HEADER_EXTENSIONS:
                        # Header komplett hashen (da sie die Abhängigkeiten definieren)
                        file_content = file_path.read_bytes()
                        file_hash = hashlib.md5(file_content).hexdigest()
                        file_hashes[rel_path] = file_hash
                    elif file_path.suffix in self.CONFIG_EXTENSIONS:
                        # Konfigurationsdateien komplett hashen
                        file_content = file_path.read_bytes()
                        file_hash = hashlib.md5(file_content).hexdigest()
                        file_hashes[rel_path] = file_hash

                except (IOError, OSError) as e:
                    print(f"⚠ Could not hash {file_path}: {e}")
                    continue

        # Add platformio*.ini hash
        project_path = Path(self.project_dir)
        for ini_path in project_path.glob('platformio*.ini'):
            if ini_path.exists() and ini_path.is_file():
                try:
                    platformio_hash = self._hash_platformio_ini_selective(ini_path)
                    if platformio_hash:
                        rel_ini_path = self._get_relative_path_from_project(ini_path)
                        file_hashes[rel_ini_path] = platformio_hash
                        print(f"✅ Hashed {ini_path.name} (selective)")
                except (IOError, OSError) as e:
                    print(f"⚠ Could not hash {ini_path}: {e}")

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

    def get_correct_build_order(self):
        """
        Combines compile_commands.json (order) with build artifacts (paths).
        Returns build order data directly as Python data structure.
        No intermediate files are written.
        
        Returns:
            dict: {
                'ordered_objects': list of dicts with 'order', 'source', 'object',
                'ordered_sources': list of source file paths,
                'ordered_object_files': list of object file paths,
                'include_paths': list of include paths,
                'defines': list of defines
            }
            or None if the file is missing or invalid.
        """
        # Load compile_commands.json for correct order
        if not self.compile_commands_file.exists():
            print(f"⚠ compile_commands_{self.env_name}.json not found")
            return None

        try:
            with self.compile_commands_file.open("r", encoding='utf-8') as f:
                compile_db = json.load(f)
        except Exception as e:
            print(f"✗ Error reading compile_commands.json: {e}")
            return None

        ordered_objects = []
        ordered_sources = []
        ordered_object_files = []
        include_paths = set()
        defines = set()

        for i, entry in enumerate(compile_db, 1):
            source_file = entry.get('file', '')
            
            # Handle both 'arguments' and 'command' formats
            if 'arguments' in entry:
                command = ' '.join(entry['arguments'])
            elif 'command' in entry:
                command = entry['command']
            else:
                print(f"⚠ Unsupported entry format in compile_commands.json (index {i})")
                continue

            # Extract object file from command
            obj_match = re.search(r'-o\s+(\S+\.o)', command)
            if obj_match:
                obj_file = obj_match.group(1)
                ordered_object_files.append(obj_file)
                ordered_objects.append({
                    'order': i,
                    'source': source_file,
                    'object': obj_file,
                })

            # Build order sources
            ordered_sources.append(source_file)

            # Extract include paths
            include_matches = re.findall(r'-I\s*([^\s]+)', command)
            for inc_path in include_matches:
                inc_path = inc_path.strip('"\'')
                if Path(inc_path).exists():
                    include_paths.add(str(Path(inc_path)))

            # Extract defines
            define_matches = re.findall(r'-D\s*([^\s]+)', command)
            for define in define_matches:
                defines.add(define)

        print(f"✓ Build order extracted directly from {self.compile_commands_file}")

        return {
            'ordered_objects': ordered_objects,
            'ordered_sources': ordered_sources,
            'ordered_object_files': ordered_object_files,
            'include_paths': sorted(include_paths),
            'defines': sorted(defines)
        }

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
            valid_sources = []
            valid_objects = []
            ordered_sources = build_order_data.get('ordered_sources', [])
            if ordered_sources:
                valid_sources = [s for s in ordered_sources if Path(s).exists()]
                if valid_sources:
                    self.env.Replace(SOURCES=valid_sources)
                    print(f"✅ Set SOURCES: {len(valid_sources)} files (exact reproduction)")
            
            ordered_object_files = build_order_data.get('ordered_object_files', [])
            if ordered_object_files:
                valid_objects = [obj for obj in ordered_object_files if Path(obj).exists()]
                if valid_objects:
                    self.env.Replace(OBJECTS=valid_objects)
                    print(f"✅ Set OBJECTS: {len(valid_objects)} files (exact reproduction)")

            if not valid_sources or not valid_objects:
                print("⚠ No sources/object files found")
                return False

            # Apply include paths and defines from compile commands
            self._apply_compile_data_to_environment(build_order_data)
            # CRITICAL: Implement correct linker order
            self._apply_correct_linker_order(valid_objects)
            print(f"✅ Linker order configured for correct symbol resolution")

            return True

        except Exception as e:
            print(f"✗ Error applying build vars: {e}")
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

    def collect_build_artifacts_paths(self):
        """
        Collect paths to build artifacts without copying them.
        Uses direct path references for maximum efficiency.
        
        Returns:
            dict: Artifact paths organized by type
        """
        if not self.lib_build_dir.exists():
            print(f"⚠ Build directory not found: {self.lib_build_dir}")
            return {}

        library_paths = []
        object_paths = []
        collected_count = 0

        print(f"📦 Collecting artifact paths from {self.lib_build_dir}")

        for root, dirs, files in os.walk(self.lib_build_dir):
            root_path = Path(root)
            for file in files:
                if file.endswith(('.a', '.o')):
                    file_path = root_path / file          
                    if file.endswith('.a'):
                        library_paths.append(str(file_path))
                    elif file.endswith('.o'):
                        object_paths.append(str(file_path))
                    
                    collected_count += 1

        print(f"📦 Collected {len(library_paths)} library paths (*.a)")
        print(f"📦 Collected {len(object_paths)} object paths (*.o)")
        print(f"📦 Total: {collected_count} artifact paths collected")

        return {
            'library_paths': library_paths,
            'object_paths': object_paths,
            'total_count': collected_count
        }

    def validate_artifact_paths(self, artifacts_data):
        """
        Validate that all artifact paths still exist.
        
        Args:
            artifacts_data (dict): Artifact data with paths
            
        Returns:
            dict: Validated artifact data with only existing paths
        """
        if not artifacts_data:
            return {}

        valid_library_paths = []
        valid_object_paths = []

        # Validate library paths
        for lib_path in artifacts_data.get('library_paths', []):
            if Path(lib_path).exists():
                valid_library_paths.append(lib_path)

        # Validate object paths
        for obj_path in artifacts_data.get('object_paths', []):
            if Path(obj_path).exists():
                valid_object_paths.append(obj_path)

        removed_count = (
            len(artifacts_data.get('library_paths', [])) - len(valid_library_paths) +
            len(artifacts_data.get('object_paths', [])) - len(valid_object_paths)
        )

        if removed_count > 0:
            print(f"⚠ {removed_count} artifact paths no longer exist and were removed")

        return {
            'library_paths': valid_library_paths,
            'object_paths': valid_object_paths,
            'total_count': len(valid_library_paths) + len(valid_object_paths)
        }

    def apply_ldf_cache_with_build_order(self, cache_data):
        """
        Extended application of LDF cache with build order integration.
        Combines library dependencies with correct build order.
        Uses direct path references without copying.
        
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

            # Apply cached artifacts using direct paths
            if artifacts and success_build_order:
                self._apply_cached_artifacts_direct(artifacts)

            return success_build_order

        except Exception as e:
            print(f"✗ Error in build order application: {e}")
            return False

    def _apply_cached_artifacts_direct(self, artifacts):
        """
        Apply cached artifacts to the SCons environment using direct paths.
        No copying involved - uses original build artifact locations.
        
        Args:
            artifacts (dict): Artifact information with direct paths
        """
        try:
            # Validate paths before applying -> overkill not needed
            #validated_artifacts = self.validate_artifact_paths(artifacts)
            validated_artifacts = artifacts
            

            # Apply static libraries using direct paths
            library_paths = validated_artifacts.get('library_paths', [])
            if library_paths:
                self.env.Append(LIBS=library_paths)
                print(f" ✅ Added {len(library_paths)} library paths (direct reference)")

            # Apply object files using direct paths
            object_paths = validated_artifacts.get('object_paths', [])
            if object_paths:
                self.env.Append(OBJECTS=object_paths)
                print(f" ✅ Added {len(object_paths)} object paths (direct reference)")

            total_artifacts = len(library_paths) + len(object_paths)
            print(f" 🚀 Total: {total_artifacts} artifacts applied via direct paths")

        except Exception as e:
            print(f"⚠ Warning applying cached artifacts: {e}")

    def save_combined_cache(self, cache_data):
        """
        Save combined cache data to file with signature verification.
        
        Args:
            cache_data (dict): Complete cache data to save
            
        Returns:
            bool: True if save was successful
        """
        try:
            # Ensure cache directory exists
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)

            # Add signature for integrity verification
            cache_data['signature'] = self.compute_signature(cache_data)

            # Save to file
            with self.cache_file.open('w') as f:
                json.dump(cache_data, f, indent=2)

            cache_size = self.cache_file.stat().st_size
            print(f"💾 Cache saved: {self.cache_file} ({cache_size} bytes)")
            return True

        except Exception as e:
            print(f"❌ Error saving cache: {e}")
            return False

    def load_combined_cache(self):
        """
        Load and validate combined cache data from file.
        
        Returns:
            dict or None: Cache data if valid, None if invalid or missing
        """
        if not self.cache_file.exists():
            return None

        try:
            with self.cache_file.open('r') as f:
                cache_data = json.load(f)

            # Verify signature
            stored_signature = cache_data.get('signature')
            if not stored_signature:
                print("⚠ Cache missing signature, invalidating")
                return None

            calculated_signature = self.compute_signature(cache_data)
            if stored_signature != calculated_signature:
                print("⚠ Cache signature mismatch, invalidating")
                return None

            # Verify project hash
            current_hash = self.get_project_hash_with_details()['final_hash']
            cached_hash = cache_data.get('project_hash')
            
            if current_hash != cached_hash:
                print("⚠ Project changed since cache creation, invalidating")
                return None

            print("✅ Valid cache found and loaded")
            return cache_data

        except Exception as e:
            print(f"⚠ Error loading cache: {e}")
            return None

    def save_ldf_cache_with_build_order(self, target, source, env):
        """
        Post-build action to save LDF cache with build order integration.
        Collects all build order and artifact information and saves it.
        """
        try:
            # We need to be in the first recusive run with --disable-auto-clean
            print("🔧 Collecting build order and artifacts for cache...")

            # Collect build order data
            build_order_data = self.get_correct_build_order()
            if not build_order_data:
                print("⚠ No build order data available, skipping cache save")
                return

            # Collect build artifacts
            artifacts_data = self.collect_build_artifacts_paths()

            # Create combined cache data
            combined_data = {
                'build_order': build_order_data,
                'artifacts': artifacts_data,
                'project_hash': self.get_project_hash_with_details()['final_hash'],
                'timestamp': datetime.datetime.now().isoformat(),
                'env_name': self.env_name,
                'linker_optimized': True,
                'direct_paths': True  # Flag indicating no file copying
            }

            # Save cache for future runs
            if self.save_combined_cache(combined_data):
                print("✅ LDF cache with build order saved successfully")
                print("🚀 Future builds will use cached dependencies with direct path references")

                if self.modify_platformio_ini_for_second_run('off'):
                    print("🔧 platformio.ini modified: lib_ldf_mode = off for NEXT build invocation")
                    print("🚀 Two-run strategy activated - next 'pio run' will use cache")
                else:
                    print("⚠ Failed to modify platformio.ini - No LDF cache use possible")
            else:
                print("⚠ Failed to save LDF cache")

        except Exception as e:
            print(f"❌ Error in post-build cache creation: {e}")

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
        Restore platformio.ini from backup.
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
        1. Compile first run in verbose mode (smart check) with --disable-auto-clean 
        2. Check for existing cache
        3. Cache gets created during/after the first (verbose) build
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
                # Restore original platformio.ini if backup exists
                if self.platformio_ini_backup.exists():
                    self.restore_ini_from_backup()
                print("⚠ Cache application failed, falling back to first run")

        # First run preparation: This will trigger the first build verbose automatically
        print("🔄 Preparing first run: Checking compile_commands...")

        # Create compiledb if missing using log2compdb at the end of the first compile run
        self.environment_specific_compiledb()

        # At this point, compiledb already exists
        print("✅ compile_commands available - proceeding with cache strategy")
        return True

    def create_complete_ldf_replacement_with_linker(self):
        """
        Creates a complete LDF replacement solution with optimized linker integration.
        Uses direct path references instead of copying files.
        
        Returns:
            bool: True if successful
        """
        print("\n=== Complete LDF Replacement Solution using existing cached build files ===")

        try:
            # Ensure compile_commands.json exists using log2compdb
            self.environment_specific_compiledb()

            # Create build order with compile data extraction
            build_order_data = self.get_correct_build_order()
            if not build_order_data:
                print("❌ Could not create build order")
                return self.fallback_to_standard_ldf()

            # Collect build artifacts paths
            artifacts_data = self.collect_build_artifacts_paths()

            # Combine with optimized linker logic
            combined_data = {
                'build_order': build_order_data,
                'artifacts': artifacts_data,
                'project_hash': self.get_project_hash_with_details()['final_hash'],
                'timestamp': datetime.datetime.now().isoformat(),
                'env_name': self.env_name,
                'linker_optimized': True,
                'direct_paths': True  # Flag indicating no file copying
            }

            # Save cache todo check if duplicate?
            #self.save_combined_cache(combined_data)

            # Apply everything with linker optimization
            success = self.apply_ldf_cache_with_build_order(combined_data)

            if success:
                print("✅ Complete LDF replacement active with direct path references")
                print("🚀 No file copying - maximum efficiency achieved")
                return True
            else:
                print("⚠ LDF replacement failed, falling back")
                return self.fallback_to_standard_ldf()

        except Exception as e:
            print(f"❌ Error in complete LDF replacement: {e}")
            return self.fallback_to_standard_ldf()

    def fallback_to_standard_ldf(self):
        """
        Fallback to standard LDF behavior if cache optimization fails.
        
        Returns:
            bool: Always returns True to allow standard build to proceed
        """
        print("🔄 Falling back to standard LDF behavior")
        print("📝 Cache will be created during this build for future optimization")
        return True

    def run_optimization(self):
        """
        Main entry point for LDF cache optimization.
        Implements intelligent caching strategy with direct path references.
        
        Returns:
            bool: True if optimization was applied or fallback is acceptable
        """
        try:
            print("\n" + "=" * 80)
            print("LDF CACHE OPTIMIZER - DIRECT PATH REFERENCE MODE")
            print("=" * 80)
            print(f"Environment: {self.env_name}")
            print(f"Project: {self.project_dir}")
            print(f"Build Dir: {self.lib_build_dir}")
            print("=" * 80)

            # Implement the two-run strategy with direct path references
            return self.implement_two_run_strategy()

        except Exception as e:
            print(f"❌ Critical error in LDF optimization: {e}")
            print(f"✗ Error saving LDF cache: {e}")
            return self.fallback_to_standard_ldf()


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
