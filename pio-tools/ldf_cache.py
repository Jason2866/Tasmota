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

class LDFCacheOptimizer:
    """
    Intelligent LDF (Library Dependency Finder) cache optimizer for PlatformIO.
    
    This class manages caching of library dependency resolution results to speed up
    subsequent builds when no include-relevant changes have been made to the project.
    """
    
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
        
        # Include-relevant file types
        self.include_relevant_extensions = {
            # Standard C/C++
            '.h', '.hpp', '.hxx', '.h++', '.hh',
            '.c', '.cpp', '.cxx', '.c++', '.cc', '.ino',
            # Template files
            '.tpp', '.tcc', '.inc',
            # Config/Manifest files
            '.json', '.properties', '.txt', '.ini'
        }
    
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
        except:
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
                        stripped.startswith('#if') or 
                        stripped.startswith('#ifdef') or
                        stripped.startswith('#ifndef') or
                        stripped.startswith('#endif') or
                        stripped.startswith('#else') or
                        stripped.startswith('#elif') or
                        (stripped.startswith('#define') and 
                         any(keyword in stripped.upper() for keyword in ['INCLUDE', 'PATH', 'CONFIG']))):
                        include_lines.append(stripped)
            
            return hashlib.sha256('\n'.join(include_lines).encode()).hexdigest()[:16]
            
        except Exception:
            # Fallback: file hash
            return self._get_file_hash(file_path)
    
    def get_project_hash(self):
        """
        Generate include-relevant hash for cache validation.
        
        This method creates a comprehensive hash of all files and content that could
        affect library dependency resolution, including headers, preprocessor directives
        in source files, and configuration files.
        
        Returns:
            str: SHA256 hash representing the current state of include-relevant project content
        """
        hash_data = []
        
        # platformio.ini
        ini_file = os.path.join(self.project_dir, "platformio.ini")
        if os.path.exists(ini_file):
            hash_data.append(self._get_file_hash(ini_file))
        
        # Scan source directory
        if os.path.exists(self.src_dir):
            for root, _, files in os.walk(self.src_dir):
                for file in sorted(files):
                    file_path = os.path.join(root, file)
                    file_ext = os.path.splitext(file)[1].lower()
                    
                    if file_ext in {'.h', '.hpp', '.hxx', '.h++', '.hh', '.inc', '.tpp', '.tcc'}:
                        # Header files: complete hash
                        hash_data.append(self._get_file_hash(file_path))
                    elif file_ext in {'.c', '.cpp', '.cxx', '.c++', '.cc', '.ino'}:
                        # Source files: include-relevant hash
                        hash_data.append(self.get_include_relevant_hash(file_path))
        
        # Scan include directories
        for inc_path in self.env.get('CPPPATH', []):
            inc_dir = str(inc_path)
            if os.path.exists(inc_dir) and inc_dir != self.src_dir:
                for root, _, files in os.walk(inc_dir):
                    for file in sorted(files):
                        if file.endswith(('.h', '.hpp', '.hxx', '.inc', '.tpp')):
                            file_path = os.path.join(root, file)
                            hash_data.append(self._get_file_hash(file_path))
        
        # Library directory
        lib_dir = os.path.join(self.project_dir, "lib")
        if os.path.exists(lib_dir):
            for root, _, files in os.walk(lib_dir):
                for file in sorted(files):
                    if file.endswith(('.h', '.hpp', '.json', '.properties')):
                        file_path = os.path.join(root, file)
                        hash_data.append(self._get_file_hash(file_path))
        
        return hashlib.sha256(''.join(hash_data).encode()).hexdigest()[:16]
    
    def load_and_validate_cache(self):
        """
        Load cache with hash validation.
        
        Loads the existing cache file and validates it against the current project state
        by comparing environment settings and include-relevant content hashes.
        
        Returns:
            dict or None: Cache data if valid, None if invalid or non-existent
        """
        if not os.path.exists(self.cache_file):
            return None
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Environment check
            if cache_data.get('pioenv') != self.env['PIOENV']:
                print("🔄 Environment changed")
                return None
            
            # Hash comparison
            current_hash = self.get_project_hash()
            cached_hash = cache_data.get('project_hash')
            
            if current_hash != cached_hash:
                print("🔄 Include-relevant changes detected - cache invalid")
                return None
            
            print("✅ No include-relevant changes - cache usable")
            return cache_data
            
        except Exception as e:
            print(f"⚠ Cache validation failed: {e}")
            return None
    
    def apply_ldf_cache(self, cache_data):
        """
        Apply LDF cache with SCons methods.
        
        Restores all cached library dependency finder results including include paths,
        library paths, compiler flags, and other build settings.
        
        Args:
            cache_data (dict): Previously cached LDF results
            
        Raises:
            Exception: If cache application fails
        """
        try:
            # Disable LDF
            self.env.Replace(LIB_LDF_MODE="off")
            
            ldf_results = cache_data['ldf_results']
            
            # Include paths (both variants for compatibility)
            includes = ldf_results.get('includes') or ldf_results.get('CPPPATH', [])
            if includes:
                self.env.PrependUnique(CPPPATH=includes)
            
            # Library paths and names
            lib_paths = ldf_results.get('lib_paths') or ldf_results.get('LIBPATH', [])
            if lib_paths:
                self.env.PrependUnique(LIBPATH=lib_paths)
            
            libs = ldf_results.get('libs') or ldf_results.get('LIBS', [])
            if libs:
                self.env.PrependUnique(LIBS=libs)
            
            # Preprocessor defines
            defines = ldf_results.get('defines') or ldf_results.get('CPPDEFINES', [])
            if defines:
                self.env.Append(CPPDEFINES=defines)
            
            # Source filter - with Replace instead of direct assignment
            src_filter = ldf_results.get('src_filter') or ldf_results.get('SRC_FILTER')
            if src_filter:
                self.env.Replace(SRC_FILTER=src_filter)
            
            # Compiler flags
            cc_flags = ldf_results.get('cc_flags') or ldf_results.get('CCFLAGS', [])
            if cc_flags:
                self.env.Append(CCFLAGS=cc_flags)
            
            cxx_flags = ldf_results.get('cxx_flags') or ldf_results.get('CXXFLAGS', [])
            if cxx_flags:
                self.env.Append(CXXFLAGS=cxx_flags)
            
            # Linker flags
            link_flags = ldf_results.get('link_flags') or ldf_results.get('LINKFLAGS', [])
            if link_flags:
                self.env.Append(LINKFLAGS=link_flags)
            
            lib_count = len(libs)
            include_count = len(includes)
            print(f"📦 Complete LDF cache applied:")
            print(f"   {lib_count} Libraries, {include_count} Include paths")
            print("   All compiler flags and build settings restored")
            
        except Exception as e:
            print(f"✗ Error applying LDF cache: {e}")
            raise
    
    def save_ldf_cache(self, target=None, source=None, env_arg=None, **kwargs):
        """
        Save complete LDF results to cache.
        
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
            cache_data = {
                # Include-relevant hash
                'project_hash': self.get_project_hash(),
                'pioenv': self.env['PIOENV'],
                'timestamp': datetime.datetime.now().isoformat(),
                
                # ALL relevant SCons variables
                'ldf_results': {
                    # Include paths
                    'includes': [str(p) for p in self.env.get('CPPPATH', [])],
                    'CPPPATH': [str(p) for p in self.env.get('CPPPATH', [])],
                    
                    # Library paths and names
                    'lib_paths': [str(p) for p in self.env.get('LIBPATH', [])],
                    'LIBPATH': [str(p) for p in self.env.get('LIBPATH', [])],
                    'libs': self.env.get('LIBS', []),
                    'LIBS': self.env.get('LIBS', []),
                    
                    # Preprocessor defines
                    'defines': self.env.get('CPPDEFINES', []),
                    'CPPDEFINES': self.env.get('CPPDEFINES', []),
                    
                    # Source filter
                    'src_filter': self.env.get('SRC_FILTER', ''),
                    'SRC_FILTER': self.env.get('SRC_FILTER', ''),
                    
                    # Compiler flags
                    'cc_flags': self.env.get('CCFLAGS', []),
                    'CCFLAGS': self.env.get('CCFLAGS', []),
                    'cxx_flags': self.env.get('CXXFLAGS', []),
                    'CXXFLAGS': self.env.get('CXXFLAGS', []),
                    
                    # Linker flags
                    'link_flags': self.env.get('LINKFLAGS', []),
                    'LINKFLAGS': self.env.get('LINKFLAGS', [])
                }
            }
            
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, default=str)
            
            lib_count = len(cache_data['ldf_results'].get('LIBS', []))
            print(f"💾 LDF cache saved: {lib_count} Libraries")
            
        except Exception as e:
            print(f"✗ Error saving LDF cache: {e}")
    
    def setup_ldf_caching(self):
        """
        Main logic for intelligent LDF caching.
        
        Orchestrates the entire caching process: validates existing cache,
        applies it if valid, or sets up cache saving for new builds.
        """
        print("\n=== LDF Cache Optimizer v1.0 ===")
        
        cache_data = self.load_and_validate_cache()
        
        if cache_data:
            print("🚀 Using LDF cache (no include-relevant changes)")
            self.apply_ldf_cache(cache_data)
        else:
            print("🔄 LDF recalculation required")
            silent_action = self.env.Action(self.save_ldf_cache)
            silent_action.strfunction = lambda target, source, env: '' # hack to silence scons command outputs
            self.env.AddPostAction("checkprogsize", silent_action)
        
        print("================================")

# Cache management commands
def clear_ldf_cache():
    """
    Delete LDF cache file.
    
    Removes the cached LDF results, forcing a complete recalculation
    on the next build.
    """
    cache_file = os.path.join(env.subst("$BUILD_DIR"), "ldf_cache.json")
    if os.path.exists(cache_file):
        os.remove(cache_file)
        print("✓ LDF Cache deleted")
    else:
        print("ℹ No LDF Cache present")

def show_ldf_cache_info():
    """
    Display cache information.
    
    Shows details about the current cache including creation time,
    environment, library count, and content hash.
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
            print(f"Hash:         {cache_data.get('project_hash', 'unknown')[:16]}...")
            print("=" * 25)
            
        except Exception as e:
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
