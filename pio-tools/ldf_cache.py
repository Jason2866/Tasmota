# ldf_cache_optimizer.py
# PlatformIO Advanced Script für intelligentes LDF-Caching
# Autor: pioarduino Maintainer
# Optimiert Build-Performance durch selektives LDF-Caching
# Version: 2.1 - Include-relevante Hash-Bildung und vollständige SCons-Variablen

Import("env")
import os
import json
import hashlib
import datetime

class LDFCacheOptimizer:
    def __init__(self, environment):
        self.env = environment
        self.cache_file = os.path.join(self.env.subst("$BUILD_DIR"), "ldf_cache.json")
        self.project_dir = self.env.subst("$PROJECT_DIR")
        self.src_dir = self.env.subst("$PROJECT_SRC_DIR")
        
        # Include-relevante Dateitypen
        self.include_relevant_extensions = {
            # Standard C/C++
            '.h', '.hpp', '.hxx', '.h++', '.hh',
            '.c', '.cpp', '.cxx', '.c++', '.cc', '.ino',
            # Template-Dateien
            '.tpp', '.tcc', '.inc',
            # Config/Manifest-Dateien
            '.json', '.properties', '.txt', '.ini'
        }
    
    def _get_file_hash(self, file_path):
        """Hash einer einzelnen Datei"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()[:12]
        except:
            return "unreadable"
    
    def get_include_relevant_hash(self, file_path):
        """Hash nur von Include-relevanten Zeilen"""
        include_lines = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    stripped = line.strip()
                    
                    # Skip Kommentare
                    if stripped.startswith('//'):
                        continue
                    
                    # Include-relevante Zeilen
                    if (stripped.startswith('#include') or 
                        stripped.startswith('#if') or 
                        stripped.startswith('#ifdef') or
                        stripped.startswith('#ifndef') or
                        stripped.startswith('#endif') or  # Auch wichtig!
                        stripped.startswith('#else') or   # Auch wichtig!
                        stripped.startswith('#elif') or   # Auch wichtig!
                        (stripped.startswith('#define') and 
                         any(keyword in stripped.upper() for keyword in ['INCLUDE', 'PATH', 'CONFIG']))):
                        include_lines.append(stripped)
            
            return hashlib.md5('\n'.join(include_lines).encode()).hexdigest()[:8]
            
        except Exception:
            # Fallback: Datei-Hash
            return self._get_file_hash(file_path)
    
    def get_project_hash(self):
        """Include-relevante Hash-Bildung für Cache-Validierung"""
        hash_data = []
        
        # platformio.ini
        ini_file = os.path.join(self.project_dir, "platformio.ini")
        if os.path.exists(ini_file):
            hash_data.append(self._get_file_hash(ini_file))
        
        # Source-Verzeichnis scannen
        if os.path.exists(self.src_dir):
            for root, _, files in os.walk(self.src_dir):
                for file in sorted(files):
                    file_path = os.path.join(root, file)
                    file_ext = os.path.splitext(file)[1].lower()
                    
                    if file_ext in {'.h', '.hpp', '.hxx', '.h++', '.hh', '.inc', '.tpp', '.tcc'}:
                        # Header-Dateien: Vollständiger Hash
                        hash_data.append(self._get_file_hash(file_path))
                    elif file_ext in {'.c', '.cpp', '.cxx', '.c++', '.cc', '.ino'}:
                        # Source-Dateien: Include-relevanter Hash
                        hash_data.append(self.get_include_relevant_hash(file_path))
        
        # Include-Verzeichnisse scannen
        for inc_path in self.env.get('CPPPATH', []):
            inc_dir = str(inc_path)
            if os.path.exists(inc_dir) and inc_dir != self.src_dir:
                for root, _, files in os.walk(inc_dir):
                    for file in sorted(files):
                        if file.endswith(('.h', '.hpp', '.hxx', '.inc', '.tpp')):
                            file_path = os.path.join(root, file)
                            hash_data.append(self._get_file_hash(file_path))
        
        # Library-Verzeichnis
        lib_dir = os.path.join(self.project_dir, "lib")
        if os.path.exists(lib_dir):
            for root, _, files in os.walk(lib_dir):
                for file in sorted(files):
                    if file.endswith(('.h', '.hpp', '.json', '.properties')):
                        file_path = os.path.join(root, file)
                        hash_data.append(self._get_file_hash(file_path))
        
        return hashlib.sha256(''.join(hash_data).encode()).hexdigest()
    
    def load_and_validate_cache(self):
        """Lade Cache mit Hash-Validierung"""
        if not os.path.exists(self.cache_file):
            return None
        
        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Environment-Check
            if cache_data.get('pioenv') != self.env['PIOENV']:
                print("🔄 Environment geändert")
                return None
            
            # Hash-Vergleich
            current_hash = self.get_project_hash()
            cached_hash = cache_data.get('project_hash')
            
            if current_hash != cached_hash:
                print("🔄 Include-relevante Änderungen erkannt - Cache ungültig")
                return None
            
            print("✅ Keine Include-relevanten Änderungen - Cache verwendbar")
            return cache_data
            
        except Exception as e:
            print(f"⚠ Cache-Validierung fehlgeschlagen: {e}")
            return None
    
    def apply_ldf_cache(self, cache_data):
        """Wende LDF-Cache mit korrekten SCons-Methoden an"""
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
            
            # Source-Filter - mit Replace statt direkter Zuweisung
            src_filter = ldf_results.get('src_filter') or ldf_results.get('SRC_FILTER')
            if src_filter:
                self.env.Replace(SRC_FILTER=src_filter)
            
            # Compiler-Flags
            cc_flags = ldf_results.get('cc_flags') or ldf_results.get('CCFLAGS', [])
            if cc_flags:
                self.env.Append(CCFLAGS=cc_flags)
            
            cxx_flags = ldf_results.get('cxx_flags') or ldf_results.get('CXXFLAGS', [])
            if cxx_flags:
                self.env.Append(CXXFLAGS=cxx_flags)
            
            # Linker-Flags
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
        """Speichere vollständige LDF-Ergebnisse"""
        if self.env.get("LIB_LDF_MODE") == "off":
            return  # Cache wurde verwendet
        
        try:
            cache_data = {
                # Include-relevanter Hash
                'project_hash': self.get_project_hash(),
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
                }
            }
            
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2, default=str)
            
            lib_count = len(cache_data['ldf_results'].get('LIBS', []))
            print(f"💾 LDF-Cache gespeichert: {lib_count} Libraries")
            
        except Exception as e:
            print(f"✗ Fehler beim Speichern des LDF Cache: {e}")
    
    def setup_ldf_caching(self):
        """Hauptlogik für intelligentes LDF-Caching"""
        print("\n=== LDF Cache Optimizer v2.1 ===")
        
        cache_data = self.load_and_validate_cache()
        
        if cache_data:
            print("🚀 Verwende LDF-Cache (keine Include-relevanten Änderungen)")
            self.apply_ldf_cache(cache_data)
        else:
            print("🔄 LDF-Neuberechnung erforderlich")
            self.env.AddPostAction("checkprogsize", self.save_ldf_cache)
        
        print("================================")

# Cache-Management-Befehle
def clear_ldf_cache():
    """Lösche LDF-Cache"""
    cache_file = os.path.join(env.subst("$BUILD_DIR"), "ldf_cache.json")
    if os.path.exists(cache_file):
        os.remove(cache_file)
        print("✓ LDF Cache gelöscht")
    else:
        print("ℹ Kein LDF Cache vorhanden")

def show_ldf_cache_info():
    """Zeige Cache-Info"""
    cache_file = os.path.join(env.subst("$BUILD_DIR"), "ldf_cache.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            
            print(f"\n=== LDF Cache Info ===")
            print(f"Erstellt:     {cache_data.get('timestamp', 'unbekannt')}")
            print(f"Environment:  {cache_data.get('pioenv', 'unbekannt')}")
            print(f"Libraries:    {len(cache_data.get('ldf_results', {}).get('LIBS', []))}")
            print(f"Include-Pfade: {len(cache_data.get('ldf_results', {}).get('CPPPATH', []))}")
            print(f"Hash:         {cache_data.get('project_hash', 'unbekannt')[:16]}...")
            print("=" * 25)
            
        except Exception as e:
            print(f"Fehler beim Lesen der Cache-Info: {e}")
    else:
        print("Kein LDF Cache vorhanden")

def force_ldf_rebuild():
    """Erzwinge LDF-Neuberechnung"""
    clear_ldf_cache()
    print("LDF wird beim nächsten Build neu berechnet")

# Custom Targets
env.AlwaysBuild(env.Alias("clear_ldf_cache", None, clear_ldf_cache))
env.AlwaysBuild(env.Alias("ldf_cache_info", None, show_ldf_cache_info))
env.AlwaysBuild(env.Alias("force_ldf_rebuild", None, force_ldf_rebuild))

# LDF Cache Optimizer initialisieren
ldf_optimizer = LDFCacheOptimizer(env)
ldf_optimizer.setup_ldf_caching()
