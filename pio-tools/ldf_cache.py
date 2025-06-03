# ldf_cache_optimizer.py
# PlatformIO Advanced Script für intelligentes LDF-Caching
# Autor: pioarduino Maintainer
# Optimiert Build-Performance durch selektives LDF-Caching
# Version: 2.0 - Korrigierte Hash-Invalidierung

import os
import json
import hashlib
import subprocess
Import("env")

class LDFCacheOptimizer:
    def __init__(self, environment):
        self.env = environment
        self.cache_file = os.path.join(self.env.subst("$BUILD_DIR"), "ldf_cache.json")
        self.project_dir = self.env.subst("$PROJECT_DIR")
        self.src_dir = self.env.subst("$PROJECT_SRC_DIR")
        
    def get_project_hash(self):
        """Erstelle Hash aus kritischen Projekt-Dateien für Cache-Invalidierung"""
        hash_data = []
        
        # platformio.ini Hash - KOMPLETT (für automatische Invalidierung bei Änderungen)
        ini_path = os.path.join(self.project_dir, "platformio.ini")
        if os.path.exists(ini_path):
            with open(ini_path, 'rb') as f:
                hash_data.append(f.read())
        
        # Source-Dateien Timestamps (für Performance nur mtime)
        for root, _, files in os.walk(self.src_dir):
            for file in files:
                if file.endswith(('.cpp', '.c', '.h', '.hpp', '.ino')):
                    file_path = os.path.join(root, file)
                    if os.path.exists(file_path):
                        stat = os.stat(file_path)
                        hash_data.append(f"{file_path}:{stat.st_mtime}".encode())
        
        # Library-Manifeste Hash
        for lib_dir in self.env.GetLibSourceDirs():
            if os.path.exists(lib_dir):
                for item in os.listdir(lib_dir):
                    lib_path = os.path.join(lib_dir, item)
                    if os.path.isdir(lib_path):
                        for manifest in ['library.json', 'library.properties', 'module.json']:
                            manifest_path = os.path.join(lib_path, manifest)
                            if os.path.exists(manifest_path):
                                with open(manifest_path, 'rb') as f:
                                    hash_data.append(f.read())
        
        return hashlib.md5(b''.join(hash_data)).hexdigest()
    
    def detect_source_only_changes(self):
        """Erkenne ob nur Source-Code geändert wurde (keine neuen Includes)"""
        try:
            # Git diff für geänderte Dateien
            result = subprocess.run(
                ['git', 'diff', '--name-only', 'HEAD~1'], 
                capture_output=True, text=True, cwd=self.project_dir
            )
            
            if result.returncode != 0:
                print("Git nicht verfügbar - Cache wird invalidiert")
                return False
                
            changed_files = result.stdout.strip().splitlines()
            if not changed_files:
                return True  # Keine Änderungen
            
            for file_path in changed_files:
                # Strukturelle Änderungen
                if file_path in ['platformio.ini', 'library.json', 'library.properties']:
                    print(f"Strukturelle Änderung erkannt: {file_path}")
                    return False
                
                # Header-Dateien geändert
                if file_path.endswith(('.h', '.hpp')):
                    print(f"Header-Datei geändert: {file_path}")
                    return False
                
                # Source-Dateien: Prüfe auf neue Includes
                if file_path.endswith(('.cpp', '.c', '.ino')):
                    if self.has_new_includes(file_path):
                        print(f"Neue Includes in {file_path} erkannt")
                        return False
            
            print("Nur Source-Code-Änderungen erkannt")
            return True
            
        except Exception as e:
            print(f"Fehler bei Change-Detection: {e} - Cache wird invalidiert")
            return False
    
    def has_new_includes(self, file_path):
        """Prüfe ob neue #include Statements hinzugefügt wurden"""
        try:
            result = subprocess.run(
                ['git', 'diff', 'HEAD~1', file_path], 
                capture_output=True, text=True, cwd=self.project_dir
            )
            
            if result.returncode != 0:
                return True  # Im Zweifel Cache invalidieren
            
            diff_lines = result.stdout.splitlines()
            for line in diff_lines:
                if line.startswith('+') and '#include' in line and not line.startswith('+++'):
                    return True
            
            return False
            
        except Exception:
            return True  # Im Zweifel Cache invalidieren
    
    def save_ldf_cache(self):
        """Speichere vollständige LDF-Ergebnisse nach erfolgreichem Build"""
        try:
            cache_data = {
                'project_hash': self.get_project_hash(),
                'pioenv': self.env['PIOENV'],
                'timestamp': subprocess.run(['date', '+%Y-%m-%d %H:%M:%S'], 
                                          capture_output=True, text=True).stdout.strip(),
                
                # LDF-Ergebnisse
                'ldf_results': {
                    'includes': [str(p) for p in self.env.get('CPPPATH', [])],
                    'defines': self.env.get('CPPDEFINES', []),
                    'libs': self.env.get('LIBS', []),
                    'lib_paths': [str(p) for p in self.env.get('LIBPATH', [])],
                    'src_filter': self.env.get('SRC_FILTER', ''),
                    'cc_flags': self.env.get('CCFLAGS', []),
                    'cxx_flags': self.env.get('CXXFLAGS', []),
                    'link_flags': self.env.get('LINKFLAGS', [])
                },
                
                # Library-Dependencies für Debugging
                'library_dependencies': []
            }
            
            # Sammle Library-Informationen
            for lb in self.env.GetLibBuilders():
                if lb.is_built or lb.is_dependent:
                    lib_dep = {
                        'name': lb.name,
                        'path': str(lb.path),
                        'include_dirs': [str(d) for d in lb.get_include_dirs()],
                        'is_dependent': lb.is_dependent,
                        'is_built': lb.is_built,
                        'dependencies': [dep.name for dep in lb.depbuilders],
                        'ldf_mode': getattr(lb, 'lib_ldf_mode', 'unknown')
                    }
                    cache_data['library_dependencies'].append(lib_dep)
            
            # Cache-Verzeichnis erstellen falls nötig
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            
            # Cache speichern
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2, default=str)
            
            print(f"✓ LDF Cache gespeichert: {len(cache_data['library_dependencies'])} Libraries")
            print(f"  Cache-Datei: {self.cache_file}")
            
        except Exception as e:
            print(f"✗ Fehler beim Speichern des LDF Cache: {e}")
    
    def load_ldf_cache(self):
        """Lade und validiere LDF-Cache"""
        if not os.path.exists(self.cache_file):
            return None
        
        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Cache-Validierung
            current_hash = self.get_project_hash()
            cached_hash = cache_data.get('project_hash')
            cached_env = cache_data.get('pioenv')
            
            if cached_hash != current_hash:
                print("LDF Cache ungültig - Projekt-Hash unterschiedlich")
                return None
            
            if cached_env != self.env['PIOENV']:
                print(f"LDF Cache ungültig - Environment geändert ({cached_env} -> {self.env['PIOENV']})")
                return None
            
            print(f"✓ LDF Cache geladen: {cache_data.get('timestamp', 'unbekannt')}")
            return cache_data
            
        except Exception as e:
            print(f"✗ Fehler beim Laden des LDF Cache: {e}")
            return None
    
    def apply_ldf_cache(self, cache_data):
        """Wende LDF-Cache auf Environment an"""
        try:
            ldf_results = cache_data['ldf_results']
            
            # Include-Pfade
            if ldf_results.get('includes'):
                self.env.PrependUnique(CPPPATH=ldf_results['includes'])
            
            # Library-Pfade und -Namen
            if ldf_results.get('lib_paths'):
                self.env.PrependUnique(LIBPATH=ldf_results['lib_paths'])
            
            if ldf_results.get('libs'):
                self.env.PrependUnique(LIBS=ldf_results['libs'])
            
            # Preprocessor-Defines
            if ldf_results.get('defines'):
                self.env.Append(CPPDEFINES=ldf_results['defines'])
            
            # Source-Filter
            if ldf_results.get('src_filter'):
                self.env['SRC_FILTER'] = ldf_results['src_filter']
            
            # Compiler-Flags (optional)
            if ldf_results.get('cc_flags'):
                self.env.Append(CCFLAGS=ldf_results['cc_flags'])
            
            if ldf_results.get('cxx_flags'):
                self.env.Append(CXXFLAGS=ldf_results['cxx_flags'])
            
            lib_count = len(cache_data.get('library_dependencies', []))
            print(f"✓ LDF-Cache angewendet: {lib_count} Libraries")
            print("  LDF-Modus: OFF (Cache verwendet)")
            
        except Exception as e:
            print(f"✗ Fehler beim Anwenden des LDF Cache: {e}")
            raise
    
    def debug_cache_decision(self, cache_data, source_only_changes):
        """Debug-Ausgabe für Cache-Entscheidungen"""
        current_hash = self.get_project_hash()
        cached_hash = cache_data.get('project_hash') if cache_data else None
        
        print(f"Cache-Debug:")
        print(f"  Aktueller Hash: {current_hash[:8]}...")
        print(f"  Cache Hash:     {cached_hash[:8] if cached_hash else 'None'}...")
        print(f"  Hash-Match:     {current_hash == cached_hash if cached_hash else False}")
        print(f"  Source-Only:    {source_only_changes}")
        print(f"  Cache-Datei:    {'Existiert' if cache_data else 'Nicht vorhanden'}")
    
    def setup_ldf_caching(self):
        """Hauptlogik für intelligentes LDF-Caching ohne platformio.ini Modifikation"""
        print("\n=== LDF Cache Optimizer v2.0 ===")
        
        # Originaler LDF-Modus aus platformio.ini
        original_ldf_mode = self.env.GetProjectOption("lib_ldf_mode", "chain")
        print(f"Original LDF-Modus: {original_ldf_mode}")
        
        # Cache-Validierung
        cache_data = self.load_ldf_cache()
        source_only_changes = self.detect_source_only_changes()
        
        # Debug-Ausgabe
        if self.env.get("PIOVERBOSE", 0):
            self.debug_cache_decision(cache_data, source_only_changes)
        
        if cache_data and source_only_changes:
            # Cache verwenden - NUR Runtime-Environment ändern (KEINE Datei-Modifikation)
            print("🚀 Verwende LDF-Cache (nur Source-Code geändert)")
            
            # KRITISCH: Nur SCons Environment ändern, platformio.ini bleibt unberührt
            self.env.Replace(lib_ldf_mode="off")
            
            # Cache anwenden
            self.apply_ldf_cache(cache_data)
            
            print(f"  Runtime LDF-Modus: OFF (Override von {original_ldf_mode})")
            
        else:
            # Normaler LDF-Lauf
            if not cache_data:
                print("📝 Erster Build - erstelle LDF-Cache")
            elif not source_only_changes:
                print("🔄 Include-Struktur geändert - LDF-Neuberechnung")
            else:
                print("⚠ Cache ungültig - LDF-Neuberechnung")
            
            print(f"  LDF-Modus: {original_ldf_mode} (aus platformio.ini)")
            
            # Cache nach erfolgreichem Build speichern
            self.env.AddPostAction("checkprogsize", 
                                  lambda target, source, env: self.save_ldf_cache())
        
        print("=" * 35)

# Cache-Management-Befehle
def clear_ldf_cache():
    """Lösche LDF-Cache manuell"""
    cache_file = os.path.join(env.subst("$BUILD_DIR"), "ldf_cache.json")
    if os.path.exists(cache_file):
        os.remove(cache_file)
        print("✓ LDF Cache gelöscht")
    else:
        print("ℹ Kein LDF Cache vorhanden")

def show_ldf_cache_info():
    """Zeige detaillierte Cache-Informationen"""
    cache_file = os.path.join(env.subst("$BUILD_DIR"), "ldf_cache.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            
            print(f"\n=== LDF Cache Info ===")
            print(f"Erstellt:     {cache_data.get('timestamp', 'unbekannt')}")
            print(f"Environment:  {cache_data.get('pioenv', 'unbekannt')}")
            print(f"Project Hash: {cache_data.get('project_hash', 'unbekannt')[:16]}...")
            print(f"Libraries:    {len(cache_data.get('library_dependencies', []))}")
            print(f"Includes:     {len(cache_data.get('ldf_results', {}).get('includes', []))}")
            print(f"Cache-Datei:  {cache_file}")
            
            # Library-Details
            libs = cache_data.get('library_dependencies', [])
            if libs:
                print(f"\nGecachte Libraries:")
                for lib in libs[:10]:  # Erste 10 anzeigen
                    print(f"  - {lib.get('name', 'unknown')} ({'dependent' if lib.get('is_dependent') else 'independent'})")
                if len(libs) > 10:
                    print(f"  ... und {len(libs) - 10} weitere")
            
            print("=" * 25)
            
        except Exception as e:
            print(f"Fehler beim Lesen der Cache-Info: {e}")
    else:
        print("Kein LDF Cache vorhanden")

def force_ldf_rebuild():
    """Erzwinge LDF-Neuberechnung durch Cache-Löschung"""
    clear_ldf_cache()
    print("LDF wird beim nächsten Build neu berechnet")

# Custom Targets für Cache-Management
env.AlwaysBuild(env.Alias("clear_ldf_cache", None, clear_ldf_cache))
env.AlwaysBuild(env.Alias("ldf_cache_info", None, show_ldf_cache_info))
env.AlwaysBuild(env.Alias("force_ldf_rebuild", None, force_ldf_rebuild))

# LDF Cache Optimizer initialisieren und ausführen
ldf_optimizer = LDFCacheOptimizer(env)
ldf_optimizer.setup_ldf_caching()
