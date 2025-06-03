# ldf_cache_optimizer.py
# PlatformIO Advanced Script für intelligentes LDF-Caching

Import("env")
import os
import json
import hashlib
import re
import datetime

class LDFCacheOptimizer:
    def __init__(self, environment):
        self.env = environment
        self.cache_file = os.path.join(self.env.subst("$BUILD_DIR"), "ldf_cache.json")
        self.project_dir = self.env.subst("$PROJECT_DIR")
        self.src_dir = self.env.subst("$PROJECT_SRC_DIR")
        
        # Erweiterte Include-relevante Dateitypen (nur sichere Ergänzungen)
        self.include_relevant_extensions = {
            # Standard C/C++
            '.h', '.hpp', '.hxx', '.h++', '.hh',
            '.c', '.cpp', '.cxx', '.c++', '.cc', '.ino',
            # Template-Dateien (echte Verbesserung)
            '.tpp', '.tcc', '.inc',
            # Config/Manifest-Dateien
            '.json', '.properties', '.txt', '.ini'
        }
        
        # Nur Standard Include-Pattern (keine experimentellen)
        self.include_patterns = [
            r'#include\s*[<"](.*?)[>"]'  # Standard C/C++
        ]
    
    def extract_include_dependencies(self, file_path):
        """Extrahiere Include-relevante Informationen aus einer Datei"""
        include_data = {
            'direct_includes': [],
            'conditional_includes': [],
            'defines_affecting_includes': []
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            in_multiline_comment = False
            in_conditional_block = False
            current_condition = ""
            
            for line_num, line in enumerate(lines):
                original_line = line
                line = line.strip()
                
                # Kommentar-Handling
                if '/*' in line and '*/' not in line:
                    in_multiline_comment = True
                    continue
                elif '*/' in line:
                    in_multiline_comment = False
                    continue
                elif in_multiline_comment or line.startswith('//'):
                    continue
                
                # Include-Statements
                for pattern in self.include_patterns:
                    matches = re.findall(pattern, line)
                    for match in matches:
                        if in_conditional_block:
                            include_data['conditional_includes'].append({
                                'condition': current_condition,
                                'include': match
                            })
                        else:
                            include_data['direct_includes'].append(match)
                
                # Conditional Compilation
                if line.startswith(('#ifdef', '#ifndef', '#if')):
                    in_conditional_block = True
                    current_condition = line
                elif line.startswith('#endif'):
                    in_conditional_block = False
                    current_condition = ""
                elif line.startswith(('#else', '#elif')):
                    current_condition = line
                
                # Include-relevante Defines
                if line.startswith('#define') and any(keyword in line.upper() 
                    for keyword in ['INCLUDE', 'PATH', 'DIR', 'CONFIG']):
                    include_data['defines_affecting_includes'].append(line)
        
        except Exception as e:
            # Fallback: Datei-Hash
            return {'file_hash': self._get_file_hash(file_path)}
        
        return include_data
    
    def get_project_include_fingerprint(self):
        """Erstelle detaillierten Include-Fingerprint"""
        fingerprint = {
            'config_files': {},
            'header_files': {},
            'source_files': {},
            'library_manifests': {}
        }
        
        # Projekt-Verzeichnisse scannen
        scan_dirs = [
            (self.src_dir, 'source'),
            (os.path.join(self.project_dir, "include"), 'header'),
            (os.path.join(self.project_dir, "lib"), 'library'),
            (self.project_dir, 'config')
        ]
        
        # Zusätzliche Include-Pfade
        for inc_path in self.env.get('CPPPATH', []):
            scan_dirs.append((str(inc_path), 'header'))
        
        for scan_dir, category in scan_dirs:
            if os.path.exists(scan_dir):
                self._scan_directory_for_includes(scan_dir, fingerprint, category)
        
        return fingerprint
    
    def _scan_directory_for_includes(self, directory, fingerprint, category):
        """Scanne Verzeichnis nach Include-relevanten Dateien"""
        for root, dirs, files in os.walk(directory):
            # Ignoriere Build-Verzeichnisse
            dirs[:] = [d for d in dirs if not d.startswith(('.pio', 'build', '.git'))]
            
            for file in sorted(files):
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, self.project_dir)
                file_ext = os.path.splitext(file)[1].lower()
                
                if file_ext not in self.include_relevant_extensions:
                    continue
                
                # Kategorisierung
                if category == 'config' and file in ['platformio.ini', 'library.json', 'library.properties']:
                    fingerprint['config_files'][rel_path] = self._get_file_hash(file_path)
                elif file_ext in {'.h', '.hpp', '.hxx', '.h++', '.hh', '.inc', '.tpp', '.tcc'}:
                    fingerprint['header_files'][rel_path] = self.extract_include_dependencies(file_path)
                elif file_ext in {'.c', '.cpp', '.cxx', '.c++', '.cc', '.ino'}:
                    include_data = self.extract_include_dependencies(file_path)
                    # Nur Include-relevante Teile für Source-Dateien
                    filtered_data = {
                        'direct_includes': include_data.get('direct_includes', []),
                        'conditional_includes': include_data.get('conditional_includes', [])
                    }
                    if filtered_data['direct_includes'] or filtered_data['conditional_includes']:
                        fingerprint['source_files'][rel_path] = filtered_data
                elif file_ext in {'.json', '.properties'}:
                    fingerprint['library_manifests'][rel_path] = self._get_file_hash(file_path)
    
    def _get_file_hash(self, file_path):
        """Hash einer einzelnen Datei"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()[:12]
        except:
            return "unreadable"
    
    def create_include_hash(self):
        """Erstelle Hash aus Include-Fingerprint"""
        fingerprint = self.get_project_include_fingerprint()
        fingerprint_json = json.dumps(fingerprint, sort_keys=True, indent=None)
        return hashlib.sha256(fingerprint_json.encode()).hexdigest()
    
    def analyze_include_changes(self, old_fingerprint, new_fingerprint):
        """Analysiere Include-Änderungen (Debugging-Hilfe)"""
        changes = []
        
        # Config-Änderungen
        if old_fingerprint.get('config_files') != new_fingerprint.get('config_files'):
            changes.append("Config-Dateien geändert")
        
        # Header-Änderungen
        old_headers = old_fingerprint.get('header_files', {})
        new_headers = new_fingerprint.get('header_files', {})
        for header_path in set(old_headers.keys()) | set(new_headers.keys()):
            if header_path not in old_headers:
                changes.append(f"Neuer Header: {header_path}")
            elif header_path not in new_headers:
                changes.append(f"Header entfernt: {header_path}")
            elif old_headers[header_path] != new_headers[header_path]:
                changes.append(f"Header geändert: {header_path}")
        
        # Source-Include-Änderungen
        old_sources = old_fingerprint.get('source_files', {})
        new_sources = new_fingerprint.get('source_files', {})
        for src_path in set(old_sources.keys()) | set(new_sources.keys()):
            if src_path not in old_sources or src_path not in new_sources:
                continue
            
            old_includes = set(old_sources[src_path].get('direct_includes', []))
            new_includes = set(new_sources[src_path].get('direct_includes', []))
            if old_includes != new_includes:
                changes.append(f"Includes geändert in: {src_path}")
        
        # Library-Änderungen
        if old_fingerprint.get('library_manifests') != new_fingerprint.get('library_manifests'):
            changes.append("Library-Manifeste geändert")
        
        return changes
    
    def load_and_validate_cache(self):
        """Lade Cache mit verbesserter Validierung"""
        if not os.path.exists(self.cache_file):
            return None
        
        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Environment-Check
            if cache_data.get('pioenv') != self.env['PIOENV']:
                print("🔄 Environment geändert")
                return None
            
            # Include-Fingerprint-Vergleich
            current_fingerprint = self.get_project_include_fingerprint()
            cached_fingerprint = cache_data.get('include_fingerprint', {})
            
            if current_fingerprint != cached_fingerprint:
                changes = self.analyze_include_changes(cached_fingerprint, current_fingerprint)
                print("🔍 Include-Änderungen erkannt:")
                for detail in changes[:3]:  # Erste 3 Änderungen
                    print(f"  • {detail}")
                if len(changes) > 3:
                    print(f"  • ... und {len(changes) - 3} weitere")
                return None
            
            print("✅ Keine Include-relevanten Änderungen - Cache verwendbar")
            return cache_data
            
        except Exception as e:
            print(f"⚠ Cache-Validierung fehlgeschlagen: {e}")
            return None
    
    def apply_ldf_cache(self, cache_data):
        """Wende LDF-Cache mit ALLEN SCons-Variablen an"""
        try:
            # LDF abschalten
            self.env.Replace(LIB_LDF_MODE="off")
            
            ldf_results = cache_data['ldf_results']
            
            # Include-Pfade (beide Varianten für Kompatibilität)
            includes = ldf_results.get('includes') or ldf_results.get('CPPPATH', [])
            if includes:
                self.env.PrependUnique(CPPPATH=includes)
            
            # Library-Pfade und -Namen
            lib_paths = ldf_results.get('lib_paths') or ldf_results.get('LIBPATH', [])
            if lib_paths:
                self.env.PrependUnique(LIBPATH=lib_paths)
            
            libs = ldf_results.get('libs') or ldf_results.get('LIBS', [])
            if libs:
                self.env.PrependUnique(LIBS=libs)
            
            # Preprocessor-Defines
            defines = ldf_results.get('defines') or ldf_results.get('CPPDEFINES', [])
            if defines:
                self.env.Append(CPPDEFINES=defines)
            
            # Source-Filter - KRITISCH
            src_filter = ldf_results.get('src_filter') or ldf_results.get('SRC_FILTER')
            if src_filter:
                self.env['SRC_FILTER'] = src_filter
            
            # Compiler-Flags - KRITISCH
            cc_flags = ldf_results.get('cc_flags') or ldf_results.get('CCFLAGS', [])
            if cc_flags:
                self.env.Append(CCFLAGS=cc_flags)
            
            cxx_flags = ldf_results.get('cxx_flags') or ldf_results.get('CXXFLAGS', [])
            if cxx_flags:
                self.env.Append(CXXFLAGS=cxx_flags)
            
            # Linker-Flags - KRITISCH
            link_flags = ldf_results.get('link_flags') or ldf_results.get('LINKFLAGS', [])
            if link_flags:
                self.env.Append(LINKFLAGS=link_flags)
            
            lib_count = len(libs)
            include_count = len(includes)
            print(f"📦 Vollständiger LDF-Cache angewendet:")
            print(f"   {lib_count} Libraries, {include_count} Include-Pfade")
            print("   Alle Compiler-Flags und Build-Einstellungen wiederhergestellt")
            
        except Exception as e:
            print(f"✗ Fehler beim Anwenden des LDF Cache: {e}")
            raise
    
    def save_ldf_cache(self, target, source, env_arg):
        """Speichere vollständige LDF-Ergebnisse mit verbesserter Struktur"""
        if self.env.get("LIB_LDF_MODE") == "off":
            return  # Cache wurde verwendet
        
        try:
            fingerprint = self.get_project_include_fingerprint()
            
            cache_data = {
                # Verbesserte Cache-Struktur
                'include_hash': self.create_include_hash(),
                'include_fingerprint': fingerprint,
                'pioenv': self.env['PIOENV'],
                'timestamp': datetime.datetime.now().isoformat(),
                
                # ALLE SCons-Variablen (vollständig wie Original)
                'ldf_results': {
                    # Include-Pfade
                    'includes': [str(p) for p in self.env.get('CPPPATH', [])],
                    'CPPPATH': [str(p) for p in self.env.get('CPPPATH', [])],
                    
                    # Library-Pfade und -Namen
                    'lib_paths': [str(p) for p in self.env.get('LIBPATH', [])],
                    'LIBPATH': [str(p) for p in self.env.get('LIBPATH', [])],
                    'libs': self.env.get('LIBS', []),
                    'LIBS': self.env.get('LIBS', []),
                    
                    # Preprocessor-Defines
                    'defines': self.env.get('CPPDEFINES', []),
                    'CPPDEFINES': self.env.get('CPPDEFINES', []),
                    
                    # Source-Filter
                    'src_filter': self.env.get('SRC_FILTER', ''),
                    'SRC_FILTER': self.env.get('SRC_FILTER', ''),
                    
                    # Compiler-Flags
                    'cc_flags': self.env.get('CCFLAGS', []),
                    'CCFLAGS': self.env.get('CCFLAGS', []),
                    'cxx_flags': self.env.get('CXXFLAGS', []),
                    'CXXFLAGS': self.env.get('CXXFLAGS', []),
                    
                    # Linker-Flags
                    'link_flags': self.env.get('LINKFLAGS', []),
                    'LINKFLAGS': self.env.get('LINKFLAGS', [])
                },
                
                # Statistiken für bessere Transparenz
                'statistics': {
                    'header_files': len(fingerprint.get('header_files', {})),
                    'source_files': len(fingerprint.get('source_files', {})),
                    'config_files': len(fingerprint.get('config_files', {})),
                    'library_manifests': len(fingerprint.get('library_manifests', {}))
                }
            }
            
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2, default=str)
            
            stats = cache_data['statistics']
            lib_count = len(cache_data['ldf_results'].get('LIBS', []))
            print(f"💾 Verbesserter LDF-Cache gespeichert:")
            print(f"   {lib_count} Libraries, {stats['header_files']} Headers, {stats['source_files']} Sources")
            
        except Exception as e:
            print(f"✗ Fehler beim Speichern des LDF Cache: {e}")
    
    def setup_ldf_caching(self):
        """Hauptlogik für intelligentes LDF-Caching"""
        print("\n=== LDF Cache Optimizer v2.1 ===")
        
        cache_data = self.load_and_validate_cache()
        
        if cache_data:
            print("🚀 Verwende LDF-Cache (keine Include-Änderungen)")
            self.apply_ldf_cache(cache_data)
        else:
            print("🔄 LDF-Neuberechnung erforderlich")
            self.env.AddPostAction("checkprogsize", self.save_ldf_cache)
        
        print("================================")

# Cache-Management-Befehle (unverändert)
def clear_ldf_cache():
    cache_file = os.path.join(env.subst("$BUILD_DIR"), "ldf_cache.json")
    if os.path.exists(cache_file):
        os.remove(cache_file)
        print("✓ LDF Cache gelöscht")
    else:
        print("ℹ Kein LDF Cache vorhanden")

def show_ldf_cache_info():
    cache_file = os.path.join(env.subst("$BUILD_DIR"), "ldf_cache.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            
            stats = cache_data.get('statistics', {})
            print(f"\n=== LDF Cache Info ===")
            print(f"Erstellt:     {cache_data.get('timestamp', 'unbekannt')}")
            print(f"Environment:  {cache_data.get('pioenv', 'unbekannt')}")
            print(f"Header-Dateien: {stats.get('header_files', 0)}")
            print(f"Source-Dateien: {stats.get('source_files', 0)}")
            print(f"Libraries:    {len(cache_data.get('ldf_results', {}).get('LIBS', []))}")
            print(f"Include-Hash: {cache_data.get('include_hash', 'unbekannt')[:16]}...")
            print("=" * 25)
            
        except Exception as e:
            print(f"Fehler beim Lesen der Cache-Info: {e}")
    else:
        print("Kein LDF Cache vorhanden")

# Custom Targets
env.AlwaysBuild(env.Alias("clear_ldf_cache", None, clear_ldf_cache))
env.AlwaysBuild(env.Alias("ldf_cache_info", None, show_ldf_cache_info))

# LDF Cache Optimizer initialisieren
ldf_optimizer = LDFCacheOptimizer(env)
ldf_optimizer.setup_ldf_caching()
