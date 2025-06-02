Import("env")
import os
import hashlib
import configparser
import shutil
import glob
import time
import importlib.util

# Globale Variablen
_backup_created = False

def get_cache_file_path():
    """Generiert Pfad zur LDF-Cache-Datei für das aktuelle Environment"""
    env_name = env.get("PIOENV")
    project_dir = env.get("PROJECT_DIR")
    cache_dir = os.path.join(project_dir, ".pio", "ldf_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{env_name}_scons_env.py")

def find_all_platformio_files():
    """Findet alle platformio*.ini Dateien im Projekt"""
    project_dir = env.get("PROJECT_DIR")
    
    ini_patterns = ['platformio.ini', 'platformio_*.ini']
    ini_files = []
    for pattern in ini_patterns:
        found_files = glob.glob(os.path.join(project_dir, pattern))
        ini_files.extend(found_files)
    
    ini_files = list(set(ini_files))
    ini_files.sort()
    return ini_files

def find_env_definition_file(env_name):
    """Findet die Datei, die das spezifische Environment definiert"""
    ini_files = find_all_platformio_files()
    
    for ini_file in ini_files:
        try:
            config = configparser.ConfigParser(allow_no_value=True)
            config.read(ini_file, encoding='utf-8')
            
            section_name = f"env:{env_name}"
            if config.has_section(section_name):
                return ini_file
        except:
            continue
    
    return None

def backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
    """Findet und modifiziert die korrekte platformio*.ini Datei"""
    env_file = find_env_definition_file(env_name)
    
    if not env_file:
        project_dir = env.get("PROJECT_DIR")
        env_file = os.path.join(project_dir, "platformio.ini")
    
    if not os.path.exists(env_file):
        return False
    
    backup_file = f"{env_file}.ldf_backup"
    if not os.path.exists(backup_file):
        shutil.copy2(env_file, backup_file)
        print(f"✓ Backup erstellt: {os.path.basename(backup_file)}")
    
    try:
        config = configparser.ConfigParser(allow_no_value=True)
        config.read(env_file, encoding='utf-8')
        
        section_name = f"env:{env_name}"
        
        if not config.has_section(section_name):
            return False
        
        if set_ldf_off:
            config.set(section_name, "lib_ldf_mode", "off")
            print(f"✓ lib_ldf_mode = off gesetzt in {os.path.basename(env_file)}")
        else:
            if config.has_option(section_name, "lib_ldf_mode"):
                config.remove_option(section_name, "lib_ldf_mode")
                print(f"✓ lib_ldf_mode entfernt aus {os.path.basename(env_file)}")
        
        with open(env_file, 'w', encoding='utf-8') as f:
            config.write(f, space_around_delimiters=True)
        
        return True
        
    except Exception as e:
        print(f"⚠ Fehler beim Modifizieren von {os.path.basename(env_file)}: {e}")
        return False

def get_current_ldf_mode(env_name):
    """Ermittelt aktuellen LDF-Modus aus allen platformio*.ini Dateien"""
    ini_files = find_all_platformio_files()
    merged_config = configparser.ConfigParser(allow_no_value=True)
    
    for ini_file in ini_files:
        try:
            temp_config = configparser.ConfigParser(allow_no_value=True)
            temp_config.read(ini_file, encoding='utf-8')
            
            for section_name in temp_config.sections():
                if not merged_config.has_section(section_name):
                    merged_config.add_section(section_name)
                
                for option, value in temp_config.items(section_name):
                    merged_config.set(section_name, option, value)
        except:
            continue
    
    section_name = f"env:{env_name}"
    if merged_config.has_section(section_name):
        if merged_config.has_option(section_name, 'lib_ldf_mode'):
            return merged_config.get(section_name, 'lib_ldf_mode')
    
    if merged_config.has_section('env'):
        if merged_config.has_option('env', 'lib_ldf_mode'):
            return merged_config.get('env', 'lib_ldf_mode')
    
    return 'chain'

def determine_path_source(path):
    """Bestimmt Quelle eines Include-Pfads"""
    path_str = str(path)
    
    if 'framework-' in path_str:
        return "FRAMEWORK"
    elif 'toolchain-' in path_str:
        return "TOOLCHAIN"
    elif 'lib/' in path_str and '.pio/' in path_str:
        return "LIB_DEPS"
    elif 'lib/' in path_str:
        return "PROJECT_LIB"
    elif 'src/' in path_str or 'include/' in path_str:
        return "PROJECT"
    elif '.platformio' in path_str:
        return "PLATFORM"
    elif 'packages/' in path_str:
        return "PACKAGES"
    else:
        return "UNKNOWN"

def convert_scons_objects_selective(value, key="", depth=0):
    """Konvertiert NUR SCons-Objekte zu Pfaden, String-Pfade bleiben unverändert"""
    
    # Schutz vor zu tiefer Rekursion
    if depth > 10:
        return str(value)
    
    # 1. SCons.Node.FS.File und ähnliche Node-Objekte → Pfade konvertieren
    if hasattr(value, 'abspath'):
        return str(value.abspath)
    elif hasattr(value, 'path'):
        return str(value.path)
    elif hasattr(value, 'get_path'):
        try:
            return str(value.get_path())
        except:
            return str(value)
    
    # 2. SCons.Builder-Objekte
    elif hasattr(value, '__class__') and 'SCons.Builder' in str(value.__class__):
        return f"<Builder:{getattr(value, 'name', 'Unknown')}>"
    
    # 3. SCons.Scanner-Objekte
    elif hasattr(value, '__class__') and 'SCons.Scanner' in str(value.__class__):
        return f"<Scanner:{getattr(value, 'name', 'Unknown')}>"
    
    # 4. SCons.Environment-Objekte
    elif hasattr(value, '__class__') and 'SCons.Environment' in str(value.__class__):
        return "<Environment>"
    
    # 5. SCons.Defaults-Objekte (Variable_Method_Caller etc.)
    elif hasattr(value, '__class__') and 'SCons.Defaults' in str(value.__class__):
        return f"<Default:{value.__class__.__name__}>"
    
    # 6. Funktionen und Callables
    elif callable(value):
        if hasattr(value, '__name__'):
            return f"<Function:{value.__name__}>"
        else:
            return f"<Callable:{value.__class__.__name__}>"
    
    # 7. Listen rekursiv verarbeiten
    elif isinstance(value, list):
        converted_list = []
        for item in value:
            converted_item = convert_scons_objects_selective(item, key, depth + 1)
            converted_list.append(converted_item)
        return converted_list
    
    # 8. Tupel rekursiv verarbeiten
    elif isinstance(value, tuple):
        converted_items = []
        for item in value:
            converted_item = convert_scons_objects_selective(item, key, depth + 1)
            converted_items.append(converted_item)
        return tuple(converted_items)
    
    # 9. Dictionaries rekursiv verarbeiten
    elif isinstance(value, dict):
        converted_dict = {}
        for dict_key, dict_value in value.items():
            converted_key = convert_scons_objects_selective(dict_key, key, depth + 1)
            converted_value = convert_scons_objects_selective(dict_value, key, depth + 1)
            converted_dict[converted_key] = converted_value
        return converted_dict
    
    # 10. deque (collections.deque) - wie bei CPPDEFINES
    elif hasattr(value, '__class__') and value.__class__.__name__ == 'deque':
        return list(value)  # Konvertiere deque zu normaler Liste
    
    # 11. os.environ und ähnliche Mapping-Objekte
    elif hasattr(value, '__class__') and 'environ' in str(value.__class__).lower():
        return dict(value)  # Konvertiere zu normalem Dictionary
    
    # 12. Andere SCons-Objekte (nicht Pfad-bezogen)
    elif hasattr(value, '__class__') and 'SCons' in str(value.__class__):
        return str(value)
    
    # 13. String-Pfade und primitive Typen UNVERÄNDERT lassen
    elif isinstance(value, (str, int, float, bool, type(None))):
        return value  # KEINE ÄNDERUNG an String-Pfaden!
    
    # 14. Alles andere als String
    else:
        return str(value)

def capture_direct_environment():
    """Erfasst Environment-Daten DIREKT ohne Clone/Dictionary"""
    
    print(f"\n🎯 DIREKTE Environment-Erfassung (ohne Clone):")
    
    # Kritische Variablen direkt aus Original-Environment lesen
    critical_vars = [
        'CPPPATH', 'CPPDEFINES', 'LIBS', 'LIBPATH', 
        'BUILD_FLAGS', 'CCFLAGS', 'CXXFLAGS', 'LINKFLAGS',
        'PIOBUILDFILES', 'LIB_DEPS', 'LIB_EXTRA_DIRS',
        'FRAMEWORK_DIR', 'PLATFORM_PACKAGES_DIR'
    ]
    
    direct_data = {}
    conversion_stats = {"file_paths": 0, "builders": 0, "functions": 0, "other": 0}
    
    for var in critical_vars:
        # DIREKTER Zugriff auf env, KEIN Clone/Dictionary
        raw_value = env.get(var, [])
        
        if var == 'CPPPATH':
            print(f"   📁 CPPPATH: {len(raw_value)} Einträge (direkt erfasst)")
            
            # Zeige erste 5 zur Verifikation
            for i, path in enumerate(raw_value[:5]):
                path_str = str(path.abspath) if hasattr(path, 'abspath') else str(path)
                source = determine_path_source(path_str)
                exists = os.path.exists(path_str)
                print(f"      {i:2d}: {source:12s} {'✓' if exists else '✗'} {path_str}")
        
        elif var == 'PIOBUILDFILES':
            if isinstance(raw_value, list):
                total_files = sum(len(file_list) if isinstance(file_list, list) else 0 for file_list in raw_value)
                print(f"   🔨 PIOBUILDFILES: {len(raw_value)} Listen, {total_files} Dateien total")
        
        elif isinstance(raw_value, list):
            print(f"   📊 {var}: {len(raw_value)} Einträge")
        else:
            print(f"   📊 {var}: {type(raw_value).__name__}")
        
        # Konvertiere SCons-Objekte zu wiederverwendbaren Daten
        converted_value = convert_scons_objects_selective(raw_value, var)
        direct_data[var] = converted_value
        
        # Zähle Konvertierungen (vereinfacht)
        if var == 'CPPPATH' and isinstance(raw_value, list):
            for item in raw_value:
                if hasattr(item, 'abspath'):
                    conversion_stats["file_paths"] += 1
    
    print(f"   🔄 {conversion_stats['file_paths']} SCons-Pfad-Objekte konvertiert")
    print(f"   ✅ String-Pfade blieben unverändert")
    
    return direct_data, conversion_stats

def freeze_direct_scons_configuration(direct_data, conversion_stats):
    """Speichert direkt erfasste Environment-Daten"""
    cache_file = get_cache_file_path()
    temp_file = cache_file + ".tmp"
    
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write("# SCons Environment - DIREKTE Erfassung (ohne Clone)\n")
            f.write("# SCons objects → paths, String paths unchanged\n")
            f.write("# Auto-generated - do not edit manually\n")
            f.write(f"# Generated: {time.ctime()}\n")
            f.write(f"# Environment: {env.get('PIOENV')}\n")
            f.write(f"# Captured DIRECTLY after compile, before linking\n\n")
            
            f.write("def restore_environment(target_env):\n")
            f.write('    """Stellt das direkt erfasste SCons-Environment wieder her"""\n')
            f.write('    restored_count = 0\n')
            f.write('    \n')
            
            var_count = 0
            
            for key, value in sorted(direct_data.items()):
                try:
                    f.write(f'    # {key} (Direkt erfasst)\n')
                    f.write(f'    try:\n')
                    f.write(f'        target_env[{repr(key)}] = {repr(value)}\n')
                    f.write(f'        restored_count += 1\n')
                    f.write(f'    except Exception as e:\n')
                    f.write(f'        print(f"⚠ Fehler bei {key}: {{e}}")\n')
                    f.write(f'        pass\n')
                    f.write(f'    \n')
                    var_count += 1
                    
                except Exception as e:
                    f.write(f'    # {key}: KONVERTIERUNGSFEHLER - {e}\n')
                    continue
            
            # Konvertierungs-Statistiken
            f.write('    # === DIREKTE ERFASSUNG STATISTIKEN ===\n')
            f.write(f'    conversion_stats = {repr(conversion_stats)}\n')
            f.write('    \n')
            
            f.write('    print(f"✓ {{restored_count}} SCons-Variablen wiederhergestellt (Direkte Erfassung)")\n')
            f.write('    print(f"✓ {{conversion_stats[\'file_paths\']}} SCons-Pfad-Objekte konvertiert")\n')
            f.write('    print(f"✓ String-Pfade blieben unverändert")\n')
            f.write('    print("✓ KEIN Clone/Dictionary verwendet")\n')
            f.write('    return restored_count > 10\n')
            f.write('\n')
            f.write('# Metadata\n')
            f.write(f'CONFIG_HASH = {repr(calculate_config_hash())}\n')
            f.write(f'ENV_NAME = {repr(env.get("PIOENV"))}\n')
            f.write(f'VARIABLE_COUNT = {var_count}\n')
            f.write(f'DIRECT_CAPTURE = True\n')
            f.write(f'CONVERTED_FILE_PATHS = {conversion_stats["file_paths"]}\n')
        
        # Atomarer Move
        shutil.move(temp_file, cache_file)
        
        file_size = os.path.getsize(cache_file)
        cpppath_count = len(direct_data.get('CPPPATH', []))
        
        print(f"✓ Direkte Environment-Erfassung gespeichert:")
        print(f"   📁 {os.path.basename(cache_file)} ({file_size} Bytes)")
        print(f"   📊 {var_count} SCons-Variablen (direkt erfasst)")
        print(f"   📄 {cpppath_count} CPPPATH-Einträge")
        print(f"   🔄 {conversion_stats['file_paths']} SCons-Objekte konvertiert")
        print(f"   ✅ KEIN Clone/Dictionary verwendet")
        
        return True
        
    except Exception as e:
        print(f"❌ Direkte Environment-Erfassung fehlgeschlagen: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def post_compile_action(target, source, env):
    """SCons Action: Erfasst Environment DIREKT nach Compile, vor Linking"""
    global _backup_created
    
    if _backup_created:
        print("✓ Environment bereits erfasst - überspringe Post-Compile Action")
        return None
    
    try:
        print(f"\n🎯 POST-COMPILE ACTION: Erfasse SCons-Environment DIREKT")
        print(f"   Target: {[str(t) for t in target]}")
        print(f"   Source: {len(source)} Dateien")
        
        # DIREKTE Environment-Erfassung (KEIN Clone/Dictionary)
        direct_data, conversion_stats = capture_direct_environment()
        
        # Prüfe ob realistische Werte vorhanden sind
        cpppath_count = len(direct_data.get('CPPPATH', []))
        libs_count = len(direct_data.get('LIBS', []))
        piobuildfiles_count = len(direct_data.get('PIOBUILDFILES', []))
        
        print(f"   📊 Direkte Environment-Statistik:")
        print(f"      CPPPATH: {cpppath_count} Pfade")
        print(f"      LIBS: {libs_count} Bibliotheken")
        print(f"      PIOBUILDFILES: {piobuildfiles_count} Listen")
        
        realistic_values = (
            cpppath_count > 10 and  # Mindestens 10 Include-Pfade
            libs_count >= 0 and libs_count < 50 and  # Realistische LIBS-Anzahl
            piobuildfiles_count >= 0  # Build-Dateien können 0 sein
        )
        
        if realistic_values:
            print(f"✅ Realistische Environment-Werte - speichere direkte Erfassung")
            
            if freeze_direct_scons_configuration(direct_data, conversion_stats):
                env_name = env.get("PIOENV")
                if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                    print(f"✓ lib_ldf_mode = off für Lauf 2 gesetzt")
                    print(f"🚀 DIREKTE SCons-Environment-Erfassung abgeschlossen!")
                    _backup_created = True
                else:
                    print(f"⚠ lib_ldf_mode konnte nicht gesetzt werden")
            else:
                print(f"❌ Direkte Environment-Erfassung fehlgeschlagen")
        else:
            print(f"⚠ Unrealistische Environment-Werte - überspringe Erfassung")
            print(f"   CPPPATH: {cpppath_count} (erwartet >10)")
            print(f"   LIBS: {libs_count} (erwartet 0-50)")
    
    except Exception as e:
        print(f"❌ Post-Compile Action Fehler: {e}")
    
    return None

def restore_exact_scons_configuration():
    """Lädt Environment aus Python-Datei (direkte Erfassung)"""
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        return False
    
    try:
        # Python-Datei als Modul laden
        spec = importlib.util.spec_from_file_location("scons_env_cache", cache_file)
        env_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(env_module)
        
        # Hash-Prüfung
        current_hash = calculate_config_hash()
        cached_hash = getattr(env_module, 'CONFIG_HASH', None)
        
        if cached_hash != current_hash:
            print("⚠ Konfiguration geändert - Cache ungültig")
            return False
        
        # Prüfe ob direkte Erfassung
        direct_capture = getattr(env_module, 'DIRECT_CAPTURE', False)
        if not direct_capture:
            print("⚠ Cache stammt nicht von direkter Erfassung")
        
        # Environment wiederherstellen
        success = env_module.restore_environment(env)
        
        if success:
            var_count = getattr(env_module, 'VARIABLE_COUNT', 0)
            converted_file_paths = getattr(env_module, 'CONVERTED_FILE_PATHS', 0)
            
            print(f"✓ Direkte Environment-Erfassung wiederhergestellt:")
            print(f"   📊 {var_count} Variablen")
            print(f"   📄 {converted_file_paths} SCons-Pfad-Objekte konvertiert")
            print(f"   ✅ KEIN Clone/Dictionary verwendet")
        
        return success
        
    except Exception as e:
        print(f"❌ Direkte Cache-Wiederherstellung fehlgeschlagen: {e}")
        return False

def early_cache_check_and_restore():
    """Prüft Cache und stellt SCons-Environment wieder her"""
    print(f"🔍 Cache-Prüfung (Direkte Environment-Erfassung)...")
    
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        print(f"📝 Kein direkter Cache - LDF wird normal ausgeführt")
        return False
    
    current_ldf_mode = get_current_ldf_mode(env.get("PIOENV"))
    
    if current_ldf_mode != 'off':
        print(f"🔄 LDF noch aktiv - direkter Cache wird nach Build erstellt")
        return False
    
    print(f"⚡ Direkter Cache verfügbar - stelle Environment wieder her")
    
    success = restore_exact_scons_configuration()
    return success

def calculate_config_hash():
    """Berechnet Hash der Konfiguration"""
    relevant_values = [
        f"BOARD:{env.get('BOARD', '')}",
        f"PLATFORM:{env.get('PLATFORM', '')}",
        f"PIOENV:{env.get('PIOENV', '')}"
    ]
    
    ini_files = find_all_platformio_files()
    
    for ini_file in sorted(ini_files):
        if os.path.exists(ini_file) and not ini_file.endswith('.ldf_backup'):
            try:
                with open(ini_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    file_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
                    relevant_values.append(f"{os.path.basename(ini_file)}:{file_hash}")
            except:
                pass
    
    relevant_values.sort()
    config_string = "|".join(relevant_values)
    return hashlib.md5(config_string.encode('utf-8')).hexdigest()

# =============================================================================
# HAUPTLOGIK - DIREKTE SCONS-ENVIRONMENT-ERFASSUNG (OHNE CLONE)
# =============================================================================

print(f"\n🎯 Direkte SCons-Environment-Erfassung für: {env.get('PIOENV')}")

# Cache-Prüfung und SCons-Environment-Wiederherstellung
cache_restored = early_cache_check_and_restore()

if cache_restored:
    print(f"🚀 Build mit direktem Environment-Cache - LDF übersprungen!")

else:
    print(f"📝 Normaler LDF-Durchlauf - erfasse Environment DIREKT nach Compile-Phase...")
    
    # SCons Action: Erfasse Environment DIREKT nach Compile, vor Linking
    env.AddPostAction("$BUILD_DIR/${PROGNAME}.elf", post_compile_action)
    
    print(f"✅ Direkte Post-Compile Action registriert für: $BUILD_DIR/${{PROGNAME}}.elf")

print(f"🏁 Direkte SCons-Environment-Erfassung initialisiert (KEIN Clone)")
print(f"💡 Reset: rm -rf .pio/ldf_cache/\n")
