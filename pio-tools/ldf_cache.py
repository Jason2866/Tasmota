Import("env")
import os
import hashlib
import configparser
import shutil
import glob
import time
import importlib.util

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

def convert_all_scons_objects_to_text(value, key="", depth=0):
    """Konvertiert ALLE SCons-Objekte rekursiv in Klartext"""
    
    # Schutz vor zu tiefer Rekursion
    if depth > 10:
        return str(value)
    
    # 1. SCons.Node.FS.File und ähnliche Node-Objekte
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
            converted_item = convert_all_scons_objects_to_text(item, key, depth + 1)
            converted_list.append(converted_item)
        return converted_list
    
    # 8. Tupel rekursiv verarbeiten
    elif isinstance(value, tuple):
        converted_items = []
        for item in value:
            converted_item = convert_all_scons_objects_to_text(item, key, depth + 1)
            converted_items.append(converted_item)
        return tuple(converted_items)
    
    # 9. Dictionaries rekursiv verarbeiten
    elif isinstance(value, dict):
        converted_dict = {}
        for dict_key, dict_value in value.items():
            converted_key = convert_all_scons_objects_to_text(dict_key, key, depth + 1)
            converted_value = convert_all_scons_objects_to_text(dict_value, key, depth + 1)
            converted_dict[converted_key] = converted_value
        return converted_dict
    
    # 10. deque (collections.deque) - wie bei CPPDEFINES
    elif hasattr(value, '__class__') and value.__class__.__name__ == 'deque':
        return list(value)  # Konvertiere deque zu normaler Liste
    
    # 11. os.environ und ähnliche Mapping-Objekte
    elif hasattr(value, '__class__') and 'environ' in str(value.__class__).lower():
        return dict(value)  # Konvertiere zu normalem Dictionary
    
    # 12. Spezielle SCons-Klassen mit String-Repräsentation
    elif hasattr(value, '__class__') and 'SCons' in str(value.__class__):
        # Versuche verschiedene Methoden für String-Konvertierung
        if hasattr(value, 'get_contents'):
            try:
                return str(value.get_contents())
            except:
                pass
        if hasattr(value, 'get_text_contents'):
            try:
                return str(value.get_text_contents())
            except:
                pass
        # Fallback zu String-Repräsentation
        return str(value)
    
    # 13. Primitive Typen direkt zurückgeben
    elif isinstance(value, (str, int, float, bool, type(None))):
        return value
    
    # 14. Alles andere als String
    else:
        return str(value)

def count_conversions(value, stats, depth=0):
    """Zählt verschiedene Arten von SCons-Objekt-Konvertierungen"""
    
    if depth > 5:  # Schutz vor zu tiefer Rekursion
        return
    
    if hasattr(value, 'abspath') or hasattr(value, 'path'):
        stats["files"] += 1
    elif hasattr(value, '__class__') and 'SCons.Builder' in str(value.__class__):
        stats["builders"] += 1
    elif callable(value):
        stats["functions"] += 1
    elif hasattr(value, '__class__') and 'SCons' in str(value.__class__):
        stats["other"] += 1
    elif isinstance(value, (list, tuple)):
        for item in value:
            count_conversions(item, stats, depth + 1)
    elif isinstance(value, dict):
        for dict_value in value.values():
            count_conversions(dict_value, stats, depth + 1)

def freeze_exact_scons_configuration():
    """Speichert Environment mit vollständiger SCons-Objekt-Konvertierung"""
    cache_file = get_cache_file_path()
    temp_file = cache_file + ".tmp"
    
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write("# SCons Environment Snapshot - ALL OBJECTS CONVERTED TO TEXT\n")
            f.write("# Auto-generated - do not edit manually\n")
            f.write(f"# Generated: {time.ctime()}\n")
            f.write(f"# Environment: {env.get('PIOENV')}\n\n")
            
            f.write("def restore_environment(target_env):\n")
            f.write('    """Stellt das SCons-Environment mit konvertierten Objekten wieder her"""\n')
            f.write('    restored_count = 0\n')
            f.write('    conversion_stats = {"files": 0, "builders": 0, "functions": 0, "other": 0}\n')
            f.write('    \n')
            
            scons_dict = env.Dictionary()
            var_count = 0
            conversion_stats = {"files": 0, "builders": 0, "functions": 0, "other": 0}
            
            for key, value in sorted(scons_dict.items()):
                try:
                    # Vollständige Konvertierung aller SCons-Objekte
                    converted_value = convert_all_scons_objects_to_text(value, key)
                    
                    # Statistiken sammeln
                    count_conversions(value, conversion_stats)
                    
                    f.write(f'    # {key} (Original: {type(value).__name__})\n')
                    f.write(f'    try:\n')
                    f.write(f'        target_env[{repr(key)}] = {repr(converted_value)}\n')
                    f.write(f'        restored_count += 1\n')
                    f.write(f'    except Exception as e:\n')
                    f.write(f'        print(f"⚠ Fehler bei {key}: {{e}}")\n')
                    f.write(f'        pass\n')
                    f.write(f'    \n')
                    var_count += 1
                    
                except Exception as e:
                    f.write(f'    # {key}: KONVERTIERUNGSFEHLER - {e}\n')
                    f.write(f'    conversion_stats["other"] += 1\n')
                    continue
            
            # Konvertierungs-Statistiken
            f.write('    # === KONVERTIERUNGS-STATISTIKEN ===\n')
            f.write(f'    conversion_stats["files"] = {conversion_stats["files"]}\n')
            f.write(f'    conversion_stats["builders"] = {conversion_stats["builders"]}\n')
            f.write(f'    conversion_stats["functions"] = {conversion_stats["functions"]}\n')
            f.write(f'    conversion_stats["other"] = {conversion_stats["other"]}\n')
            f.write('    \n')
            
            f.write('    print(f"✓ {{restored_count}} SCons-Variablen wiederhergestellt")\n')
            f.write('    print(f"✓ {{conversion_stats[\"files\"]}} Datei-Objekte konvertiert")\n')
            f.write('    print(f"✓ {{conversion_stats[\"builders\"]}} Builder-Objekte konvertiert")\n')
            f.write('    print(f"✓ {{conversion_stats[\"functions\"]}} Funktionen konvertiert")\n')
            f.write('    print(f"✓ {{conversion_stats[\"other\"]}} andere Objekte konvertiert")\n')
            f.write('    return restored_count > 50\n')
            f.write('\n')
            f.write('# Metadata\n')
            f.write(f'CONFIG_HASH = {repr(calculate_config_hash())}\n')
            f.write(f'ENV_NAME = {repr(env.get("PIOENV"))}\n')
            f.write(f'VARIABLE_COUNT = {var_count}\n')
            f.write(f'CONVERTED_FILES = {conversion_stats["files"]}\n')
            f.write(f'CONVERTED_BUILDERS = {conversion_stats["builders"]}\n')
            f.write(f'CONVERTED_FUNCTIONS = {conversion_stats["functions"]}\n')
            f.write(f'CONVERTED_OTHER = {conversion_stats["other"]}\n')
        
        # Atomarer Move
        shutil.move(temp_file, cache_file)
        
        file_size = os.path.getsize(cache_file)
        total_conversions = sum(conversion_stats.values())
        
        print(f"✓ Environment mit vollständiger Objekt-Konvertierung gespeichert:")
        print(f"   📁 {os.path.basename(cache_file)} ({file_size} Bytes)")
        print(f"   📊 {var_count} SCons-Variablen")
        print(f"   🔄 {total_conversions} Objekte konvertiert:")
        print(f"      📄 {conversion_stats['files']} Datei-Objekte")
        print(f"      🔨 {conversion_stats['builders']} Builder-Objekte")
        print(f"      ⚙️  {conversion_stats['functions']} Funktionen")
        print(f"      📦 {conversion_stats['other']} andere Objekte")
        
        return True
        
    except Exception as e:
        print(f"❌ Vollständige Objekt-Konvertierung fehlgeschlagen: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def restore_exact_scons_configuration():
    """Lädt Environment aus Python-Datei"""
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
            print("⚠ Konfiguration geändert - Python-Cache ungültig")
            return False
        
        # Environment wiederherstellen
        success = env_module.restore_environment(env)
        
        if success:
            var_count = getattr(env_module, 'VARIABLE_COUNT', 0)
            converted_files = getattr(env_module, 'CONVERTED_FILES', 0)
            converted_builders = getattr(env_module, 'CONVERTED_BUILDERS', 0)
            converted_functions = getattr(env_module, 'CONVERTED_FUNCTIONS', 0)
            converted_other = getattr(env_module, 'CONVERTED_OTHER', 0)
            
            print(f"✓ Environment aus Python-Datei wiederhergestellt:")
            print(f"   📊 {var_count} Variablen")
            print(f"   📄 {converted_files} Datei-Objekte")
            print(f"   🔨 {converted_builders} Builder-Objekte")
            print(f"   ⚙️  {converted_functions} Funktionen")
            print(f"   📦 {converted_other} andere Objekte")
        
        return success
        
    except Exception as e:
        print(f"❌ Python-Datei-Wiederherstellung fehlgeschlagen: {e}")
        return False

def early_cache_check_and_restore():
    """Prüft Cache und stellt SCons-Environment wieder her"""
    print(f"🔍 Cache-Prüfung (Vollständige Objekt-Konvertierung)...")
    
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        print(f"📝 Kein Python-Cache - LDF wird normal ausgeführt")
        return False
    
    current_ldf_mode = get_current_ldf_mode(env.get("PIOENV"))
    
    if current_ldf_mode != 'off':
        print(f"🔄 LDF noch aktiv - Python-Cache wird nach Build erstellt")
        return False
    
    print(f"⚡ Python-Cache verfügbar - stelle Environment wieder her")
    
    success = restore_exact_scons_configuration()
    return success

def count_scons_objects_in_value(value, depth=0):
    """Zählt verbleibende SCons-Objekte in einem Wert"""
    
    if depth > 5:
        return 0
    
    count = 0
    
    if hasattr(value, '__class__') and 'SCons' in str(value.__class__):
        count += 1
    elif isinstance(value, (list, tuple)):
        for item in value:
            count += count_scons_objects_in_value(item, depth + 1)
    elif isinstance(value, dict):
        for dict_value in value.values():
            count += count_scons_objects_in_value(dict_value, depth + 1)
    
    return count

def verify_frozen_restoration():
    """Erweiterte Verifikation mit Objekt-Konvertierungs-Check"""
    print(f"\n🔍 SCons-Environment-Verifikation (Vollständige Objekt-Konvertierung)...")
    
    critical_scons_vars = [
        "CPPPATH", "CPPDEFINES", "BUILD_FLAGS", "LIBS", 
        "CCFLAGS", "CXXFLAGS", "LINKFLAGS", "PIOBUILDFILES"
    ]
    
    all_ok = True
    scons_objects_found = 0
    
    for var in critical_scons_vars:
        if var in env and env[var]:
            value = env[var]
            
            # Prüfe ob noch SCons-Objekte vorhanden sind
            scons_obj_count = count_scons_objects_in_value(value)
            scons_objects_found += scons_obj_count
            
            if var == "CPPPATH":
                paths = value
                print(f"   ✅ {var}: {len(paths)} Include-Pfade")
                
                # Prüfe lib/default/headers
                project_dir = env.get("PROJECT_DIR")
                lib_default = os.path.join(project_dir, "lib", "default", "headers")
                found = any(lib_default in str(path) for path in paths)
                
                if found:
                    print(f"      ✅ lib/default/headers: VERFÜGBAR")
                else:
                    print(f"      ❌ lib/default/headers: FEHLT")
                    all_ok = False
                
                # Prüfe auf String-Pfade (keine Objekte mehr)
                string_paths = [p for p in paths if isinstance(p, str)]
                print(f"      ✅ String-Pfade: {len(string_paths)}/{len(paths)}")
                
            elif var == "PIOBUILDFILES":
                # Prüfe ob Datei-Objekte zu Strings konvertiert wurden
                if isinstance(value, list):
                    string_files = 0
                    for item_list in value:
                        if isinstance(item_list, list):
                            string_files += sum(1 for item in item_list if isinstance(item, str))
                    print(f"   ✅ {var}: {string_files} Dateien als Strings")
                else:
                    print(f"   ✅ {var}: Vorhanden")
                    
            elif hasattr(value, '__len__') and not isinstance(value, str):
                print(f"   ✅ {var}: {len(value)} Einträge")
                if scons_obj_count > 0:
                    print(f"      ⚠️  {scons_obj_count} SCons-Objekte noch vorhanden")
            else:
                print(f"   ✅ {var}: Vorhanden")
        else:
            print(f"   ❌ {var}: Fehlt")
            all_ok = False
    
    scons_dict_size = len(env.Dictionary())
    print(f"   📊 SCons Dictionary: {scons_dict_size} Variablen")
    print(f"   🔄 Verbleibende SCons-Objekte: {scons_objects_found}")
    
    if all_ok and scons_objects_found == 0:
        print(f"✅ SCons-Environment vollständig konvertiert und wiederhergestellt")
    elif all_ok:
        print(f"⚠️  SCons-Environment wiederhergestellt, aber {scons_objects_found} Objekte nicht konvertiert")
    else:
        print(f"❌ SCons-Environment UNVOLLSTÄNDIG")
    
    return all_ok

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
# HAUPTLOGIK - UNIVERSELLE SCONS-OBJEKT-KONVERTIERUNG
# =============================================================================

print(f"\n🎯 Universelle SCons-Objekt-Konvertierung für: {env.get('PIOENV')}")

# Cache-Prüfung und SCons-Environment-Wiederherstellung
cache_restored = early_cache_check_and_restore()

if cache_restored:
    print(f"🚀 Build mit vollständig konvertierter SCons-Konfiguration - LDF übersprungen!")
    
    if not verify_frozen_restoration():
        print(f"❌ KRITISCHER FEHLER: SCons-Environment unvollständig!")
        print(f"💡 Löschen Sie '.pio/ldf_cache/' und starten Sie neu")

else:
    print(f"📝 Normaler LDF-Durchlauf - konvertiere ALLE SCons-Objekte...")
    
    def post_build_freeze_configuration(source, target, env):
        """Post-Build: Speichere SCons-Konfiguration mit vollständiger Objekt-Konvertierung"""
        print(f"\n🔄 Post-Build: Konvertiere ALLE SCons-Objekte zu Klartext...")
        
        if freeze_exact_scons_configuration():
            print(f"\n🎯 ALLE SCons-Objekte erfolgreich konvertiert:")
            
            # Setze LDF auf off ERST NACH erfolgreichem Speichern
            env_name = env.get("PIOENV")
            if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                print(f"✓ lib_ldf_mode = off für Lauf 2 gesetzt")
                print(f"🚀 Lauf 2: Vollständig konvertierte Konfiguration!")
            else:
                print(f"⚠ lib_ldf_mode konnte nicht gesetzt werden")
            
        else:
            print(f"❌ Universelle Objekt-Konvertierung fehlgeschlagen")
    
    env.AddPostAction("buildprog", post_build_freeze_configuration)

print(f"🏁 Universelle SCons-Objekt-Konvertierung initialisiert")
print(f"💡 Reset: rm -rf .pio/ldf_cache/\n")
