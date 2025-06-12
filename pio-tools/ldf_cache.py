"""
PlatformIO Advanced Script for intelligent LDF caching with build order management.
Integrated with PlatformIO Core functions for maximum efficiency.

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
from SCons.Script import COMMAND_LINE_TARGETS, DefaultEnvironment
from SCons.Node import FS
from dataclasses import dataclass
from typing import Optional

# Import PlatformIO Core constants
SRC_HEADER_EXT = ["h", "hpp", "hxx", "h++", "hh", "inc", "tpp", "tcc"]
SRC_ASM_EXT = ["S", "spp", "SPP", "sx", "s", "asm", "ASM"]
SRC_C_EXT = ["c"]
SRC_CXX_EXT = ["cc", "cpp", "cxx", "c++"]
SRC_BUILD_EXT = SRC_C_EXT + SRC_CXX_EXT + SRC_ASM_EXT

# Global run state management
project_dir = env.subst("$PROJECT_DIR")
env_name = env.subst("$PIOENV")
compiledb_path = Path(project_dir) / ".pio" / "compiledb" / f"compile_commands_{env_name}.json"
logfile_path = Path(project_dir) / ".pio" / "compiledb" / f"compile_commands_{env_name}.log"
logfile_path.parent.mkdir(parents=True, exist_ok=True)

# Run state detection
def is_first_run():
    return (
        os.environ.get('_PIO_RECURSIVE_CALL') != 'true'
        and os.environ.get('PLATFORMIO_SETTING_FORCE_VERBOSE') != 'true'
        and not (compiledb_path.exists() and compiledb_path.stat().st_size > 0)
    )

def is_second_run():
    return os.environ.get('_PIO_RECURSIVE_CALL') == 'true'

# First run: Generate compile commands with verbose output
if is_first_run():
    current_targets = COMMAND_LINE_TARGETS[:]
    is_build_target = (
        not current_targets or
        any(target in ["build", "buildprog"] for target in current_targets)
    )
    if is_build_target:
        print(f"🔄 First run: Creating comprehensive cache for {env_name}...")
        env_vars = os.environ.copy()
        env_vars['PLATFORMIO_SETTING_FORCE_VERBOSE'] = 'true'
        env_vars['_PIO_RECURSIVE_CALL'] = 'true'
        with open(logfile_path, "w") as logfile:
            result = subprocess.run(
                ['pio', 'run', '-e', env_name, '--disable-auto-clean'],
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
        if cc_cmd.name not in cmd_args[0]:
            return None

        cmd_args = cmd_args[:]
        cmd_args[0] = str(cc_cmd)

        if directory is None:
            directory = Path.cwd()
        else:
            directory = Path(directory)

        input_path = None

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
        path = Path(compiler_name)
        return cls(name=compiler_name, path=path)

    def find_invocation_start(self, cmd_args: list[str]) -> int:
        for index, arg in enumerate(cmd_args):
            if self.name in arg or Path(arg).stem == self.name:
                return index
        raise ValueError(f"compiler invocation for {self.name} not found")

def parse_build_log_to_compile_commands(logfile_path: Path, compiler_names: list[str]) -> list[CompileCommand]:
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

                if dirchange_match := DIRCHANGE_PATTERN.search(line):
                    action = dirchange_match.group("action")
                    path = dirchange_match.group("path")
                    if action == "Leaving":
                        if len(dirstack) > 1:
                            dirstack.pop()
                    elif action == "Entering":
                        dirstack.append(path)
                    continue

                try:
                    cmd_args = shlex.split(line)
                except ValueError:
                    continue

                if not cmd_args:
                    continue

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
    PlatformIO LDF cache optimizer integrated with Core functions.
    Uses PlatformIO's native functions for maximum efficiency and compatibility.
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
        self.env = environment
        self.env_name = self.env.get("PIOENV")
        self.project_dir = self.env.subst("$PROJECT_DIR")
        self.src_dir = self.env.subst("$PROJECT_SRC_DIR")
        self.build_dir = self.env.subst("$BUILD_DIR")

        cache_base = Path(self.project_dir) / ".pio" / "ldf_cache"
        self.cache_file = cache_base / f"ldf_cache_{self.env_name}.py"
        self.ldf_cache_ini = Path(self.project_dir) / "ldf_cache.ini"
        self.platformio_ini = Path(self.project_dir) / "platformio.ini"
        self.platformio_ini_backup = Path(self.project_dir) / ".pio" / f"platformio_backup_{self.env_name}.ini"

        compiledb_base = Path(self.project_dir) / ".pio" / "compiledb"
        self.compiledb_dir = compiledb_base
        self.compile_commands_file = compiledb_base / f"compile_commands_{self.env_name}.json"
        self.compile_commands_log_file = compiledb_base / f"compile_commands_{self.env_name}.log"

        self.lib_build_dir = Path(self.project_dir) / ".pio" / "build" / self.env_name
        self.ALL_RELEVANT_EXTENSIONS = self.HEADER_EXTENSIONS | self.SOURCE_EXTENSIONS | self.CONFIG_EXTENSIONS

        # Cache application status tracking
        self._cache_applied_successfully = False

        # Register exit handler for cleanup
        self.register_exit_handler()

        # Execute based on run state
        if is_first_run():
            print("🔄 First run: Cache creation mode")
            self.execute_first_run()
        elif is_second_run():
            print("🔄 Second run: Cache application mode")
            self.execute_second_run()

    def execute_first_run(self):
        """First run: Create comprehensive cache with LDF active"""
        self.validate_ldf_mode_compatibility()
        
        # platformio.ini für zweiten Run vorbereiten
        self.backup_and_modify_platformio_ini()
        
        self.register_post_build_cache_creation()
        self.integrate_with_core_functions()

    def execute_second_run(self):
        """Second run: Apply cached dependencies with LDF disabled"""
        self._cache_applied_successfully = False
        
        try:
            cache_data = self.load_cache()
            if cache_data and self.validate_cache(cache_data):
                success = self.apply_ldf_cache_with_build_order(cache_data)
                if success:
                    self._cache_applied_successfully = True
                    print("✅ Cache applied successfully - keeping lib_ldf_mode=off")
                else:
                    print("❌ Cache application failed")
            else:
                print("⚠ No valid cache found, falling back to normal build")
        
        except Exception as e:
            print(f"❌ Error in second run: {e}")
            self._cache_applied_successfully = False
        
        finally:
            # Nur wiederherstellen wenn Cache NICHT erfolgreich angewendet wurde
            if not self._cache_applied_successfully:
                print("🔄 Restoring original platformio.ini due to cache failure")
                self.restore_platformio_ini()
            else:
                print("✅ Keeping modified platformio.ini for optimal performance")
            
            # Backup-Dateien nur löschen wenn Cache erfolgreich war
            if self._cache_applied_successfully:
                self.cleanup_backup_files()

    def register_exit_handler(self):
        """Register exit handler with conditional restore"""
        def cleanup_on_exit():
            try:
                # Prüfe ob Script-Instanz noch existiert und Cache-Status
                if hasattr(self, '_cache_applied_successfully'):
                    if not self._cache_applied_successfully:
                        self.restore_platformio_ini()
                else:
                    # Fallback: Wiederherstellen wenn Status unbekannt
                    self.restore_platformio_ini()
            except:
                pass  # Ignore errors during cleanup
        
        atexit.register(cleanup_on_exit)

    def backup_and_modify_platformio_ini(self):
        """Backup original platformio.ini and modify for second run"""
        try:
            # Backup erstellen
            if not self.platformio_ini_backup.exists():
                shutil.copy2(self.platformio_ini, self.platformio_ini_backup)
                print(f"✅ Backup created: {self.platformio_ini_backup}")

            # platformio.ini für zweiten Run modifizieren
            modified_lines = []
            ldf_mode_found = False
            
            with self.platformio_ini.open('r', encoding='utf-8') as f:
                for line in f:
                    line_stripped = line.strip()
                    
                    # LDF Mode auf 'off' setzen
                    if line_stripped.startswith('lib_ldf_mode'):
                        modified_lines.append('lib_ldf_mode = off  ; Modified by LDF Cache Optimizer\n')
                        ldf_mode_found = True
                        print("🔄 Modified lib_ldf_mode to 'off'")
                    else:
                        modified_lines.append(line)
            
            # Falls lib_ldf_mode nicht existiert, hinzufügen
            if not ldf_mode_found:
                # Suche nach [env:xxx] Sektion für aktuelles Environment
                env_section_found = False
                final_lines = []
                
                for line in modified_lines:
                    final_lines.append(line)
                    if line.strip() == f'[env:{self.env_name}]':
                        env_section_found = True
                        final_lines.append('lib_ldf_mode = off  ; Added by LDF Cache Optimizer\n')
                        print(f"✅ Added lib_ldf_mode = off to [env:{self.env_name}]")
                
                modified_lines = final_lines

            # Modifizierte platformio.ini schreiben
            with self.platformio_ini.open('w', encoding='utf-8') as f:
                f.writelines(modified_lines)
                
            print(f"✅ platformio.ini modified for second run")
            return True
            
        except Exception as e:
            print(f"❌ Error modifying platformio.ini: {e}")
            return False

    def restore_platformio_ini(self):
        """Restore original platformio.ini after second run"""
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

    def cleanup_backup_files(self):
        """Clean up backup files after successful build"""
        try:
            if self.platformio_ini_backup.exists():
                self.platformio_ini_backup.unlink()
                print("🧹 Backup files cleaned up")
        except Exception as e:
            print(f"⚠ Warning cleaning backup files: {e}")

    def validate_ldf_mode_compatibility(self):
        try:
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
            return True

    def register_post_build_cache_creation(self):
        """Register post-build action for cache creation (first run only)"""
        def create_cache_post_build(target, source, env):
            try:
                print("🔧 Creating comprehensive cache after build...")
                self.create_compiledb_integrated()
                cache_data = self.create_comprehensive_cache()
                if cache_data:
                    self.save_cache(cache_data)
                    print("✅ Cache created successfully")
            except Exception as e:
                print(f"⚠ Error in post-build cache creation: {e}")

        self.env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", create_cache_post_build)

    def integrate_with_core_functions(self):
        """Integrate with PlatformIO Core functions"""
        self.register_cache_middleware()
        self.integrate_with_project_deps()

    def register_cache_middleware(self):
        """Register cache middleware in PlatformIO's build pipeline"""
        def cache_middleware(env, node):
            if isinstance(node, FS.File):
                file_path = node.srcnode().get_path()
                if self.is_file_cached(file_path):
                    print(f"📦 Using cached analysis for {Path(file_path).name}")
            return node

        self.env.AddBuildMiddleware(cache_middleware, "*.cpp")
        self.env.AddBuildMiddleware(cache_middleware, "*.c")

    def integrate_with_project_deps(self):
        """Integrate cache application before ProcessProjectDeps"""
        original_process_deps = getattr(self.env, 'ProcessProjectDeps', None)
        
        def cached_process_deps():
            if is_second_run():
                cache_data = self.load_cache()
                if cache_data and self.validate_cache(cache_data):
                    self.apply_cache_to_scons_vars(cache_data)
                    print("✅ Applied LDF cache before ProcessProjectDeps")
            
            if original_process_deps:
                return original_process_deps()

        self.env.AddMethod(cached_process_deps, 'ProcessProjectDeps')

    def create_compiledb_integrated(self):
        """Create compile_commands.json using integrated log parsing"""
        if self.compile_commands_file.exists():
            print(f"✅ {self.compile_commands_file} exists")
            return True

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

        compiler_names = [
            "xtensa-esp32-elf-gcc", "xtensa-esp32-elf-g++", 
            "riscv32-esp-elf-gcc", "riscv32-esp-elf-g++",
            "xtensa-lx106-elf-gcc", "xtensa-lx106-elf-g++",
            "arm-none-eabi-gcc", "arm-none-eabi-g++"
        ]

        try:
            compile_commands = parse_build_log_to_compile_commands(build_log, compiler_names)

            if not compile_commands:
                print("❌ No compiler commands found in build log")
                return False

            self.compiledb_dir.mkdir(parents=True, exist_ok=True)

            json_entries = []
            for cmd in compile_commands:
                json_entries.append({
                    'file': cmd.file,
                    'output': cmd.output,
                    'directory': cmd.directory,
                    'arguments': cmd.arguments
                })

            with self.compile_commands_file.open('w') as f:
                json.dump(json_entries, f, indent=2)

            file_size = self.compile_commands_file.stat().st_size
            print(f"✅ Generated {self.compile_commands_file} ({file_size} bytes)")
            print(f"✅ Found {len(compile_commands)} compiler invocations")
            return True

        except Exception as e:
            print(f"❌ Error creating compile_commands.json: {e}")
            return False

    def collect_sources_via_core(self, src_filter=None):
        """Use PlatformIO's MatchSourceFiles instead of custom implementation"""
        try:
            sources = self.env.MatchSourceFiles(
                self.src_dir, 
                src_filter or self.env.get("SRC_FILTER"),
                SRC_BUILD_EXT
            )
            print(f"✅ Collected {len(sources)} source files via PlatformIO Core")
            return sources
        except Exception as e:
            print(f"⚠ Error collecting sources via Core: {e}")
            return []

    def get_correct_build_order(self):
        """Extract build order from compile_commands.json"""
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
            
            if 'arguments' in entry:
                command = ' '.join(entry['arguments'])
            elif 'command' in entry:
                command = entry['command']
            else:
                continue

            obj_match = re.search(r'-o\s+(\S+\.o)', command)
            if obj_match:
                obj_file = obj_match.group(1)
                ordered_object_files.append(obj_file)
                ordered_objects.append({
                    'order': i,
                    'source': source_file,
                    'object': obj_file,
                })

            ordered_sources.append(source_file)

            include_matches = re.findall(r'-I\s*([^\s]+)', command)
            for inc_path in include_matches:
                inc_path = inc_path.strip('"\'')
                if Path(inc_path).exists():
                    include_paths.add(str(Path(inc_path)))

            define_matches = re.findall(r'-D\s*([^\s]+)', command)
            for define in define_matches:
                defines.add(define)

        print(f"✓ Build order extracted from {self.compile_commands_file}")

        return {
            'ordered_objects': ordered_objects,
            'ordered_sources': ordered_sources,
            'ordered_object_files': ordered_object_files,
            'include_paths': sorted(include_paths),
            'defines': sorted(defines)
        }

    def collect_build_artifacts_paths(self):
        """Collect paths to build artifacts without copying"""
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

        return {
            'library_paths': library_paths,
            'object_paths': object_paths,
            'total_count': collected_count
        }

    def get_project_hash_with_details(self):
        """Calculate project hash for cache validation"""
        file_hashes = {}
        
        src_path = Path(self.src_dir)
        
        for file_path in src_path.rglob('*'):
            if file_path.is_dir() or self._is_ignored_directory(file_path.parent):
                continue
                
            if file_path.suffix in self.ALL_RELEVANT_EXTENSIONS:
                try:
                    rel_path = self._get_relative_path_from_project(file_path)
                    if file_path.suffix in self.SOURCE_EXTENSIONS:
                        includes = self._extract_includes(file_path)
                        include_hash = hashlib.md5(str(sorted(includes)).encode()).hexdigest()
                        file_hashes[rel_path] = include_hash
                    elif file_path.suffix in self.HEADER_EXTENSIONS:
                        file_content = file_path.read_bytes()
                        file_hash = hashlib.md5(file_content).hexdigest()
                        file_hashes[rel_path] = file_hash
                    elif file_path.suffix in self.CONFIG_EXTENSIONS:
                        file_content = file_path.read_bytes()
                        file_hash = hashlib.md5(file_content).hexdigest()
                        file_hashes[rel_path] = file_hash

                except (IOError, OSError) as e:
                    print(f"⚠ Could not hash {file_path}: {e}")
                    continue

        project_path = Path(self.project_dir)
        for ini_path in project_path.glob('platformio*.ini'):
            if ini_path.exists() and ini_path.is_file():
                try:
                    platformio_hash = self._hash_platformio_ini_selective(ini_path)
                    if platformio_hash:
                        rel_ini_path = self._get_relative_path_from_project(ini_path)
                        file_hashes[rel_ini_path] = platformio_hash
                except (IOError, OSError) as e:
                    print(f"⚠ Could not hash {ini_path}: {e}")

        combined_content = json.dumps(file_hashes, sort_keys=True)
        final_hash = hashlib.sha256(combined_content.encode()).hexdigest()

        return {
            'file_hashes': file_hashes,
            'final_hash': final_hash,
            'file_count': len(file_hashes)
        }

    def create_comprehensive_cache(self):
        """Create comprehensive cache data"""
        try:
            print("🔧 Creating comprehensive cache...")
            
            project_hash = self.get_project_hash_with_details()
            build_order = self.get_correct_build_order()
            artifacts = self.collect_build_artifacts_paths()
            
            if not build_order:
                print("⚠ No build order data available")
                return None

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

            cache_data['signature'] = self.compute_signature(cache_data)
            
            print(f"✅ Cache created with {project_hash['file_count']} files")
            return cache_data

        except Exception as e:
            print(f"❌ Error creating cache: {e}")
            return None

    def save_cache(self, cache_data):
        """Save cache data to file"""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            with self.cache_file.open('w') as f:
                f.write("# LDF Cache Data - Auto-generated\n")
                f.write("# Do not edit manually\n\n")
                f.write("cache_data = ")
                f.write(pprint.pformat(cache_data, width=120, depth=None))
                f.write("\n")
            
            print(f"✅ Cache saved to {self.cache_file}")
            return True
            
        except Exception as e:
            print(f"❌ Error saving cache: {e}")
            return False

    def load_cache(self):
        """Load cache data from file"""
        if not self.cache_file.exists():
            return None

        try:
            cache_globals = {}
            with self.cache_file.open('r') as f:
                exec(f.read(), cache_globals)
            
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
        """Validate cache integrity and freshness"""
        if not cache_data:
            return False

        try:
            stored_signature = cache_data.get('signature')
            if not stored_signature:
                print("⚠ Cache missing signature")
                return False

            computed_signature = self.compute_signature(cache_data)
            if stored_signature != computed_signature:
                print("⚠ Cache signature mismatch")
                return False

            current_hash = self.get_project_hash_with_details()
            if cache_data.get('project_hash') != current_hash['final_hash']:
                print("⚠ Project files changed, cache invalid")
                return False

            print("✅ Cache validation successful")
            return True

        except Exception as e:
            print(f"⚠ Cache validation error: {e}")
            return False

    def apply_ldf_cache_with_build_order(self, cache_data):
        """Apply cached dependencies with correct build order"""
        try:
            build_order = cache_data.get('build_order', {})
            artifacts = cache_data.get('artifacts', {})

            if not build_order:
                print("❌ No build order data in cache")
                return False

            print("🔧 Applying build order with artifact integration...")

            # Alle Cache-Anwendungen müssen erfolgreich sein
            build_order_success = self.apply_build_order_to_environment(build_order)
            scons_vars_success = self.apply_cache_to_scons_vars(cache_data)
            
            if build_order_success and scons_vars_success:
                print("✅ LDF cache applied successfully")
                return True
            else:
                print("❌ Partial cache application failure")
                return False

        except Exception as e:
            print(f"✗ Error applying LDF cache: {e}")
            return False

    def apply_build_order_to_environment(self, build_order_data):
        """Apply correct build order to SCons environment"""
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
                    print(f"✅ Set SOURCES: {len(valid_sources)} files")
            
            ordered_object_files = build_order_data.get('ordered_object_files', [])
            if ordered_object_files:
                valid_objects = [obj for obj in ordered_object_files if Path(obj).exists()]
                if valid_objects:
                    self.env.Replace(OBJECTS=valid_objects)
                    print(f"✅ Set OBJECTS: {len(valid_objects)} files")

            if not valid_sources or not valid_objects:
                print("⚠ No sources/object files found")
                return False

            self._apply_compile_data_to_environment(build_order_data)
            self._apply_correct_linker_order(valid_objects)

            return True

        except Exception as e:
            print(f"✗ Error applying build order: {e}")
            return False

    def apply_cache_to_scons_vars(self, cache_data):
        """Apply cache data directly to SCons variables using PlatformIO Core methods"""
        try:
            build_order = cache_data.get('build_order', {})
            
            # Use PlatformIO's ProcessFlags for robust flag handling
            if 'defines' in build_order:
                defines_flags = [f"-D{define}" for define in build_order['defines']]
                self.env.ProcessFlags(defines_flags)
                print(f"✅ Applied {len(build_order['defines'])} defines via ProcessFlags")
            
            # Apply include paths
            if 'include_paths' in build_order:
                include_flags = [f"-I{path}" for path in build_order['include_paths']]
                self.env.ProcessFlags(include_flags)
                print(f"✅ Applied {len(build_order['include_paths'])} include paths via ProcessFlags")

            # Apply artifacts to SCons variables
            artifacts = cache_data.get('artifacts', {})
            if 'library_paths' in artifacts:
                valid_libs = [lib for lib in artifacts['library_paths'] if Path(lib).exists()]
                if valid_libs:
                    self.env.Prepend(LIBS=valid_libs)
                    print(f"✅ Applied {len(valid_libs)} library paths")

            return True

        except Exception as e:
            print(f"⚠ Warning applying cache to SCons vars: {e}")
            return False

    def _apply_compile_data_to_environment(self, build_order_data):
        """Apply compile data to environment"""
        try:
            include_paths = build_order_data.get('include_paths', [])
            if include_paths:
                existing_paths = [str(p) for p in self.env.get('CPPPATH', [])]
                new_paths = [p for p in include_paths if p not in existing_paths]
                if new_paths:
                    self.env.Append(CPPPATH=new_paths)
                    print(f"✅ Added {len(new_paths)} include paths")

            defines = build_order_data.get('defines', [])
            if defines:
                existing_defines = [str(d) for d in self.env.get('CPPDEFINES', [])]
                new_defines = [d for d in defines if d not in existing_defines]
                if new_defines:
                    self.env.Append(CPPDEFINES=new_defines)
                    print(f"✅ Added {len(new_defines)} defines")

        except Exception as e:
            print(f"⚠ Warning applying compile data: {e}")

    def _apply_correct_linker_order(self, object_files):
        """Apply correct linker order for symbol resolution"""
        try:
            current_linkflags = self.env.get('LINKFLAGS', [])

            custom_linkcom = (
                "$LINK -o $TARGET "
                "${_long_sources_hook(__env__, SOURCES)} "
                "$LINKFLAGS "
                "$__RPATH $_LIBDIRFLAGS $_LIBFLAGS"
            )

            self.env.Replace(LINKCOM=custom_linkcom)

            optimized_linkflags = []
            optimized_linkflags.extend(["-Wl,--start-group"])

            for flag in current_linkflags:
                if flag not in optimized_linkflags:
                    optimized_linkflags.append(flag)

            optimized_linkflags.extend([
                "-Wl,--end-group",
                "-Wl,--gc-sections",
            ])

            self.env.Replace(LINKFLAGS=optimized_linkflags)
            print(f"🔗 Linker optimized with {len(optimized_linkflags)} flags")

        except Exception as e:
            print(f"⚠ Warning during linker optimization: {e}")

    def is_file_cached(self, file_path):
        """Check if file is in cache"""
        cache_data = self.load_cache()
        if not cache_data:
            return False
        
        rel_path = self._get_relative_path_from_project(file_path)
        return rel_path in cache_data.get('file_hashes', {})

    def compute_signature(self, data):
        """Compute signature for cache validation"""
        data_copy = data.copy()
        data_copy.pop('signature', None)
        data_str = json.dumps(data_copy, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()

    def _normalize_path(self, path):
        """Platform-independent path normalization"""
        if not path:
            return ""
        normalized = Path(path).resolve()
        return str(normalized).replace(os.sep, '/')

    def _is_ignored_directory(self, dir_path):
        """Check if directory should be ignored"""
        if not dir_path:
            return False
        path_obj = Path(dir_path)
        if path_obj.name in self.IGNORE_DIRS:
            return True
        for part in path_obj.parts:
            if part in self.IGNORE_DIRS:
                return True
        return False

    def _get_relative_path_from_project(self, file_path):
        """Get relative path from project root"""
        try:
            file_path = Path(file_path).resolve()
            project_dir = Path(self.project_dir).resolve()
            rel_path = file_path.relative_to(project_dir)
            return str(rel_path).replace(os.sep, '/')
        except (ValueError, OSError):
            return str(Path(file_path)).replace(os.sep, '/')

    def _extract_includes(self, file_path):
        """Extract #include directives from source file"""
        includes = set()
        try:
            file_path = Path(file_path)
            with file_path.open('r', encoding='utf-8', errors='ignore') as f:
                for line in f:
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
        """Hash platformio.ini excluding LDF-related lines"""
        if ini_path is None:
            ini_path = self.platformio_ini
        
        if not ini_path.exists():
            return ""

        excluded_patterns = ['lib_ldf_mode']

        try:
            relevant_lines = []
            with ini_path.open('r', encoding='utf-8') as f:
                for line in f:
                    line_stripped = line.strip()
                    if not line_stripped or line_stripped.startswith(';') or line_stripped.startswith('#'):
                        continue
            
                    should_exclude = any(
                        pattern.lower() in line_stripped.lower() 
                        for pattern in excluded_patterns
                    )
            
                    if not should_exclude:
                        relevant_lines.append(line_stripped)
    
            relevant_content = '\n'.join(sorted(relevant_lines))
            return hashlib.md5(relevant_content.encode()).hexdigest()
    
        except (IOError, OSError) as e:
            print(f"⚠ Could not read {ini_path}: {e}")
            return ""

# Initialize the LDF Cache Optimizer
try:
    optimizer = LDFCacheOptimizer(env)
    print("✅ LDF Cache Optimizer initialized successfully")
except Exception as e:
    print(f"❌ Error initializing LDF Cache Optimizer: {e}")
    import traceback
    traceback.print_exc()
