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
    return os.path.join(cache_dir, f"{env_name}_ldf_build_data.pkl.gz")

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

def safe_convert_for_pickle(obj, max_depth=5, current_depth=0):
    """Konvertiert Objekte sicher für Pickle"""
    if current_depth > max_depth:
        return str(obj)
    
    try:
        # Test ob bereits pickle-bar
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
            if i > 200:  # Begrenze Listen
                break
            converted.append(safe_convert_for_pickle(item, max_depth, current_depth + 1))
        return converted
    elif isinstance(obj, dict):
        converted = {}
        for key, value in obj.items():
            if len(converted) > 100:  # Begrenze Dictionaries
                break
            safe_key = str(key)
            converted[safe_key] = safe_convert_for_pickle(value, max_depth, current_depth + 1)
        return converted
    else:
        return str(obj)

def capture_ldf_build_data_only():
    """Erfasst NUR LDF-generierte Build-Daten (ohne Tools/Toolchain)"""
    print(f"🔍 Erfasse LDF-Build-Daten (ohne Tools/Toolchain)...")
    
    # NUR LDF-generierte Build-Daten cachen
    ldf_generated_vars = [
        # Include-Pfade (wichtigste Variable!)
        "CPPPATH",
        
        # Library-Pfade und -Konfiguration
        "LIBPATH",
        "LIBSOURCE_DIRS", 
        "EXTRA_LIB_DIRS",
        
        # Preprocessor-Defines
        "CPPDEFINES",
        
        # Build-Flags
        "BUILD_FLAGS",
        "CCFLAGS", 
        "CXXFLAGS",
        "LINKFLAGS",
        
        # Libraries
        "LIBS",
        "LIB_DEPS",
        "LIB_IGNORE",
        
        # Board-spezifische Build-Daten (nicht Pfade!)
        "BOARD",
        "PLATFORM", 
        "FRAMEWORK",
        "BOARD_MCU",
        "BOARD_F_CPU",
        "BOARD_F_FLASH"
    ]
    
    ldf_data = {}
    
    for var in ldf_generated_vars:
        if var in env:
            original_value = env[var]
            
            try:
                converted_value = safe_convert_for_pickle(original_value)
                ldf_data[var] = converted_value
                
                # Debug-Ausgabe für Include-Pfade
                if var == "CPPPATH" and hasattr(converted_value, '__len__'):
                    print(f"   ✓ {var}: {len(converted_value)} Include-Pfade erfasst")
                    for i, path in enumerate(converted_value[:3]):  # Zeige erste 3
                        print(f"     {i+1}. {path}")
                    if len(converted_value) > 3:
                        print(f"     ... und {len(converted_value) - 3} weitere")
                elif hasattr(converted_value, '__len__') and not isinstance(converted_value, str):
                    print(f"   ✓ {var}: {len(converted_value)} Elemente")
                else:
                    print(f"   ✓ {var}: Erfasst")
                        
            except Exception as e:
                print(f"   ⚠ {var}: Fehler - {e}")
                ldf_data[var] = str(original_value)[:200]
    
    print(f"✅ {len(ldf_data)} LDF-Build-Variablen erfasst")
    return ldf_data

def early_cache_check_and_restore():
    """Prüft Cache und stellt LDF-Build-Daten wieder her"""
    print(f"🔍 Frühe Cache-Prüfung (LDF-Build-Daten)...")
    
    cached_data = load_ldf_build_cache()
    
    if not cached_data:
        print(f"📝 Kein Cache - LDF wird normal ausgeführt")
        return False
    
    current_ldf_mode = get_current_ldf_mode(env.get("PIOENV"))
    
    if current_ldf_mode != 'off':
        print(f"🔄 LDF noch aktiv - Cache wird nach Build erstellt")
        return False
    
    print(f"⚡ Cache verfügbar - stelle LDF-Build-Daten wieder her")
    
    # LDF-Build-Daten direkt wiederherstellen
    restored_count = 0
    
    for var_name, cached_value in cached_data.items():
        if var_name.startswith('_'):
            continue  # Skip Metadaten
            
        try:
            # Direkte Zuweisung der LDF-Daten
            env[var_name] = cached_value
            restored_count += 1
            
            # Debug-Ausgabe für Include-Pfade
            if var_name == "CPPPATH" and hasattr(cached_value, '__len__'):
                print(f"   ✓ {var_name}: {len(cached_value)} Include-Pfade wiederhergestellt")
            elif hasattr(cached_value, '__len__') and not isinstance(cached_value, str):
                print(f"   ✓ {var_name}: {len(cached_value)} Elemente")
            else:
                print(f"   ✓ {var_name}: Wiederhergestellt")
                
        except Exception as e:
            print(f"   ⚠ {var_name}: Fehler - {e}")
    
    print(f"✅ {restored_count} LDF-Build-Variablen wiederhergestellt")
    return restored_count > 3  # Mindestens CPPPATH, CPPDEFINES, BUILD_FLAGS

def verify_ldf_data_completeness():
    """Verifikation der LDF-Build-Daten"""
    print(f"\n🔍 LDF-Build-Daten-Verifikation...")
    
    critical_ldf_vars = ["CPPPATH", "CPPDEFINES", "BUILD_FLAGS"]
    
    all_ok = True
    for var in critical_ldf_vars:
        if var in env and env[var]:
            if var == "CPPPATH":
                print(f"   ✅ {var}: {len(env[var])} Include-Pfade")
            elif hasattr(env[var], '__len__'):
                print(f"   ✅ {var}: {len(env[var])} Einträge")
            else:
                print(f"   ✅ {var}: Vorhanden")
        else:
            print(f"   ❌ {var}: Fehlt")
            all_ok = False
    
    if all_ok:
        print(f"✅ LDF-Build-Daten vollständig")
    else:
        print(f"⚠️  LDF-Build-Daten unvollständig")
    
    return all_ok

def calculate_final_config_hash():
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
    hash_value = hashlib.md5(config_string.encode('utf-8')).hexdigest()
    
    return hash_value

def save_ldf_build_cache(ldf_data):
    """Speichert LDF-Build-Cache"""
    cache_file = get_cache_file_path()
    
    try:
        cache_dir = os.path.dirname(cache_file)
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
        
        final_hash = calculate_final_config_hash()
        
        cache_data = {
            "config_hash": final_hash,
            "env_name": env.get("PIOENV"),
            "cache_version": "4.0",  # Neue Version ohne Tools
            "_cache_type": "ldf_build_data_only"
        }
        
        # LDF-Build-Daten hinzufügen
        cache_data.update(ldf_data)
        
        with gzip.open(cache_file, 'wb') as f:
            pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        file_size = os.path.getsize(cache_file)
        
        print(f"✓ LDF-Build-Cache (ohne Tools) gespeichert:")
        print(f"   📁 Datei: {os.path.basename(cache_file)} ({file_size} Bytes)")
        print(f"   📊 LDF-Build-Variablen: {len(ldf_data)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Cache-Speicherfehler: {e}")
        return False

def load_ldf_build_cache():
    """Lädt LDF-Build-Cache"""
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        return None
    
    try:
        with gzip.open(cache_file, 'rb') as f:
            cache_data = pickle.load(f)
        
        cache_version = cache_data.get("cache_version", "1.0")
        if cache_version not in ["3.0", "4.0"]:
            print(f"⚠ Veraltete Cache-Version {cache_version} - wird ignoriert")
            return None
        
        current_hash = calculate_final_config_hash()
        cached_hash = cache_data.get("config_hash")
        
        if cached_hash == current_hash:
            # Entferne Metadaten und gib nur LDF-Build-Daten zurück
            ldf_data = {k: v for k, v in cache_data.items() 
                       if not k.startswith('_') and k not in ['config_hash', 'env_name', 'cache_version']}
            return ldf_data
        else:
            print(f"⚠ LDF-Cache ungültig - Konfiguration hat sich geändert")
        
    except Exception as e:
        print(f"⚠ Cache-Ladefehler: {e}")
    
    return None

# =============================================================================
# HAUPTLOGIK - LDF-BUILD-DATEN CACHING (OHNE TOOLS)
# =============================================================================

print(f"\n🚀 Tasmota LDF-Optimierung (Build-Daten ohne Tools) für Environment: {env.get('PIOENV')}")

# Cache-Prüfung und Wiederherstellung
cache_restored = early_cache_check_and_restore()

if cache_restored:
    print(f"🚀 Build läuft mit LDF-Build-Cache - LDF übersprungen!")
    
    if not verify_ldf_data_completeness():
        print(f"⚠️  LDF-Build-Daten unvollständig")

else:
    print(f"📝 Führe normalen LDF-Durchlauf durch...")
    
    def post_build_cache_creation(source, target, env):
        """Post-Build: Erstelle LDF-Build-Cache"""
        print(f"\n🔄 Post-Build: Erstelle LDF-Build-Cache...")
        
        ldf_build_data = capture_ldf_build_data_only()
        
        if len(ldf_build_data) > 3:  # Mindestens CPPPATH, CPPDEFINES, BUILD_FLAGS
            env_name = env.get("PIOENV")
            if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                print(f"✓ lib_ldf_mode = off für nächsten Build gesetzt")
            
            if save_ldf_build_cache(ldf_build_data):
                print(f"\n📊 LDF-Build-Cache erfolgreich erstellt:")
                print(f"   📊 Build-Variablen: {len(ldf_build_data)}")
                print(f"   🚫 Tools/Toolchain: Nicht gecacht (PlatformIO verwaltet das)")
                print(f"\n💡 Führen Sie 'pio run' erneut aus für optimierten Build")
                print(f"   Nächster Build überspringt LDF-Scan!")
            else:
                print(f"⚠ Fehler beim Erstellen des LDF-Build-Cache")
        else:
            print(f"⚠ Unvollständige LDF-Build-Daten erfasst")
    
    env.AddPostAction("buildprog", post_build_cache_creation)

print(f"🏁 LDF-Optimierung (Build-Daten ohne Tools) Setup abgeschlossen")
print(f"💡 Tipp: Löschen Sie '.pio/ldf_cache/' um den Cache zurückzusetzen\n")
