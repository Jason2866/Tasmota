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
    return os.path.join(cache_dir, f"{env_name}_ldf_complete.pkl.gz")

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
            if i > 500:  # Erhöht für vollständige Erfassung
                break
            converted.append(safe_convert_for_pickle(item, max_depth, current_depth + 1))
        return converted
    elif isinstance(obj, dict):
        converted = {}
        for key, value in obj.items():
            if len(converted) > 200:  # Erhöht für vollständige Erfassung
                break
            safe_key = str(key)
            converted[safe_key] = safe_convert_for_pickle(value, max_depth, current_depth + 1)
        return converted
    else:
        return str(obj)

def capture_complete_ldf_data():
    """Erfasst ALLE LDF-generierten Datenstrukturen (vollständige Analyse)"""
    print(f"🔍 Erfasse ALLE LDF-generierten Datenstrukturen...")
    
    # VOLLSTÄNDIGE LDF-Variable-Liste (basierend auf PlatformIO-Dokumentation)
    complete_ldf_vars = [
        # === PRIMÄRE LDF-AUSGABEN ===
        "CPPPATH",                  # Alle Include-Verzeichnisse
        "CPPDEFINES",               # Preprocessor-Defines (LDF-evaluiert)
        "LIBPATH",                  # Library-Suchpfade
        "LIBS",                     # Gefundene Libraries
        "LIBSOURCE_DIRS",           # Library-Source-Verzeichnisse
        "PIOBUILDFILES",            # ALLE analysierten Source-Dateien
        "SRC_FILTER",               # Angewendete Source-Filter
        
        # === LDF-KONFIGURATION ===
        "LIB_LDF_MODE",             # Aktueller LDF-Modus
        "LIB_DEPS",                 # Aufgelöste Library-Dependencies
        "LIB_IGNORE",               # Ignorierte Libraries
        "LIB_EXTRA_DIRS",           # Extra Library-Verzeichnisse
        "LIB_COMPAT_MODE",          # Library-Kompatibilitätsmodus
        "LIB_FORCE",                # Erzwungene Libraries
        "LIB_ARCHIVE",              # Library-Archive
        
        # === PLATFORMIO-VERZEICHNISSE ===
        "PROJECT_DIR",              # Projekt-Root
        "PROJECT_SRC_DIR",          # Source-Verzeichnis
        "PROJECT_LIB_DIR",          # Lokales lib/ Verzeichnis
        "PROJECT_LIBDEPS_DIR",      # .pio/libdeps/{env}/
        "PROJECT_INCLUDE_DIR",      # Include-Verzeichnis
        "PROJECT_BUILD_DIR",        # Build-Verzeichnis
        "PROJECT_DATA_DIR",         # Data-Verzeichnis
        "PLATFORMIO_CORE_DIR",      # PlatformIO-Core
        "PLATFORMIO_GLOBALLIB_DIR", # Globale Libraries
        "PLATFORMIO_PACKAGES_DIR",  # Packages
        "PLATFORMIO_LIBDEPS_DIR",   # Global LibDeps
        
        # === BUILD-FLAGS (LDF-beeinflusst) ===
        "BUILD_FLAGS",              # Haupt-Build-Flags
        "CCFLAGS",                  # C-Compiler-Flags
        "CXXFLAGS",                 # C++-Compiler-Flags
        "LINKFLAGS",                # Linker-Flags
        "ASFLAGS",                  # Assembler-Flags
        "ASPPFLAGS",                # Assembler-Preprocessor-Flags
        
        # === FRAMEWORK-SPEZIFISCH ===
        "ARDUINO_FRAMEWORK_DIR",    # Arduino-Framework-Pfad
        "ARDUINO_CORE_DIR",         # Arduino-Core-Verzeichnis
        "ARDUINO_VARIANT_DIR",      # Board-Variant-Verzeichnis
        "ARDUINO_LIB_DIRS",         # Arduino-Library-Verzeichnisse
        "BOARD",                    # Board-Typ
        "BOARD_MCU",                # MCU-Typ
        "BOARD_F_CPU",              # CPU-Frequenz
        "BOARD_F_FLASH",            # Flash-Frequenz
        "PLATFORM",                 # Platform-Name
        "FRAMEWORK",                # Framework-Name
        
        # === ZUSÄTZLICHE BUILD-DATEN ===
        "EXTRA_LIB_DIRS",           # Extra Library-Verzeichnisse
        "BUILD_SRC_FILTER",         # Build-Source-Filter
        "BUILDSRC_DIR",             # Build-Source-Verzeichnis
        "BUILD_DIR",                # Build-Verzeichnis
        "LIBDEPS_DIR",              # LibDeps-Verzeichnis
        
        # === ERWEITERTE LDF-DATEN ===
        "LIB_BUILTIN",              # Built-in Libraries
        "ARDUINO_LIBS",             # Arduino-spezifische Libraries
        "FRAMEWORK_ARDUINOESPRESSIF32_LIB_BUILDERS"  # ESP32-Builder
    ]
    
    ldf_data = {}
    found_count = 0
    
    for var in complete_ldf_vars:
        if var in env:
            original_value = env[var]
            
            try:
                converted_value = safe_convert_for_pickle(original_value)
                ldf_data[var] = converted_value
                found_count += 1
                
                # Detaillierte Debug-Ausgabe für kritische Variablen
                if var == "CPPPATH" and hasattr(converted_value, '__len__'):
                    print(f"   ✓ {var}: {len(converted_value)} Include-Pfade")
                    # Prüfe speziell auf lib/default/headers
                    project_dir = env.get("PROJECT_DIR")
                    lib_default = os.path.join(project_dir, "lib", "default", "headers")
                    found_lib_default = any(lib_default in str(path) for path in converted_value)
                    if found_lib_default:
                        print(f"      ✅ lib/default/headers gefunden!")
                    else:
                        print(f"      ⚠️  lib/default/headers NICHT gefunden")
                elif var in ["PROJECT_LIB_DIR", "PROJECT_LIBDEPS_DIR", "LIBDEPS_DIR"]:
                    print(f"   ✓ {var}: {converted_value}")
                elif var == "PIOBUILDFILES" and hasattr(converted_value, '__len__'):
                    print(f"   ✓ {var}: {len(converted_value)} Source-Dateien")
                elif var == "LIB_EXTRA_DIRS" and hasattr(converted_value, '__len__'):
                    print(f"   ✓ {var}: {len(converted_value)} Extra-Verzeichnisse")
                elif hasattr(converted_value, '__len__') and not isinstance(converted_value, str):
                    print(f"   ✓ {var}: {len(converted_value)} Elemente")
                else:
                    print(f"   ✓ {var}: Erfasst")
                        
            except Exception as e:
                print(f"   ⚠ {var}: Fehler - {e}")
                ldf_data[var] = str(original_value)[:500]
        else:
            print(f"   - {var}: Nicht vorhanden")
    
    print(f"✅ {found_count}/{len(complete_ldf_vars)} LDF-Variablen erfasst")
    return ldf_data

def early_cache_check_and_restore():
    """Prüft Cache und stellt ALLE LDF-Daten wieder her"""
    print(f"🔍 Cache-Prüfung (VOLLSTÄNDIGE LDF-Daten)...")
    
    cached_data = load_ldf_cache()
    
    if not cached_data:
        print(f"📝 Kein Cache - LDF wird normal ausgeführt")
        return False
    
    current_ldf_mode = get_current_ldf_mode(env.get("PIOENV"))
    
    if current_ldf_mode != 'off':
        print(f"🔄 LDF noch aktiv - Cache wird nach Build erstellt")
        return False
    
    print(f"⚡ Cache verfügbar - stelle ALLE LDF-Daten wieder her")
    
    # ALLE LDF-Daten wiederherstellen
    restored_count = 0
    
    for var_name, cached_value in cached_data.items():
        if var_name.startswith('_'):
            continue  # Skip Metadaten
            
        try:
            # Direkte Zuweisung ALLER LDF-Daten
            env[var_name] = cached_value
            restored_count += 1
            
            # Debug-Ausgabe für kritische Variablen
            if var_name == "CPPPATH" and hasattr(cached_value, '__len__'):
                print(f"   ✓ {var_name}: {len(cached_value)} Include-Pfade")
                # Prüfe lib/default/headers
                project_dir = env.get("PROJECT_DIR")
                lib_default = os.path.join(project_dir, "lib", "default", "headers")
                found_lib_default = any(lib_default in str(path) for path in cached_value)
                if found_lib_default:
                    print(f"      ✅ lib/default/headers wiederhergestellt!")
            elif var_name in ["PROJECT_LIB_DIR", "PROJECT_LIBDEPS_DIR", "LIBDEPS_DIR"]:
                print(f"   ✓ {var_name}: {cached_value}")
            elif var_name == "PIOBUILDFILES" and hasattr(cached_value, '__len__'):
                print(f"   ✓ {var_name}: {len(cached_value)} Source-Dateien")
            elif hasattr(cached_value, '__len__') and not isinstance(cached_value, str):
                print(f"   ✓ {var_name}: {len(cached_value)} Elemente")
            else:
                print(f"   ✓ {var_name}: OK")
                
        except Exception as e:
            print(f"   ⚠ {var_name}: Fehler - {e}")
    
    print(f"✅ {restored_count} LDF-Variablen wiederhergestellt")
    return restored_count > 10  # Mindestens 10 kritische Variablen

def verify_complete_ldf_data():
    """Vollständige Verifikation ALLER LDF-Daten"""
    print(f"\n🔍 Vollständige LDF-Daten-Verifikation...")
    
    critical_vars = [
        "CPPPATH", 
        "CPPDEFINES", 
        "BUILD_FLAGS",
        "PROJECT_LIB_DIR",
        "PIOBUILDFILES",
        "LIB_EXTRA_DIRS"
    ]
    
    all_ok = True
    for var in critical_vars:
        if var in env and env[var]:
            if var == "CPPPATH":
                paths = env[var]
                print(f"   ✅ {var}: {len(paths)} Include-Pfade")
                
                # Spezielle Prüfung für lib/default/headers
                project_dir = env.get("PROJECT_DIR")
                lib_default = os.path.join(project_dir, "lib", "default", "headers")
                found = any(lib_default in str(path) for path in paths)
                
                if found:
                    print(f"      ✅ lib/default/headers: GEFUNDEN")
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
    
    if all_ok:
        print(f"✅ ALLE LDF-Daten vollständig verfügbar")
    else:
        print(f"❌ LDF-Daten UNVOLLSTÄNDIG - Build wird fehlschlagen")
    
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

def save_ldf_cache(ldf_data):
    """Speichert vollständigen LDF-Cache"""
    cache_file = get_cache_file_path()
    
    try:
        cache_dir = os.path.dirname(cache_file)
        os.makedirs(cache_dir, exist_ok=True)
        
        cache_data = {
            "config_hash": calculate_config_hash(),
            "env_name": env.get("PIOENV"),
            "cache_version": "6.0",  # Neue Version für vollständige LDF-Erfassung
            "_cache_type": "complete_ldf_data"
        }
        
        cache_data.update(ldf_data)
        
        with gzip.open(cache_file, 'wb') as f:
            pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        file_size = os.path.getsize(cache_file)
        
        print(f"✓ Vollständiger LDF-Cache gespeichert:")
        print(f"   📁 {os.path.basename(cache_file)} ({file_size} Bytes)")
        print(f"   📊 LDF-Variablen: {len(ldf_data)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Cache-Speicherfehler: {e}")
        return False

def load_ldf_cache():
    """Lädt vollständigen LDF-Cache"""
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        return None
    
    try:
        with gzip.open(cache_file, 'rb') as f:
            cache_data = pickle.load(f)
        
        cache_version = cache_data.get("cache_version", "1.0")
        if cache_version != "6.0":
            print(f"⚠ Veraltete Cache-Version {cache_version} - wird ignoriert")
            return None
        
        current_hash = calculate_config_hash()
        cached_hash = cache_data.get("config_hash")
        
        if cached_hash == current_hash:
            ldf_data = {k: v for k, v in cache_data.items() 
                       if not k.startswith('_') and k not in ['config_hash', 'env_name', 'cache_version']}
            return ldf_data
        else:
            print(f"⚠ Cache ungültig - Konfiguration geändert")
        
    except Exception as e:
        print(f"⚠ Cache-Ladefehler: {e}")
    
    return None

# =============================================================================
# HAUPTLOGIK - VOLLSTÄNDIGE LDF-DATEN CACHING
# =============================================================================

print(f"\n🚀 Tasmota LDF-Optimierung (VOLLSTÄNDIGE LDF-Erfassung) für: {env.get('PIOENV')}")

# Cache-Prüfung und vollständige Wiederherstellung
cache_restored = early_cache_check_and_restore()

if cache_restored:
    print(f"🚀 Build mit VOLLSTÄNDIGEM LDF-Cache - LDF übersprungen!")
    
    if not verify_complete_ldf_data():
        print(f"❌ KRITISCHER FEHLER: LDF-Daten unvollständig!")
        print(f"💡 Löschen Sie '.pio/ldf_cache/' und starten Sie neu")

else:
    print(f"📝 Normaler LDF-Durchlauf - erfasse ALLE LDF-Daten...")
    
    def post_build_complete_cache(source, target, env):
        """Post-Build: Vollständiger LDF-Cache"""
        print(f"\n🔄 Post-Build: Erstelle VOLLSTÄNDIGEN LDF-Cache...")
        
        complete_ldf_data = capture_complete_ldf_data()
        
        if len(complete_ldf_data) > 15:  # Mindestens 15 kritische Variablen
            env_name = env.get("PIOENV")
            if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                print(f"✓ lib_ldf_mode = off gesetzt")
            
            if save_ldf_cache(complete_ldf_data):
                print(f"\n📊 VOLLSTÄNDIGER LDF-Cache erstellt:")
                print(f"   📊 Variablen: {len(complete_ldf_data)}")
                print(f"   🎯 Erfasst: ALLE LDF-generierten Datenstrukturen")
                print(f"   🚀 Nächster Build: Komplett ohne LDF!")
            else:
                print(f"❌ Cache-Erstellung fehlgeschlagen")
        else:
            print(f"❌ Unvollständige LDF-Daten - Cache nicht erstellt")
    
    env.AddPostAction("buildprog", post_build_complete_cache)

print(f"🏁 VOLLSTÄNDIGE LDF-Optimierung initialisiert")
print(f"💡 Cache-Reset: rm -rf .pio/ldf_cache/\n")
