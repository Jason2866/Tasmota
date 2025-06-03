# ldf_cache.py - Erweiterte Include-Erkennung
Import("env")
import os
import json
import hashlib
import re
import datetime

class PreciseLDFCache:
    def __init__(self):
        self.cache_file = os.path.join(env.subst("$BUILD_DIR"), "ldf_cache.json")
        self.project_dir = env.subst("$PROJECT_DIR")
        
    def extract_include_dependencies(self, file_path):
        """Extrahiere nur Include-relevante Informationen aus einer Datei"""
        include_data = {
            'includes': [],
            'conditional_includes': [],
            'defines_affecting_includes': []
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            in_multiline_comment = False
            
            for line_num, line in enumerate(lines, 1):
                original_line = line
                line = line.strip()
                
                # Multiline-Kommentare handhaben
                if '/*' in line and '*/' not in line:
                    in_multiline_comment = True
                    continue
                elif '*/' in line:
                    in_multiline_comment = False
                    continue
                elif in_multiline_comment:
                    continue
                
                # Einzeilige Kommentare ignorieren
                if line.startswith('//'):
                    continue
                
                # Include-Statements
                if line.startswith('#include'):
                    # Normalisiere Include-Statement
                    match = re.match(r'#include\s*[<"](.*?)[>"]', line)
                    if match:
                        include_data['includes'].append(match.group(1))
                
                # Conditional Includes (in #ifdef, #if, etc.)
                elif line.startswith(('#ifdef', '#ifndef', '#if')):
                    # Schaue in den nächsten Zeilen nach Includes
                    for next_line_idx in range(line_num, min(line_num + 10, len(lines))):
                        next_line = lines[next_line_idx].strip()
                        if next_line.startswith('#include'):
                            match = re.match(r'#include\s*[<"](.*?)[>"]', next_line)
                            if match:
                                include_data['conditional_includes'].append({
                                    'condition': line,
                                    'include': match.group(1)
                                })
                        elif next_line.startswith(('#endif', '#else', '#elif')):
                            break
                
                # Defines die Include-Pfade beeinflussen könnten
                elif line.startswith('#define') and any(keyword in line.upper() for keyword in 
                    ['PATH', 'DIR', 'INCLUDE', 'LIB', 'CONFIG']):
                    include_data['defines_affecting_includes'].append(line)
        
        except Exception as e:
            # Bei Fehlern: Fallback auf Datei-Hash
            return {'file_hash': self._get_file_hash(file_path)}
        
        return include_data
    
    def get_include_structure_hash(self):
        """Erstelle Hash nur aus Include-relevanten Änderungen"""
        include_structure = {}
        
        # Source-Verzeichnis scannen
        src_dir = env.subst("$PROJECT_SRC_DIR")
        if os.path.exists(src_dir):
            include_structure.update(self._scan_directory_for_includes(src_dir))
        
        # Include-Verzeichnisse scannen
        for inc_path in env.get('CPPPATH', []):
            inc_dir = str(inc_path)
            if os.path.exists(inc_dir) and inc_dir != src_dir:
                include_structure.update(self._scan_directory_for_includes(inc_dir))
        
        # Library-Verzeichnis
        lib_dir = os.path.join(self.project_dir, "lib")
        if os.path.exists(lib_dir):
            include_structure.update(self._scan_directory_for_includes(lib_dir))
        
        # Sortiert für konsistente Hashes
        sorted_structure = json.dumps(include_structure, sort_keys=True)
        return hashlib.sha256(sorted_structure.encode()).hexdigest()
    
    def _scan_directory_for_includes(self, directory):
        """Scanne Verzeichnis nach Include-relevanten Änderungen"""
        include_map = {}
        
        for root, _, files in os.walk(directory):
            for file in sorted(files):  # Sortiert für Konsistenz
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, self.project_dir)
                
                if file.endswith(('.h', '.hpp')):
                    # Header-Dateien: Vollständige Include-Analyse
                    include_map[rel_path] = self.extract_include_dependencies(file_path)
                
                elif file.endswith(('.cpp', '.c', '.ino')):
                    # Source-Dateien: Nur Include-Statements
                    include_data = self.extract_include_dependencies(file_path)
                    # Nur Include-relevante Teile speichern
                    filtered_data = {
                        'includes': include_data.get('includes', []),
                        'conditional_includes': include_data.get('conditional_includes', [])
                    }
                    if filtered_data['includes'] or filtered_data['conditional_includes']:
                        include_map[rel_path] = filtered_data
                
                elif file.endswith(('.json', '.properties')):
                    # Library-Manifeste: Vollständiger Inhalt
                    include_map[rel_path] = self._get_file_hash(file_path)
        
        return include_map
    
    def _get_file_hash(self, file_path):
        """Erstelle Hash einer einzelnen Datei"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()[:8]
        except:
            return "unreadable"
    
    def get_config_hash(self):
        """Hash für platformio.ini - nur relevante Sektionen"""
        ini_file = os.path.join(self.project_dir, "platformio.ini")
        if not os.path.exists(ini_file):
            return ""
        
        relevant_lines = []
        current_env = f"[env:{env['PIOENV']}]"
        in_relevant_section = False
        
        try:
            with open(ini_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    
                    # Sektions-Erkennung
                    if line.startswith('['):
                        in_relevant_section = (line == current_env or 
                                             line == '[platformio]' or 
                                             line == '[common]')
                    
                    # Relevante Zeilen sammeln
                    elif in_relevant_section and line and not line.startswith(';'):
                        # Nur dependency-relevante Optionen
                        if any(line.startswith(prefix) for prefix in [
                            'lib_deps', 'lib_', 'build_flags', 'board', 
                            'platform', 'framework', 'monitor_', 'upload_'
                        ]):
                            relevant_lines.append(line)
        
        except Exception:
            # Fallback: Ganze Datei
            with open(ini_file, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        
        return hashlib.md5('\n'.join(relevant_lines).encode()).hexdigest()
    
    def get_combined_hash(self):
        """Kombinierter Hash aus Config und Include-Struktur"""
        config_hash = self.get_config_hash()
        include_hash = self.get_include_structure_hash()
        
        combined = f"{config_hash}:{include_hash}"
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def has_include_changes_since_cache(self, cache_data):
        """Prüfe ob Include-relevante Änderungen seit letztem Cache aufgetreten sind"""
        if not cache_data:
            return True
        
        current_hash = self.get_combined_hash()
        cached_hash = cache_data.get('combined_hash')
        
        if current_hash != cached_hash:
            # Detaillierte Analyse welcher Teil sich geändert hat
            current_config = self.get_config_hash()
            current_includes = self.get_include_structure_hash()
            
            cached_config = cache_data.get('config_hash', '')
            cached_includes = cache_data.get('include_hash', '')
            
            if current_config != cached_config:
                print("🔧 platformio.ini Änderungen erkannt")
                return True
            
            if current_includes != cached_includes:
                print("📁 Include-Struktur Änderungen erkannt")
                return True
        
        return False
    
    def load_and_validate_cache(self):
        """Lade Cache und prüfe auf Include-Änderungen"""
        if not os.path.exists(self.cache_file):
            return None
        
        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Environment-Check
            if cache_data.get('pioenv') != env['PIOENV']:
                print("🔄 Environment geändert")
                return None
            
            # Include-Change-Check
            if self.has_include_changes_since_cache(cache_data):
                return None
            
            print("✅ Keine Include-Änderungen - Cache verwendbar")
            return cache_data
            
        except Exception as e:
            print(f"⚠ Cache-Validierung fehlgeschlagen: {e}")
            return None
    
    def apply_cache(self, cache_data):
        """Wende Cache an"""
        env.Replace(LIB_LDF_MODE="off")
        
        results = cache_data.get('ldf_results', {})
        
        if results.get('CPPPATH'):
            env.PrependUnique(CPPPATH=results['CPPPATH'])
        if results.get('LIBPATH'):
            env.PrependUnique(LIBPATH=results['LIBPATH'])
        if results.get('LIBS'):
            env.PrependUnique(LIBS=results['LIBS'])
        if results.get('CPPDEFINES'):
            env.AppendUnique(CPPDEFINES=results['CPPDEFINES'])
        
        lib_count = len(results.get('LIBS', []))
        print(f"📦 {lib_count} Libraries aus Cache geladen")
    
    def save_cache(self, target, source, env_arg):
        """Speichere detaillierten Cache"""
        if env.get("LIB_LDF_MODE") == "off":
            return
        
        try:
            cache_data = {
                'combined_hash': self.get_combined_hash(),
                'config_hash': self.get_config_hash(),
                'include_hash': self.get_include_structure_hash(),
                'pioenv': env['PIOENV'],
                'timestamp': datetime.datetime.now().isoformat(),
                'ldf_results': {
                    'CPPPATH': [str(p) for p in env.get('CPPPATH', [])],
                    'LIBPATH': [str(p) for p in env.get('LIBPATH', [])],
                    'LIBS': env.get('LIBS', []),
                    'CPPDEFINES': env.get('CPPDEFINES', [])
                }
            }
            
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            lib_count = len(cache_data['ldf_results'].get('LIBS', []))
            print(f"💾 Präziser LDF-Cache gespeichert ({lib_count} Libraries)")
            
        except Exception as e:
            print(f"⚠ Cache-Speicherung fehlgeschlagen: {e}")
    
    def setup(self):
        """Hauptlogik"""
        print("\n=== Precise LDF Cache ===")
        
        cache_data = self.load_and_validate_cache()
        
        if cache_data:
            self.apply_cache(cache_data)
        else:
            print("🔄 LDF-Neuberechnung erforderlich")
            env.AddPostAction("$PROGPATH", self.save_cache)
        
        print("=========================")

# Cache initialisieren
precise_cache = PreciseLDFCache()
precise_cache.setup()
