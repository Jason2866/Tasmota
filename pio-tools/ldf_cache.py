# ldf_cache.py
"""
PlatformIO Advanced Script for intelligent LDF caching.
This module optimizes build performance through selective LDF caching and restoring

Copyright: Jason2866
"""

Import("env")
import os
import json
import hashlib
import datetime
import time
from platformio.project.config import ProjectConfig

def disable_ldf_early(target, source, env):
    """Pre-action to disable LDF before any build steps"""
    env.Replace(LIB_LDF_MODE="off")
    print("🔧 LDF disabled via pre-action")

# Set pre-action to disable LDF before everything else
env.AddPreAction("buildprog", disable_ldf_early)

class LDFCacheOptimizer:
    """
    Intelligent LDF (Library Dependency Finder) cache optimizer for PlatformIO.
    
    This class manages caching of library dependency resolution results to speed up
    subsequent builds when no include-relevant changes have been made to the project.
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
        self.cache_file = os.path.join(self.env.subst("$BUILD_DIR"), "ldf_cache.json")
        self.project_dir = self.env.subst("$PROJECT_DIR")
        self.src_dir = self.env.subst("$PROJECT_SRC_DIR")
        
        self.ALL_RELEVANT_EXTENSIONS = self.HEADER_EXTENSIONS | self.SOURCE_EXTENSIONS | self.CONFIG_EXTENSIONS
    
    def _get_file_hash(self, file_path):
        """
        Generate hash of a single file.
        
        Args:
            file_path (str): Path to the file to hash
            
        Returns:
            str: SHA256 hash of the file content (first 16 characters) or "unreadable" if error
        """
        try:
            with open(file_path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()[:16]
        except (IOError, OSError, PermissionError):
            return "unreadable"
    
    def get_include_relevant_hash(self, file_path):
        """
        Generate hash only from include-relevant lines in source files.
        
        This method extracts preprocessor directives and include statements that
        affect dependency resolution, ignoring implementation details that don't
        impact library dependencies.
        
        Args:
            file_path (str): Path to the source file
            
        Returns:
            str: SHA256 hash of include-relevant content (first 16 characters)
        """
        include_lines = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    stripped = line.strip()
                    
                    # Skip comments
                    if stripped.startswith('//'):
                        continue
                    
                    # Include-relevant lines
                    if (stripped.startswith('#include') or 
                        (stripped.startswith('#define') and 
                         any(keyword in stripped.upper() for keyword in ['INCLUDE', 'PATH', 'CONFIG']))):
                        include_lines.append(stripped)
            
            content = '\n'.join(include_lines)
            return hashlib.sha256(content.encode()).hexdigest()[:16]
            
        except (IOError, OSError, PermissionError, UnicodeDecodeError):
            # Fallback: file hash
            return self._get_file_hash(file_path)
    
    def safe_serialize_scons_value(self, value):
        """
        Safe serialization of SCons values to prevent JSON corruption.
        
        Args:
            value: SCons value to serialize
            
        Returns:
            Serializable value (list, string, or None)
        """
        if value is None:
            return None
        
        # SCons NodeList or similar iterable objects
        if hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
            try:
                # Try to serialize as list
                return [str(item) for item in value if item is not None]
            except (TypeError, AttributeError):
                return str(value)
        
        # Simple values
        elif isinstance(value, (str, int, float, bool)):
            return value
        
        # Everything else as string
        else:
            return str(value)
    
    def is_platformio_path(self, path):
        """
        Check if path belongs to PlatformIO installation.
        
        Args:
            path (str): Path to check
            
        Returns:
            bool: True if path is part of PlatformIO installation
        """
        # Get PlatformIO paths
        platformio_paths = set()
        
        # Main PlatformIO directory
        if 'PLATFORMIO_CORE_DIR' in os.environ:
            platformio_paths.add(os.path.normpath(os.environ['PLATFORMIO_CORE_DIR']))
        
        # Standard PlatformIO paths
        pio_home = os.path.join(ProjectConfig.get_instance().get("platformio", "platforms_dir"))
        platformio_paths.add(os.path.normpath(pio_home))
        
        # Project-specific .pio directories
        platformio_paths.add(os.path.normpath(os.path.join(self.project_dir, ".pio")))
        
        norm_path = os.path.normpath(path)
        return any(norm_path.startswith(pio_path) for pio_path in platformio_paths)
    
    def get_project_hash_with_details(self):
        """
        Generate hash with detailed file tracking and optimized early filtering.
        Excludes all PlatformIO-installed components (framework, tools, etc.)
        
        Returns:
            dict: Contains final_hash, file_hashes dict, total_files count, and timing info
        """
        start_time = time.time()
        
        file_hashes = {}
        hash_data = []
        
        # Generated file to skip (PlatformIO merges .ino files)
        generated_cpp = os.path.basename(self.project_dir).lower() + ".ino.cpp"
        #print(f"🔍 Generated file to skip: {generated_cpp}")
        
        # Process platformio.ini first
        ini_file = os.path.join(self.project_dir, "platformio.ini")
        if os.path.exists(ini_file):
            ini_hash = self._get_file_hash(ini_file)
            hash_data.append(ini_hash)
            file_hashes['platformio.ini'] = ini_hash
            #print(f"🔍 platformio.ini: {ini_hash}")
        
        # Collect all scan directories
        scan_dirs = []
        
        # Add source directory
        if os.path.exists(self.src_dir):
            scan_dirs.append(('source', self.src_dir))
        
        # Add library directory
        lib_dir = os.path.join(self.project_dir, "lib")
        if os.path.exists(lib_dir) and not self.is_platformio_path(lib_dir):
            scan_dirs.append(('library', lib_dir))
        
        # Add include directories (filtered)
        #print(f"🔍 Filtering include directories...")
        for inc_path in self.env.get('CPPPATH', []):
            inc_dir = str(inc_path)
            
            # Skip PlatformIO paths
            if self.is_platformio_path(inc_dir):
                #print(f"🚫 Skipping PlatformIO include path: {inc_dir}")
                continue
            
            # Skip variants and other system paths explicitly
            if any(skip_dir in inc_dir for skip_dir in ['variants', '.platformio', '.pio']):
                #print(f"🚫 Skipping system path: {inc_dir}")
                continue
            
            if os.path.exists(inc_dir) and inc_dir != self.src_dir:
                scan_dirs.append(('include', inc_dir))
                #print(f"✅ Including path: {inc_dir}")
        
        total_scanned = 0
        total_relevant = 0
        scan_start_time = time.time()
        
        # Single-pass scanning with early filtering and smart hashing
        for dir_type, scan_dir in scan_dirs:
            print(f"🔍 Scanning {dir_type} directory: {scan_dir}")
            
            try:
                for root, dirs, files in os.walk(scan_dir):
                    # Skip PlatformIO paths
                    if self.is_platformio_path(root):
                        #print(f"🚫 Skipping PlatformIO subpath: {root}")
                        continue
                    
                    # Filter ignored directories
                    dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]
                    
                    # Early file type filtering - MAJOR OPTIMIZATION
                    relevant_files = []
                    for file in files:
                        total_scanned += 1
                        file_ext = os.path.splitext(file)[1].lower()
                        
                        # Early extension filter - skip irrelevant files immediately
                        if file_ext in self.ALL_RELEVANT_EXTENSIONS:
                            relevant_files.append((file, file_ext))
                            total_relevant += 1
                    
                    # Process only relevant files
                    for file, file_ext in relevant_files:
                        # Skip generated files
                        if file == generated_cpp:
                            #print(f"🚫 Skipping generated file: {file}")
                            continue
                        
                        file_path = os.path.join(root, file)
                        
                        # Smart hashing based on file type
                        if file_ext in self.HEADER_EXTENSIONS or file_ext in self.CONFIG_EXTENSIONS:
                            # Header and config files: complete hash
                            file_hash = self._get_file_hash(file_path)
                        elif file_ext in self.SOURCE_EXTENSIONS:
                            # Source files: include-relevant hash only
                            file_hash = self.get_include_relevant_hash(file_path)
                        else:
                            continue  # Should not happen due to early filter
                        
                        file_hashes[file_path] = file_hash
                        hash_data.append(file_hash)
            
            except (IOError, OSError, PermissionError) as e:
                print(f"⚠ Warning: Could not scan directory {scan_dir}: {e}")
                continue
        
        scan_elapsed = time.time() - scan_start_time
        
        final_hash = hashlib.sha256(''.join(hash_data).encode()).hexdigest()[:16]
        
        total_elapsed = time.time() - start_time
        
        print(f"🔍 Scanning completed in {scan_elapsed:.2f}s")
        print(f"🔍 Total hash calculation completed in {total_elapsed:.2f}s")
        print(f"🔍 Scan complete: {total_scanned} files scanned, {total_relevant} relevant, {len(file_hashes)} hashed")
        
        if total_scanned > 0:
            print(f"🔍 Performance: {((total_relevant/total_scanned)*100):.1f}% relevance ratio")
        
        #print(f"🔍 Final project hash: {final_hash}")
        
        return {
            'final_hash': final_hash,
            'file_hashes': file_hashes,
            'total_files': len(file_hashes),
            'scan_time': scan_elapsed,
            'total_time': total_elapsed,
            'files_scanned': total_scanned,
            'files_relevant': total_relevant
        }
    
    def get_project_hash(self):
        """
        Compatibility wrapper for get_project_hash_with_details.
        
        Returns:
            str: Project hash
        """
        return self.get_project_hash_with_details()['final_hash']
    
    def compare_hash_details(self, current_hashes, cached_hashes):
        """
        Compare hash details and show only differences.
        
        Args:
            current_hashes (dict): Current file hashes
            cached_hashes (dict): Cached file hashes
        """
        differences_found = 0
        
        # New files
        for file_path, current_hash in current_hashes.items():
            if file_path not in cached_hashes:
                print(f"   ➕ NEW: {file_path} -> {current_hash}")
                differences_found += 1
        
        # Changed files
        for file_path, current_hash in current_hashes.items():
            if file_path in cached_hashes:
                cached_hash = cached_hashes[file_path]
                if current_hash != cached_hash:
                    print(f"   🔄 CHANGED: {file_path}")
                    print(f"      Old: {cached_hash}")
                    print(f"      New: {current_hash}")
                    differences_found += 1
        
        # Deleted files
        for file_path in cached_hashes:
            if file_path not in current_hashes:
                print(f"   ➖ DELETED: {file_path}")
                differences_found += 1
        
        print(f"\n   Total differences: {differences_found}")
        print(f"   Current files: {len(current_hashes)}")
        print(f"   Cached files: {len(cached_hashes)}")
    
    def load_and_validate_cache(self):
        """
        Load cache with targeted hash debugging - only show differences.
        
        Loads the existing cache file and validates it against the current project state
        by comparing environment settings and include-relevant content hashes.
        
        Returns:
            dict or None: Cache data if valid, None if invalid or non-existent
        """
        if not os.path.exists(self.cache_file):
            print("🔍 No cache file exists")
            return None
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Environment check
            if cache_data.get('pioenv') != self.env['PIOENV']:
                print(f"🔄 Environment changed: {cache_data.get('pioenv')} -> {self.env['PIOENV']}")
                return None
            
            # Hash comparison with difference detection
            print("🔍 Comparing hashes (showing only differences)...")
            comparison_start = time.time()
            
            current_hash_details = self.get_project_hash_with_details()
            cached_hash = cache_data.get('project_hash')
            cached_hash_details = cache_data.get('hash_details', {})
            
            current_hash = current_hash_details['final_hash']
            
            comparison_elapsed = time.time() - comparison_start
            
            print(f"\n🔍 Hash comparison completed in {comparison_elapsed:.2f}s:")
            print(f"   Current:  {current_hash}")
            print(f"   Cached:   {cached_hash}")
            print(f"   Match:    {current_hash == cached_hash}")
            
            if current_hash != cached_hash:
                print("\n🔄 Files with DIFFERENT hashes:")
                self.compare_hash_details(current_hash_details['file_hashes'], cached_hash_details)
                return None
            
            print("✅ No include-relevant changes - cache usable")
            return cache_data
            
        except (IOError, OSError, PermissionError, json.JSONDecodeError) as e:
            print(f"⚠ Cache validation failed: {e}")
            return None
    
    def apply_ldf_cache(self, cache_data):
        """
        Apply LDF cache with SCons methods and validation.
        
        Restores all cached library dependency finder results including include paths,
        library paths, compiler flags, and other build settings.
        
        Args:
            cache_data (dict): Previously cached LDF results
            
        Returns:
            bool: True if successfully applied, False otherwise
        """
        try:
            apply_start = time.time()
            
            ldf_results = cache_data.get('ldf_results', {})
            
            # Validate loaded data
            for key, value in ldf_results.items():
                if value and not isinstance(value, (list, str)):
                    print(f"⚠ Warning: Unexpected cached type for {key}: {type(value)}")
                    return False
            
            # Safe restoration
            if ldf_results.get('CPPPATH'):
                self.env.PrependUnique(CPPPATH=ldf_results['CPPPATH'])
            
            if ldf_results.get('LIBPATH'):
                self.env.PrependUnique(LIBPATH=ldf_results['LIBPATH'])
            
            if ldf_results.get('LIBS'):
                self.env.PrependUnique(LIBS=ldf_results['LIBS'])
            
            if ldf_results.get('CPPDEFINES'):
                self.env.AppendUnique(CPPDEFINES=ldf_results['CPPDEFINES'])
            
            if ldf_results.get('SRC_FILTER'):
                self.env.Replace(SRC_FILTER=ldf_results['SRC_FILTER'])
            
            if ldf_results.get('CCFLAGS'):
                self.env.AppendUnique(CCFLAGS=ldf_results['CCFLAGS'])
            
            if ldf_results.get('CXXFLAGS'):
                self.env.AppendUnique(CXXFLAGS=ldf_results['CXXFLAGS'])
            
            if ldf_results.get('LINKFLAGS'):
                self.env.AppendUnique(LINKFLAGS=ldf_results['LINKFLAGS'])
            
            apply_elapsed = time.time() - apply_start
            
            lib_count = len(ldf_results.get('LIBS', []))
            include_count = len(ldf_results.get('CPPPATH', []))
            print(f"📦 LDF cache applied in {apply_elapsed:.3f}s: {lib_count} Libraries, {include_count} Include paths")
            
            return True
            
        except (KeyError, TypeError, AttributeError) as e:
            print(f"✗ Error applying LDF cache: {e}")
            # Delete cache on errors
            if os.path.exists(self.cache_file):
                try:
                    os.remove(self.cache_file)
                    print("🗑️ Corrupted cache deleted")
                except (IOError, OSError, PermissionError):
                    print("⚠ Could not delete corrupted cache file")
            return False
    
    def save_ldf_cache(self, target=None, source=None, env_arg=None, **kwargs):
        """
        Save complete LDF results to cache with safe SCons serialization.
        
        This method is called as a post-action after successful build to capture
        all SCons variables and build settings determined by the LDF process.
        
        Args:
            target: SCons target (unused)
            source: SCons source (unused) 
            env_arg: SCons environment (unused, uses self.env)
        """
        if self.env.get("LIB_LDF_MODE") == "off":
            return  # Cache was used
        
        try:
            save_start = time.time()
            print("💾 Saving LDF cache...")
            
            hash_details = self.get_project_hash_with_details()
            
            # Safe extraction of SCons variables
            def extract_scons_var(var_name):
                try:
                    value = self.env.get(var_name, [])
                    return self.safe_serialize_scons_value(value)
                except (KeyError, TypeError, AttributeError) as e:
                    print(f"⚠ Warning: Could not serialize {var_name}: {e}")
                    return []
            
            cache_data = {
                'project_hash': hash_details['final_hash'],
                'hash_details': hash_details['file_hashes'],
                'pioenv': str(self.env['PIOENV']),
                'timestamp': datetime.datetime.now().isoformat(),
                'performance': {
                    'scan_time': hash_details.get('scan_time', 0),
                    'total_time': hash_details.get('total_time', 0),
                    'files_scanned': hash_details.get('files_scanned', 0),
                    'files_relevant': hash_details.get('files_relevant', 0)
                },
                
                'ldf_results': {
                    'CPPPATH': extract_scons_var('CPPPATH'),
                    'LIBPATH': extract_scons_var('LIBPATH'), 
                    'LIBS': extract_scons_var('LIBS'),
                    'CPPDEFINES': extract_scons_var('CPPDEFINES'),
                    'SRC_FILTER': str(self.env.get('SRC_FILTER', '')),
                    'CCFLAGS': extract_scons_var('CCFLAGS'),
                    'CXXFLAGS': extract_scons_var('CXXFLAGS'),
                    'LINKFLAGS': extract_scons_var('LINKFLAGS')
                }
            }
            
            # Validation before saving
            for key, value in cache_data['ldf_results'].items():
                if not isinstance(value, (list, str, type(None))):
                    print(f"⚠ Warning: Unexpected type for {key}: {type(value)}")
            
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            
            # Safe JSON serialization
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False, default=str)
            
            # Verification by reading back
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                test_load = json.load(f)
            
            save_elapsed = time.time() - save_start
            lib_count = len(cache_data['ldf_results'].get('LIBS', []))
            print(f"💾 LDF cache saved and verified in {save_elapsed:.3f}s: {lib_count} Libraries")
            
        except (IOError, OSError, PermissionError, TypeError, ValueError) as e:
            print(f"✗ Error saving LDF cache: {e}")
            # Delete cache file on error
            if os.path.exists(self.cache_file):
                try:
                    os.remove(self.cache_file)
                except (IOError, OSError, PermissionError):
                    print("⚠ Could not delete failed cache file")
    
    def setup_ldf_caching(self):
        """
        Main logic for intelligent LDF caching.
        
        Orchestrates the entire caching process: validates existing cache,
        applies it if valid, or sets up cache saving for new builds.
        """
        setup_start = time.time()
        print("\n=== LDF Cache Optimizer v1.0 ===")
        
        cache_data = self.load_and_validate_cache()
        
        if cache_data:
            print("🚀 Using LDF cache")
            success = self.apply_ldf_cache(cache_data)
            if not success:
                # Bei Fehler: LDF wieder aktivieren
                self.env.Replace(LIB_LDF_MODE="chain")
                print("🔄 Cache failed, re-enabling LDF")
        else:
            # Kein Cache: LDF wieder aktivieren für diesen Build
            self.env.Replace(LIB_LDF_MODE="chain")
            print("🔄 No cache, LDF recalculation required")
            # Cache nach dem Build speichern
            silent_action = self.env.Action(self.save_ldf_cache)
            silent_action.strfunction = lambda target, source, env: '' # hack to silence scons command outputs
            self.env.AddPostAction("checkprogsize", silent_action)
        
        setup_elapsed = time.time() - setup_start
        print(f"⏱️ LDF Cache setup completed in {setup_elapsed:.3f}s")
        print("=" * 60)

# Cache management commands
def clear_ldf_cache():
    """
    Delete LDF cache file.
    
    Removes the cached LDF results, forcing a complete recalculation
    on the next build.
    """
    cache_file = os.path.join(env.subst("$BUILD_DIR"), "ldf_cache.json")
    if os.path.exists(cache_file):
        try:
            os.remove(cache_file)
            print("✓ LDF Cache deleted")
        except (IOError, OSError, PermissionError) as e:
            print(f"✗ Error deleting cache: {e}")
    else:
        print("ℹ No LDF Cache present")

def show_ldf_cache_info():
    """
    Display cache information.
    
    Shows details about the current cache including creation time,
    environment, library count, content hash, and performance metrics.
    """
    cache_file = os.path.join(env.subst("$BUILD_DIR"), "ldf_cache.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            print(f"\n=== LDF Cache Info ===")
            print(f"Created:      {cache_data.get('timestamp', 'unknown')}")
            print(f"Environment:  {cache_data.get('pioenv', 'unknown')}")
            print(f"Libraries:    {len(cache_data.get('ldf_results', {}).get('LIBS', []))}")
            print(f"Include paths: {len(cache_data.get('ldf_results', {}).get('CPPPATH', []))}")
            print(f"Hash:         {cache_data.get('project_hash', 'unknown')}")
            
            # Performance metrics
            perf = cache_data.get('performance', {})
            if perf:
                print(f"\n--- Performance Metrics ---")
                print(f"Scan time:    {perf.get('scan_time', 0):.2f}s")
                print(f"Total time:   {perf.get('total_time', 0):.2f}s")
                print(f"Files scanned: {perf.get('files_scanned', 0)}")
                print(f"Files relevant: {perf.get('files_relevant', 0)}")
                if perf.get('files_scanned', 0) > 0:
                    relevance = (perf.get('files_relevant', 0) / perf.get('files_scanned', 1)) * 100
                    print(f"Relevance:    {relevance:.1f}%")
            
            print("=" * 25)
            
        except (IOError, OSError, PermissionError, json.JSONDecodeError) as e:
            print(f"Error reading cache info: {e}")
    else:
        print("No LDF Cache present")

def force_ldf_rebuild():
    """
    Force LDF recalculation.
    
    Clears the cache and ensures LDF will be recalculated on the next build,
    regardless of whether changes were detected.
    """
    clear_ldf_cache()
    print("LDF will be recalculated on next build")

# Custom Targets
env.AlwaysBuild(env.Alias("clear_ldf_cache", None, clear_ldf_cache))
env.AlwaysBuild(env.Alias("ldf_cache_info", None, show_ldf_cache_info))
env.AlwaysBuild(env.Alias("force_ldf_rebuild", None, force_ldf_rebuild))

# Initialize LDF Cache Optimizer
ldf_optimizer = LDFCacheOptimizer(env)
ldf_optimizer.setup_ldf_caching()
