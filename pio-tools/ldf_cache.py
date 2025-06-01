Import("env")
import os
import pickle
import gzip
import hashlib
import configparser
import shutil
import glob

def get_cache_file_path():
    """Generiert Pfad zur LDF-Cache-Datei für das aktuelle Environment"""
    env_name = env.get("PIOENV")
    project_dir = env.get("PROJECT_DIR")
    cache_dir = os.path.join(project_dir, ".pio", "ldf_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{env_name}_scons_complete.pkl.gz")

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

def safe_convert_for_pickle(obj, max_depth=10, current_depth=0):
    """Konvertiert Objekte sicher für Pickle (SCons-optimiert)"""
    if current_depth > max_depth:
        return str(obj)
    
    try:
        pickle.dumps(obj)
        return obj
    except:
        pass
    
    if obj is None:
        return None
    elif isinstance(obj, (str, int, float, bool)):
        return obj
    elif isinstance(obj, (list, tuple)):
        converted = []
        for i, item in enumerate(obj):
            if i > 2000:  # Erhöht für SCons-Datenstrukturen
                break
            converted.append(safe_convert_for_pickle(item, max_depth, current_depth + 1))
        return converted
    elif isinstance(obj, dict):
        converted = {}
        for key, value in obj.items():
            if len(converted) > 1000:  # Erhöht für SCons-Datenstrukturen
                break
            safe_key = str(key)
            converted[safe_key] = safe_convert_for_pickle(value, max_depth, current_depth + 1)
        return converted
    else:
        # SCons-spezifische Objekte als String speichern
        return str(obj)

def capture_complete_scons_environment():
    """Erfasst das KOMPLETTE SCons-Environment nach LDF-Durchlauf"""
    print(f"🔍 Erfasse KOMPLETTES SCons-Environment...")
    
    scons_data = {
        "dictionary": {},
        "internals": {},
        "metadata": {}
    }
    
    # 1. KOMPLETTES SCons Dictionary erfassen
    try:
        scons_dict = env.Dictionary()
        print(f"   📊 SCons Dictionary: {len(scons_dict)} Variablen")
        
        for key, value in scons_dict.items():
            try:
                converted_value = safe_convert_for_pickle(value)
                scons_data["dictionary"][key] = converted_value
                
                # Debug-Ausgabe für kritische Variablen
                if key == "CPPPATH" and hasattr(converted_value, '__len__'):
                    print(f"      ✓ {key}: {len(converted_value)} Include-Pfade")
                    # Prüfe lib/default/headers
                    project_dir = env.get("PROJECT_DIR")
                    lib_default = os.path.join(project_dir, "lib", "default", "headers")
                    found = any(lib_default in str(path) for path in converted_value)
                    if found:
                        print(f"         ✅ lib/default/headers: GEFUNDEN")
                    else:
                        print(f"         ⚠️  lib/default/headers: NICHT GEFUNDEN")
                elif key in ["CPPDEFINES", "BUILD_FLAGS", "LIBS"] and hasattr(converted_value, '__len__'):
                    print(f"      ✓ {key}: {len(converted_value)} Einträge")
                elif key in ["PROJECT_DIR", "PROJECT_LIB_DIR", "PLATFORM", "BOARD"]:
                    print(f"      ✓ {key}: {converted_value}")
                    
            except Exception as e:
                print(f"      ⚠ {key}: Konvertierungsfehler - {e}")
                scons_data["dictionary"][key] = str(value)[:500]
                
    except Exception as e:
        print(f"   ❌ SCons Dictionary-Fehler: {e}")
    
    # 2. SCons-Interna erfassen (soweit möglich)
    try:
        # SCons Builder-Informationen
        if hasattr(env, '_builders') and env._builders:
            builders_data = {}
            for name, builder in env._builders.items():
                try:
                    builders_data[name] = str(builder)
                except:
                    builders_data[name] = "Builder-Object"
            scons_data["internals"]["builders"] = builders_data
            print(f"   ✓ SCons Builders: {len(builders_data)} erfasst")
        
        # SCons Scanner-Informationen  
        if hasattr(env, '_scanners') and env._scanners:
            scanners_data = {}
            for scanner in env._scanners:
                try:
                    scanners_data[str(scanner)] = str(scanner)
                except:
                    scanners_data[str(scanner)] = "Scanner-Object"
            scons_data["internals"]["scanners"] = scanners_data
            print(f"   ✓ SCons Scanners: {len(scanners_data)} erfasst")
            
    except Exception as e:
        print(f"   ⚠ SCons-Interna: {e}")
    
    # 3. Metadata
    scons_data["metadata"] = {
        "pioenv": env.get("PIOENV"),
        "project_dir": env.get("PROJECT_DIR"),
        "platform": env.get("PLATFORM"),
        "board": env.get("BOARD"),
        "framework": env.get("FRAMEWORK"),
        "capture_timestamp": hashlib.md5(str(os.times()).encode()).hexdigest()[:8],
        "scons_version": str(env._get_major_minor_revision()) if hasattr(env, '_get_major_minor_revision') else "unknown"
    }
    
    total_vars = len(scons_data["dictionary"])
    print(f"✅ SCons-Environment komplett erfasst: {total_vars} Variablen")
    
    return scons_data

def restore_complete_scons_environment(scons_data):
    """Stellt das KOMPLETTE SCons-Environment wieder her"""
    print(f"⚡ Stelle KOMPLETTES SCons-Environment wieder her...")
    
    restored_count = 0
    
    # 1. ALLE SCons Dictionary-Variablen wiederherstellen
    if "dictionary" in scons_data:
        for key, value in scons_data["dictionary"].items():
            try:
                # Direkte SCons-Environment-Zuweisung
                env[key] = value
                restored_count += 1
                
                # Debug-Ausgabe für kritische Variablen
                if key == "CPPPATH" and hasattr(value, '__len__'):
                    print(f"   ✓ {key}: {len(value)} Include-Pfade wiederhergestellt")
                    # Prüfe lib/default/headers
                    project_dir = env.get("PROJECT_DIR")
                    lib_default = os.path.join(project_dir, "lib", "default", "headers")
                    found = any(lib_default in str(path) for path in value)
                    if found:
                        print(f"      ✅ lib/default/headers: WIEDERHERGESTELLT")
                    else:
                        print(f"      ❌ lib/default/headers: FEHLT IMMER NOCH")
                elif key in ["CPPDEFINES", "BUILD_FLAGS", "LIBS"] and hasattr(value, '__len__'):
                    print(f"   ✓ {key}: {len(value)} Einträge")
                elif key in ["PROJECT_DIR", "PROJECT_LIB_DIR", "PLATFORM", "BOARD"]:
                    print(f"   ✓ {key}: {value}")
                    
            except Exception as e:
                print(f"   ⚠ {key}: Wiederherstellungsfehler - {e}")
    
    # 2. SCons-Interna wiederherstellen (soweit möglich)
    if "internals" in scons_data:
        try:
            # Builder-Wiederherstellung ist komplex und möglicherweise nicht nötig
            # da diese meist zur Laufzeit generiert werden
            pass
        except Exception as e:
            print(f"   ⚠ SCons-Interna-Wiederherstellung: {e}")
    
    print(f"✅ {restored_count} SCons-Variablen wiederhergestellt")
    return restored_count > 20  # Mindestens 20 wichtige SCons-Variablen

def verify_complete_scons_environment():
    """Verifikation des wiederhergestellten SCons-Environments"""
    print(f"\n🔍 SCons-Environment-Verifikation...")
    
    # Prüfe kritische SCons-Variablen
    critical_scons_vars = [
        "CPPPATH", "CPPDEFINES", "BUILD_FLAGS", "LIBS", 
        "CCFLAGS", "CXXFLAGS", "LINKFLAGS", "PIOBUILDFILES"
    ]
    
    all_ok = True
    for var in critical_scons_vars:
        if var in env and env[var]:
            if var == "CPPPATH":
                paths = env[var]
                print(f"   ✅ {var}: {len(paths)} Include-Pfade")
                
                # Kritische lib/default/headers-Prüfung
                project_dir = env.get("PROJECT_DIR")
                lib_default = os.path.join(project_dir, "lib", "default", "headers")
                found = any(lib_default in str(path) for path in paths)
                
                if found:
                    print(f"      ✅ lib/default/headers: VERFÜGBAR")
                else:
                    print(f"      ❌ lib/default/headers: FEHLT")
                    all_ok = False
                    
            elif hasattr(env[var], '__len__') and not isinstance(env[var], str):
                print(f"   ✅ {var}: {len(env[var])} Einträge")
            else:
                print(f"   ✅ {var}: Vorhanden")
        else:
            print(f"   ❌ {var}: Fehlt")
            all_ok = False
    
    # Zusätzliche SCons-spezifische Prüfungen
    scons_dict_size = len(env.Dictionary())
    print(f"   📊 SCons Dictionary: {scons_dict_size} Variablen")
    
    if all_ok:
        print(f"✅ SCons-Environment vollständig wiederhergestellt")
    else:
        print(f"❌ SCons-Environment UNVOLLSTÄNDIG")
    
    return all_ok

def early_cache_check_and_restore():
    """Prüft Cache und stellt SCons-Environment wieder her"""
    print(f"🔍 Cache-Prüfung (KOMPLETTES SCons-Environment)...")
    
    cached_data = load_scons_cache()
    
    if not cached_data:
        print(f"📝 Kein SCons-Cache - LDF wird normal ausgeführt")
        return False
    
    current_ldf_mode = get_current_ldf_mode(env.get("PIOENV"))
    
    if current_ldf_mode != 'off':
        print(f"🔄 LDF noch aktiv - SCons-Cache wird nach Build erstellt")
        return False
    
    print(f"⚡ SCons-Cache verfügbar - stelle komplettes Environment wieder her")
    
    # KOMPLETTES SCons-Environment wiederherstellen
    success = restore_complete_scons_environment(cached_data)
    
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

def save_scons_cache(scons_data):
    """Speichert KOMPLETTEN SCons-Cache"""
    cache_file = get_cache_file_path()
    
    try:
        cache_dir = os.path.dirname(cache_file)
        os.makedirs(cache_dir, exist_ok=True)
        
        cache_data = {
            "config_hash": calculate_config_hash(),
            "env_name": env.get("PIOENV"),
            "cache_version": "8.0",  # Neue Version für SCons-Environment
            "_cache_type": "complete_scons_environment"
        }
        
        cache_data.update(scons_data)
        
        with gzip.open(cache_file, 'wb') as f:
            pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        file_size = os.path.getsize(cache_file)
        
        print(f"✓ KOMPLETTER SCons-Cache gespeichert:")
        print(f"   📁 {os.path.basename(cache_file)} ({file_size} Bytes)")
        print(f"   📊 SCons-Variablen: {len(scons_data.get('dictionary', {}))}")
        
        return True
        
    except Exception as e:
        print(f"❌ SCons-Cache-Speicherfehler: {e}")
        return False

def load_scons_cache():
    """Lädt KOMPLETTEN SCons-Cache"""
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        return None
    
    try:
        with gzip.open(cache_file, 'rb') as f:
            cache_data = pickle.load(f)
        
        cache_version = cache_data.get("cache_version", "1.0")
        if cache_version != "8.0":
            print(f"⚠ Veraltete Cache-Version {cache_version} - wird ignoriert")
            return None
        
        current_hash = calculate_config_hash()
        cached_hash = cache_data.get("config_hash")
        
        if cached_hash == current_hash:
            # Entferne Metadaten und gib SCons-Daten zurück
            scons_data = {k: v for k, v in cache_data.items() 
                         if not k.startswith('_') and k not in ['config_hash', 'env_name', 'cache_version']}
            return scons_data
        else:
            print(f"⚠ SCons-Cache ungültig - Konfiguration geändert")
        
    except Exception as e:
        print(f"⚠ SCons-Cache-Ladefehler: {e}")
    
    return None

# =============================================================================
# HAUPTLOGIK - KOMPLETTES SCONS-ENVIRONMENT CACHING
# =============================================================================

print(f"\n🚀 Tasmota LDF-Optimierung (KOMPLETTES SCons-Environment) für: {env.get('PIOENV')}")

# Cache-Prüfung und SCons-Environment-Wiederherstellung
cache_restored = early_cache_check_and_restore()

if cache_restored:
    print(f"🚀 Build mit KOMPLETTEM SCons-Cache - LDF übersprungen!")
    
    if not verify_complete_scons_environment():
        print(f"❌ KRITISCHER FEHLER: SCons-Environment unvollständig!")
        print(f"💡 Löschen Sie '.pio/ldf_cache/' und starten Sie neu")

else:
    print(f"📝 Normaler LDF-Durchlauf - erfasse KOMPLETTES SCons-Environment...")
    
    def post_build_scons_cache(source, target, env):
        """Post-Build: KOMPLETTER SCons-Environment-Cache"""
        print(f"\n🔄 Post-Build: Erstelle KOMPLETTEN SCons-Cache...")
        
        complete_scons_data = capture_complete_scons_environment()
        
        if len(complete_scons_data.get("dictionary", {})) > 30:  # Mindestens 30 SCons-Variablen
            env_name = env.get("PIOENV")
            if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                print(f"✓ lib_ldf_mode = off gesetzt")
            
            if save_scons_cache(complete_scons_data):
                print(f"\n📊 KOMPLETTER SCons-Cache erstellt:")
                print(f"   🎯 KOMPLETTES SCons-Environment erfasst")
                print(f"   📊 Dictionary-Variablen: {len(complete_scons_data.get('dictionary', {}))}")
                print(f"   🚀 Nächster Build: Komplett ohne LDF!")
            else:
                print(f"❌ SCons-Cache-Erstellung fehlgeschlagen")
        else:
            print(f"❌ Unvollständiges SCons-Environment - Cache nicht erstellt")
    
    env.AddPostAction("buildprog", post_build_scons_cache)

print(f"🏁 KOMPLETTE SCons-Environment-Optimierung initialisiert")
print(f"💡 Cache-Reset: rm -rf .pio/ldf_cache/\n")
