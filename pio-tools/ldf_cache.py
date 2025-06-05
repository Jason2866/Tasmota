# ldf_cache.py
"""
PlatformIO Advanced Script for intelligent LDF caching with full environment dump.
This module optimizes build performance through selective LDF caching and restoring,
using SCons native serialization, smart cache invalidation, cache file signature,
and PlatformIO version compatibility check.

Copyright: Jason2866
"""

Import("env")
import os
import hashlib
import datetime
import time
import re
from platformio.project.config import ProjectConfig

class LDFCacheOptimizer:
    """
    Intelligent LDF (Library Dependency Finder) cache optimizer for PlatformIO.

    This class manages caching of library dependency resolution results to speed up
    subsequent builds when no include-relevant changes have been made to the project.
    Uses SCons native serialization (env.Dump) to store and restore all build variables
    with smart hash-based cache invalidation, cache file signature, and PlatformIO version check.
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
        Initialize the LDF Cache Optimizer.

        Args:
            environment: PlatformIO SCons environment object
        """
        self.env = environment
        self.project_dir = self.env.subst("$PROJECT_DIR")
        self.src_dir = self.env.subst("$PROJECT_SRC_DIR")
        self.cache_file = os.path.join(self.project_dir, ".pio", "ldf_cache", f"ldf_cache_{self.env['PIOENV']}.py")
        self.platformio_ini = os.path.join(self.project_dir, "platformio.ini")
        self.original_ldf_mode = None
        self.ALL_RELEVANT_EXTENSIONS = self.HEADER_EXTENSIONS | self.SOURCE_EXTENSIONS | self.CONFIG_EXTENSIONS

    # ------------------- PlatformIO.ini Modification Methods -------------------

    def find_lib_ldf_mode_in_ini(self):
        """
        Find all occurrences of lib_ldf_mode in platformio.ini across all sections.

        Returns:
            list: List of dictionaries with section, line_number, and line content
        """
        lib_ldf_mode_lines = []
        try:
            if os.path.exists(self.platformio_ini):
                with open(self.platformio_ini, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                for i, line in enumerate(lines):
                    if 'lib_ldf_mode' in line.lower():
                        section = None
                        for j in range(i, -1, -1):
                            if lines[j].strip().startswith('[') and lines[j].strip().endswith(']'):
                                section = lines[j].strip()
                                break
                        lib_ldf_mode_lines.append({
                            'section': section, 
                            'line_number': i+1, 
                            'line': line.strip(),
                            'line_index': i
                        })
                return lib_ldf_mode_lines
            else:
                print(f"❌ platformio.ini not found: {self.platformio_ini}")
                return []
        except Exception as e:
            print(f"❌ Error reading platformio.ini: {e}")
            return []

    def modify_platformio_ini(self, new_ldf_mode):
        """
        Modify or add lib_ldf_mode in platformio.ini.

        Args:
            new_ldf_mode (str): New LDF mode ('off' or 'chain')
        Returns:
            bool: True if modification was successful, False otherwise
        """
        try:
            ldf_entries = self.find_lib_ldf_mode_in_ini()
            if ldf_entries:
                first_entry = ldf_entries[0]
                with open(self.platformio_ini, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                current_line = lines[first_entry['line_index']]
                match = re.search(r'lib_ldf_mode\s*=\s*(\w+)', current_line)
                if match:
                    self.original_ldf_mode = match.group(1)
                else:
                    self.original_ldf_mode = "chain"
                lines[first_entry['line_index']] = re.sub(
                    r'lib_ldf_mode\s*=\s*\w+', 
                    f'lib_ldf_mode = {new_ldf_mode}', 
                    current_line
                )
                with open(self.platformio_ini, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                print(f"🔧 Modified {first_entry['section']}: lib_ldf_mode = {new_ldf_mode}")
                return True
            else:
                print("🔍 No existing lib_ldf_mode found, adding to [platformio] section")
                return self.add_lib_ldf_mode_to_platformio_section(new_ldf_mode)
        except Exception as e:
            print(f"❌ Error modifying platformio.ini: {e}")
            return False

    def add_lib_ldf_mode_to_platformio_section(self, new_ldf_mode):
        """
        Add lib_ldf_mode to [platformio] section if not present.

        Args:
            new_ldf_mode (str): New LDF mode to add
        Returns:
            bool: True if addition was successful, False otherwise
        """
        try:
            with open(self.platformio_ini, 'r', encoding='utf-8') as f:
                content = f.read()
            self.original_ldf_mode = "chain"
            platformio_section = re.search(r'\[platformio\]', content)
            if platformio_section:
                insert_pos = platformio_section.end()
                new_content = (content[:insert_pos] + 
                             f'\nlib_ldf_mode = {new_ldf_mode}' + 
                             content[insert_pos:])
            else:
                new_content = f'[platformio]\nlib_ldf_mode = {new_ldf_mode}\n\n' + content
            with open(self.platformio_ini, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"🔧 Added to [platformio]: lib_ldf_mode = {new_ldf_mode}")
            return True
        except Exception as e:
            print(f"❌ Error adding lib_ldf_mode: {e}")
            return False

    def restore_platformio_ini(self):
        """
        Restore the original lib_ldf_mode in platformio.ini after build.
        """
        if self.original_ldf_mode is None:
            return
        try:
            ldf_entries = self.find_lib_ldf_mode_in_ini()
            if ldf_entries:
                first_entry = ldf_entries[0]
                with open(self.platformio_ini, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                if self.original_ldf_mode == "chain":
                    lines.pop(first_entry['line_index'])
                else:
                    lines[first_entry['line_index']] = re.sub(
                        r'lib_ldf_mode\s*=\s*\w+', 
                        f'lib_ldf_mode = {self.original_ldf_mode}', 
                        lines[first_entry['line_index']]
                    )
                with open(self.platformio_ini, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                print(f"🔧 Restored lib_ldf_mode = {self.original_ldf_mode}")
        except Exception as e:
            print(f"❌ Error restoring platformio.ini: {e}")

    # ------------------- Smart Hash Generation & Comparison -------------------

    def _get_file_hash(self, file_path):
        """
        Generate SHA256 hash of a file.

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
                    if stripped.startswith('//'):
                        continue
                    if (stripped.startswith('#include') or 
                        (stripped.startswith('#define') and 
                         any(keyword in stripped.upper() for keyword in ['INCLUDE', 'PATH', 'CONFIG']))):
                        include_lines.append(stripped)
            content = '\n'.join(include_lines)
            return hashlib.sha256(content.encode()).hexdigest()[:16]
        except (IOError, OSError, PermissionError, UnicodeDecodeError):
            return self._get_file_hash(file_path)

    def is_platformio_path(self, path):
        """
        Check if path belongs to PlatformIO installation.

        Args:
            path (str): Path to check

        Returns:
            bool: True if path is part of PlatformIO installation
        """
        platformio_paths = set()
        if 'PLATFORMIO_CORE_DIR' in os.environ:
            platformio_paths.add(os.path.normpath(os.environ['PLATFORMIO_CORE_DIR']))
        pio_home = os.path.join(ProjectConfig.get_instance().get("platformio", "platforms_dir"))
        platformio_paths.add(os.path.normpath(pio_home))
        platformio_paths.add(os.path.normpath(os.path.join(self.project_dir, ".pio")))
        norm_path = os.path.normpath(path)
        return any(norm_path.startswith(pio_path) for pio_path in platformio_paths)

    def compare_hash_details(self, current_hashes, cached_hashes):
        """
        Compare hash details and show only differences.
        """
        differences_found = 0
        for file_path, current_hash in current_hashes.items():
            if file_path not in cached_hashes:
                print(f"   ➕ NEW: {file_path} -> {current_hash}")
                differences_found += 1
        for file_path, current_hash in current_hashes.items():
            if file_path in cached_hashes:
                cached_hash = cached_hashes[file_path]
                if current_hash != cached_hash:
                    print(f"   🔄 CHANGED: {file_path}")
                    print(f"      Old: {cached_hash}")
                    print(f"      New: {current_hash}")
                    differences_found += 1
        for file_path in cached_hashes:
            if file_path not in current_hashes:
                print(f"   ➖ DELETED: {file_path}")
                differences_found += 1
        print(f"\n   Total differences: {differences_found}")
        print(f"   Current files: {len(current_hashes)}")
        print(f"   Cached files: {len(cached_hashes)}")

    def get_project_hash_with_details(self):
        """
        Generate hash with detailed file tracking and optimized early filtering.
        Excludes all PlatformIO-installed components and lib_ldf_mode settings.

        Returns:
            dict: Contains final_hash, file_hashes dict, total_files count, and timing info
        """
        start_time = time.time()
        file_hashes = {}
        hash_data = []
        generated_cpp = os.path.basename(self.project_dir).lower() + ".ino.cpp"
        if os.path.exists(self.platformio_ini):
            try:
                with open(self.platformio_ini, 'r', encoding='utf-8') as f:
                    ini_content = f.read()
                filtered_content = re.sub(r'lib_ldf_mode\s*=\s*\w+\n?', '', ini_content)
                ini_hash = hashlib.sha256(filtered_content.encode()).hexdigest()[:16]
                hash_data.append(ini_hash)
                file_hashes['platformio.ini'] = ini_hash
            except Exception as e:
                print(f"⚠ Error reading platformio.ini: {e}")
        scan_dirs = []
        if os.path.exists(self.src_dir):
            scan_dirs.append(('source', self.src_dir))
        lib_dir = os.path.join(self.project_dir, "lib")
        if os.path.exists(lib_dir) and not self.is_platformio_path(lib_dir):
            scan_dirs.append(('library', lib_dir))
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
                        if file_ext in self.HEADER_EXTENSIONS or file_ext in self.CONFIG_EXTENSIONS:
                            file_hash = self._get_file_hash(file_path)
                        elif file_ext in self.SOURCE_EXTENSIONS:
                            file_hash = self.get_include_relevant_hash(file_path)
                        else:
                            continue
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
        return {
            'final_hash': final_hash,
            'file_hashes': file_hashes,
            'total_files': len(file_hashes),
            'scan_time': scan_elapsed,
            'total_time': total_elapsed,
            'files_scanned': total_scanned,
            'files_relevant': total_relevant
        }

    # ------------------- Enhanced Cache Validation ----------------------------

    def load_and_validate_cache(self):
        """
        Load and validate cache with smart hash comparison, signature, and PIO version.

        Returns:
            dict or None: Cache data if valid, None if invalid or non-existent
        """
        if not os.path.exists(self.cache_file):
            print("🔍 No cache file exists")
            return None
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_content = f.read()
            cache_data = eval(cache_content.split('\n\n', 1)[1])

            # PlatformIO version check
            current_pio_version = getattr(self.env, "PioVersion", lambda: "unknown")()
            if cache_data.get('pio_version') != current_pio_version:
                print(f"⚠ Cache invalid: PlatformIO version changed from {cache_data.get('pio_version')} to {current_pio_version}")
                clear_ldf_cache()
                return None

            # Signature check (integrity)
            expected_signature = cache_data.get('signature')
            actual_signature = self.compute_signature(cache_data)
            if expected_signature != actual_signature:
                print("⚠ Cache invalid: Signature mismatch. Possible file tampering or corruption.")
                clear_ldf_cache()
                return None

            # Environment check
            if cache_data.get('pioenv') != self.env['PIOENV']:
                print(f"🔄 Environment changed: {cache_data.get('pioenv')} -> {self.env['PIOENV']}")
                clear_ldf_cache()
                return None

            # Detailed hash comparison
            print("🔍 Comparing hashes (showing only differences)...")
            current_hash_details = self.get_project_hash_with_details()
            if cache_data.get('project_hash') != current_hash_details['final_hash']:
                print("\n🔄 Project files changed:")
                self.compare_hash_details(current_hash_details['file_hashes'], cache_data.get('hash_details', {}))
                clear_ldf_cache()
                return None

            print("✅ No include-relevant changes - cache valid")
            return cache_data

        except Exception as e:
            print(f"⚠ Cache validation failed: {e}")
            clear_ldf_cache()
            return None

    def compute_signature(self, cache_data):
        """
        Compute a signature for the cache to detect tampering.

        Args:
            cache_data (dict): The cache data dictionary

        Returns:
            str: SHA256 signature string
        """
        # Exclude the signature field itself
        data = dict(cache_data)
        data.pop('signature', None)
        raw = repr(data).encode()
        return hashlib.sha256(raw).hexdigest()

    # ------------------- SCons Environment Handling ---------------------------

    def convert_all_scons_objects(self, obj, depth=0, max_depth=10):
        """
        Rekursive Konvertierung aller SCons-Objekte zu Debug-Strings.
        """
        if depth > max_depth:
            return f"<MAX_DEPTH_REACHED:{type(obj).__name__}>"
        
        obj_type_str = str(type(obj))
        
        # SCons.Node Objekte - verschiedene Typen
        if 'SCons.Node' in obj_type_str:
            try:
                # Versuche verschiedene Pfad-Attribute
                if hasattr(obj, 'abspath'):
                    return f"<Node:abspath={obj.abspath}>"
                elif hasattr(obj, 'path'):
                    return f"<Node:path={obj.path}>"
                elif hasattr(obj, 'relpath'):
                    return f"<Node:relpath={obj.relpath}>"
                elif hasattr(obj, 'get_path'):
                    return f"<Node:get_path={obj.get_path()}>"
                else:
                    return f"<Node:{obj_type_str}={str(obj)}>"
            except Exception as e:
                return f"<Node:ERROR={e}>"
        
        # Andere SCons-Objekte
        elif 'SCons' in obj_type_str:
            try:
                return f"<SCons:{type(obj).__name__}={str(obj)}>"
            except:
                return f"<SCons:{type(obj).__name__}:UNCONVERTIBLE>"
        
        # Container-Typen rekursiv verarbeiten
        elif isinstance(obj, dict):
            converted_dict = {}
            for key, value in obj.items():
                try:
                    converted_key = self.convert_all_scons_objects(key, depth+1, max_depth)
                    converted_value = self.convert_all_scons_objects(value, depth+1, max_depth)
                    converted_dict[converted_key] = converted_value
                except Exception as e:
                    converted_dict[str(key)] = f"<CONVERSION_ERROR:{e}>"
            return converted_dict
        
        elif isinstance(obj, (list, tuple)):
            converted_list = []
            for item in obj:
                try:
                    converted_item = self.convert_all_scons_objects(item, depth+1, max_depth)
                    converted_list.append(converted_item)
                except Exception as e:
                    converted_list.append(f"<CONVERSION_ERROR:{e}>")
            return converted_list if isinstance(obj, list) else tuple(converted_list)
        
        # Normale Objekte
        else:
            return obj

    def debug_dump_all_scons_objects(self):
        """
        Debug-Ausgabe aller SCons-Objekte im Environment.
        """
        try:
            # Vollständigen Environment-Dump holen
            env_dump = self.env.Dump(format='pretty')
            scons_vars = eval(env_dump)
            
            print("\n=== DEBUG: All SCons Objects Conversion ===")
            
            # Statistiken sammeln
            total_vars = len(scons_vars)
            scons_objects_found = 0
            conversion_errors = 0
            
            converted_vars = {}
            
            for var_name, var_value in scons_vars.items():
                try:
                    # Prüfe ob SCons-Objekte enthalten sind
                    var_str = str(var_value)
                    contains_scons = 'SCons' in var_str
                    
                    if contains_scons:
                        scons_objects_found += 1
                        print(f"\n🔍 {var_name} (contains SCons objects):")
                        print(f"   Original: {var_str[:200]}{'...' if len(var_str) > 200 else ''}")
                    
                    # Konvertiere alle SCons-Objekte
                    converted_value = self.convert_all_scons_objects(var_value)
                    converted_vars[var_name] = converted_value
                    
                    if contains_scons:
                        print(f"   Converted: {str(converted_value)[:200]}{'...' if len(str(converted_value)) > 200 else ''}")
                    
                except Exception as e:
                    conversion_errors += 1
                    converted_vars[var_name] = f"<CONVERSION_ERROR:{e}>"
                    print(f"❌ Error converting {var_name}: {e}")
            
            print(f"\n📊 Debug Statistics:")
            print(f"   Total variables: {total_vars}")
            print(f"   Variables with SCons objects: {scons_objects_found}")
            print(f"   Conversion errors: {conversion_errors}")
            print(f"   Successfully converted: {total_vars - conversion_errors}")
            
            # Vollständige konvertierte Ausgabe
            print(f"\n=== All Converted Variables ===")
            for var_name, var_value in converted_vars.items():
                try:
                    print(f"{var_name}: {var_value}")
                except Exception as e:
                    print(f"{var_name}: <OUTPUT_ERROR:{e}>")
            
            return converted_vars
            
        except Exception as e:
            print(f"❌ Debug dump failed: {e}")
            return {}

    def get_comprehensive_ldf_vars(self):
        """
        Extrahiere alle LDF-relevanten Variablen und konvertiere Node-Objekte.
        """
        LDF_RELEVANT_VARS = {
            'CPPPATH', 'LIBPATH', 'LIBS', 'LIB_DEPS', 'LIB_IGNORE', 
            'LIB_EXTRA_DIRS', 'LIB_LDF_MODE', 'LIB_COMPAT_MODE',
            'LIBSOURCE_DIRS', 'PROJECT_LIBDEPS_DIR', 'PLATFORM', 
            'FRAMEWORK', 'BOARD', 'BUILD_FLAGS', 'CPPDEFINES'
        }
        
        extracted_vars = {}
        node_conversions = 0
        
        for var_name in LDF_RELEVANT_VARS:
            if var_name in self.env:
                var_value = self.env[var_name]
                
                # Zähle Node-Konversionen für Debugging
                original_str = str(var_value)
                serialized_value = self.convert_all_scons_objects(var_value)
                
                if 'SCons.Node' in original_str:
                    node_conversions += 1
                    print(f"🔄 Converted {var_name}: Node objects -> strings")
                
                extracted_vars[var_name] = serialized_value
        
        print(f"📊 Node conversions: {node_conversions} variables contained SCons.Node objects")
        return extracted_vars

    def extract_ldf_results(self):
        """
        Extrahiere LDF-Ergebnisse aus dem Dateisystem.
        """
        ldf_results = {}
        
        # Pfad zu den LDF-Ergebnissen
        libdeps_dir = os.path.join(self.project_dir, ".pio", "libdeps", self.env['PIOENV'])
        
        if os.path.exists(libdeps_dir):
            try:
                # Gefundene Libraries
                libraries = []
                for lib_dir in os.listdir(libdeps_dir):
                    lib_path = os.path.join(libdeps_dir, lib_dir)
                    if os.path.isdir(lib_path):
                        # Extrahiere Library-Info
                        library_json = os.path.join(lib_path, "library.json")
                        if os.path.exists(library_json):
                            try:
                                with open(library_json, 'r') as f:
                                    import json
                                    lib_info = json.loads(f.read())
                                    libraries.append({
                                        'name': lib_info.get('name', lib_dir),
                                        'version': lib_info.get('version', 'unknown'),
                                        'path': lib_path
                                    })
                            except:
                                libraries.append({'name': lib_dir, 'path': lib_path})
                        else:
                            libraries.append({'name': lib_dir, 'path': lib_path})
                
                ldf_results['libraries'] = libraries
                ldf_results['libdeps_dir'] = libdeps_dir
                
            except Exception as e:
                print(f"⚠ Error extracting LDF results: {e}")
                
        return ldf_results

    def _analyze_node_types(self, scons_vars):
        """
        Analysiere die verschiedenen SCons.Node Typen im Environment.
        """
        node_types = {}
        node_examples = {}
        
        for var_name, var_value in scons_vars.items():
            var_str = str(var_value)
            if 'SCons.Node' in var_str:
                # Extrahiere Node-Typ
                import re
                node_matches = re.findall(r'SCons\.Node\.([^>]+)', var_str)
                for node_type in node_matches:
                    if node_type not in node_types:
                        node_types[node_type] = 0
                        node_examples[node_type] = []
                    node_types[node_type] += 1
                    if len(node_examples[node_type]) < 3:  # Nur erste 3 Beispiele
                        node_examples[node_type].append({
                            'variable': var_name,
                            'example': var_str[:100] + '...' if len(var_str) > 100 else var_str
                        })
        
        return {
            'node_type_counts': node_types,
            'node_examples': node_examples
        }

    def create_analysis_dump(self):
        """
        Erstelle einen detaillierten Dump für die Analyse der LDF-Daten.
        """
        try:
            print("\n🔍 Creating detailed analysis dump...")
            
            # Hole alle Environment-Daten
            env_dump = self.env.Dump(format='pretty')
            scons_vars = eval(env_dump)
            
            # Konvertiere alle SCons-Objekte
            converted_vars = self.debug_dump_all_scons_objects()
            
            # Extrahiere LDF-relevante Daten
            build_vars = self.get_comprehensive_ldf_vars()
            ldf_results = self.extract_ldf_results()
            
            # Erstelle strukturierten Analyse-Dump
            analysis_data = {
                'analysis_info': {
                    'timestamp': datetime.datetime.now().isoformat(),
                    'pioenv': str(self.env['PIOENV']),
                    'project_dir': self.project_dir,
                    'purpose': 'LDF Cache Analysis - for script optimization'
                },
                'raw_scons_vars': {
                    'total_count': len(scons_vars),
                    'sample_vars': dict(list(scons_vars.items())[:10]),  # Erste 10 für Übersicht
                },
                'converted_scons_vars': converted_vars,
                'ldf_relevant_vars': build_vars,
                'ldf_filesystem_results': ldf_results,
                'critical_paths': {
                    'CPPPATH': self.env.get('CPPPATH', []),
                    'LIBPATH': self.env.get('LIBPATH', []),
                    'LIBS': self.env.get('LIBS', []),
                },
                'node_analysis': self._analyze_node_types(scons_vars)
            }
            
            # Speichere Analyse-Dump
            analysis_file = os.path.join(self.project_dir, ".pio", "ldf_cache", f"analysis_dump_{self.env['PIOENV']}.py")
            os.makedirs(os.path.dirname(analysis_file), exist_ok=True)
            
            with open(analysis_file, 'w', encoding='utf-8') as f:
                f.write("# LDF Cache Analysis Dump\n")
                f.write("# This file contains detailed analysis data for script optimization\n")
                f.write("# Generated for upload and analysis\n\n")
                f.write("analysis_data = ")
                f.write(repr(analysis_data))
            
            print(f"📁 Analysis dump saved to: {analysis_file}")
            print(f"📊 Analysis contains:")
            print(f"   - {len(converted_vars)} converted SCons variables")
            print(f"   - {len(build_vars)} LDF-relevant variables")
            print(f"   - {len(ldf_results.get('libraries', []))} detected libraries")
            print(f"   - Node type analysis")
            
            return analysis_file
            
        except Exception as e:
            print(f"❌ Error creating analysis dump: {e}")
            return None

    def apply_ldf_cache(self, cache_data):
        """
        Restore relevant build variables from cache.
        """
        try:
            build_vars = cache_data.get('build_vars', {})
            print("🔧 Restoring build variables from cache...")
            
            restored_count = 0
            for var_name, var_value in build_vars.items():
                try:
                    self.env[var_name] = var_value
                    restored_count += 1
                except Exception as e:
                    print(f"⚠ Error restoring {var_name}: {e}")
            
            print(f"📦 Restored {restored_count} build variables")
            return True
        except Exception as e:
            print(f"✗ Error restoring environment: {e}")
            return False

    def save_ldf_cache(self, target=None, source=None, env_arg=None, **kwargs):
        """
        Save LDF cache with comprehensive SCons object debugging.
        """
        try:
            hash_details = self.get_project_hash_with_details()
            
            # Debug: Alle SCons-Objekte konvertieren und ausgeben
            print("\n🔧 DEBUG MODE: Converting all SCons objects...")
            converted_debug_vars = self.debug_dump_all_scons_objects()
            
            # Extrahiere relevante Build-Variablen
            build_vars = self.get_comprehensive_ldf_vars()
            ldf_results = self.extract_ldf_results()
            
            # Erstelle zusätzlich einen Analyse-Dump
            analysis_file = self.create_analysis_dump()
            if analysis_file:
                print(f"\n📤 Upload this file for analysis: {analysis_file}")
            
            pio_version = getattr(self.env, "PioVersion", lambda: "unknown")()
            
            cache_data = {
                'build_vars': build_vars,
                'ldf_results': ldf_results,
                'debug_vars': converted_debug_vars,  # Vollständige Debug-Daten
                'project_hash': hash_details['final_hash'],
                'hash_details': hash_details['file_hashes'],
                'pioenv': str(self.env['PIOENV']),
                'timestamp': datetime.datetime.now().isoformat(),
                'pio_version': pio_version,
            }
            
            # Compute and add signature
            cache_data['signature'] = self.compute_signature(cache_data)
            
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                f.write("# LDF Cache - Comprehensive Build Data\n")
                f.write("# Generated automatically\n\n")
                f.write(repr(cache_data))
                
            print(f"💾 Saved comprehensive cache with {len(build_vars)} build vars and {len(ldf_results.get('libraries', []))} libraries")
            
            # Ausgabe der relevanten Build-Variablen
            print("\n=== Relevant Build Variables ===")
            for var_name, var_value in build_vars.items():
                print(f"{var_name}: {var_value}")
                
            print(f"\n=== LDF Libraries ({len(ldf_results.get('libraries', []))}) ===")
            for lib in ldf_results.get('libraries', []):
                print(f"📚 {lib.get('name', 'unknown')} v{lib.get('version', '?')} -> {lib.get('path', '')}")
                
        except Exception as e:
            print(f"✗ Error saving cache: {e}")

    # ------------------- Main Logic --------------------------------------------

    def setup_ldf_caching(self):
        """
        Orchestrate caching process with smart invalidation, signature, and version check.
        """
        print("\n=== LDF Cache Optimizer (Debug Mode) ===")
        cache_data = self.load_and_validate_cache()
        if cache_data:
            print("🚀 Valid cache found - disabling LDF")
            if self.modify_platformio_ini("off"):
                self.apply_ldf_cache(cache_data)
                self.env.AddPostAction("checkprogsize", lambda *args: self.restore_platformio_ini())
        else:
            print("🔄 No valid cache - running full LDF")
            self.env.AddPostAction("checkprogsize", self.save_ldf_cache)
        print("=" * 60)

# ------------------- Cache Management Commands --------------------------------

def clear_ldf_cache():
    """
    Delete LDF cache file.
    """
    project_dir = env.subst("$PROJECT_DIR")
    cache_file = os.path.join(project_dir, ".pio", "ldf_cache", f"ldf_cache_{env['PIOENV']}.py")
    if os.path.exists(cache_file):
        try:
            os.remove(cache_file)
            print("✓ LDF Cache deleted")
        except Exception as e:
            print(f"✗ Error deleting cache: {e}")
    else:
        print("ℹ No LDF Cache present")

def show_ldf_cache_info():
    """
    Display cache information.
    """
    project_dir = env.subst("$PROJECT_DIR")
    cache_file = os.path.join(project_dir, ".pio", "ldf_cache", f"ldf_cache_{env['PIOENV']}.py")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = eval(f.read().split('\n\n', 1)[1])
            print("\n=== LDF Cache Info ===")
            print(f"Environment:  {cache_data.get('pioenv', 'unknown')}")
            print(f"Project hash: {cache_data.get('project_hash', 'unknown')}")
            print(f"PlatformIO version: {cache_data.get('pio_version', 'unknown')}")
            print(f"Signature:    {cache_data.get('signature', 'none')}")
            print(f"Created:      {cache_data.get('timestamp', 'unknown')}")
            print(f"File size:    {os.path.getsize(cache_file)} bytes")
            print(f"Build vars:   {len(cache_data.get('build_vars', {}))}")
            print(f"Libraries:    {len(cache_data.get('ldf_results', {}).get('libraries', []))}")
            print("=" * 25)
        except Exception as e:
            print(f"Error reading cache: {e}")
    else:
        print("No LDF Cache present")

def create_standalone_analysis_dump():
    """
    Erstelle einen Analyse-Dump als eigenständiges Command.
    """
    project_dir = env.subst("$PROJECT_DIR")
    optimizer = LDFCacheOptimizer(env)
    analysis_file = optimizer.create_analysis_dump()
    if analysis_file:
        print(f"✅ Analysis dump created: {analysis_file}")
        print("📤 Upload this file for script optimization!")
    else:
        print("❌ Failed to create analysis dump")

# Register custom targets
env.AlwaysBuild(env.Alias("clear_ldf_cache", None, clear_ldf_cache))
env.AlwaysBuild(env.Alias("ldf_cache_info", None, show_ldf_cache_info))
env.AlwaysBuild(env.Alias("create_analysis_dump", None, create_standalone_analysis_dump))

# Initialize and run
ldf_optimizer = LDFCacheOptimizer(env)
ldf_optimizer.setup_ldf_caching()
