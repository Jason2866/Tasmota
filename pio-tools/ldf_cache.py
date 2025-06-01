Import("env")
import os
import json
import hashlib
import configparser
import shutil
import glob
import re

def get_cache_file_path():
    """Generiert Pfad zur LDF-Cache-Datei für das aktuelle Environment"""
    env_name = env.get("PIOENV")
    project_dir = env.get("PROJECT_DIR")
    cache_dir = os.path.join(project_dir, ".pio", "ldf_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{env_name}_ldf_complete.json")

def find_all_platformio_files():
    """Findet alle platformio*.ini Dateien im Projekt"""
    project_dir = env.get("PROJECT_DIR")
    
    ini_patterns = ['platformio.ini', 'platformio_*.ini']
    ini_files = []
    for pattern in ini_patterns:
        found_files = glob.glob(os.path.join(project_dir, pattern))
        ini_files.extend(found_files)
    
    ini_files = list(set(ini_files))
    
    def sort_priority(filepath):
        filename = os.path.basename(filepath).lower()
        if filename == 'platformio.ini':
            return 0
        elif 'env' in filename and 'override' not in filename:
            return 1
        elif 'cenv' in filename:
            return 2
        elif 'override' in filename:
            return 3
        else:
            return 4
    
    ini_files.sort(key=sort_priority)
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
                print(f"✓ Environment [{section_name}] gefunden in: {os.path.basename(ini_file)}")
                return ini_file
                
        except Exception as e:
            print(f"⚠ Fehler beim Lesen von {os.path.basename(ini_file)}: {e}")
            continue
    
    print(f"⚠ Environment [env:{env_name}] nicht in PlatformIO-Dateien gefunden")
    return None

def backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
    """Findet und modifiziert die korrekte platformio*.ini Datei"""
    env_file = find_env_definition_file(env_name)
    
    if not env_file:
        print(f"⚠ Environment {env_name} nicht gefunden - verwende platformio.ini")
        project_dir = env.get("PROJECT_DIR")
        env_file = os.path.join(project_dir, "platformio.ini")
    
    if not os.path.exists(env_file):
        print(f"⚠ Datei nicht gefunden: {env_file}")
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
            print(f"⚠ Sektion [env:{env_name}] nicht in {os.path.basename(env_file)} gefunden")
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
                    
        except Exception as e:
            print(f"⚠ Fehler beim Lesen von {os.path.basename(ini_file)}: {e}")
            continue
    
    section_name = f"env:{env_name}"
    if merged_config.has_section(section_name):
        if merged_config.has_option(section_name, 'lib_ldf_mode'):
            mode = merged_config.get(section_name, 'lib_ldf_mode')
            return mode
    
    if merged_config.has_section('env'):
        if merged_config.has_option('env', 'lib_ldf_mode'):
            mode = merged_config.get('env', 'lib_ldf_mode')
            return mode
    
    return 'chain'

def normalize_path_list(path_list):
    """Normalisiert Pfad-Listen für konsistente Speicherung"""
    if not path_list:
        return []
    
    normalized = []
    for path in path_list:
        if isinstance(path, str):
            # Normalisiere Pfade für plattformübergreifende Kompatibilität
            norm_path = os.path.normpath(path).replace('\\', '/')
            normalized.append(norm_path)
        else:
            normalized.append(str(path))
    
    return sorted(list(set(normalized)))

def capture_complete_ldf_environment():
    """Erfasst ALLE vom LDF generierten Build-Environment-Daten"""
    print(f"🔍 Erfasse vollständige LDF-Environment-Daten...")
    
    # Alle kritischen Environment-Variablen erfassen
    ldf_environment = {
        # Library-bezogene Variablen
        "LIBS": env.get("LIBS", []),
        "LIBPATH": normalize_path_list(env.get("LIBPATH", [])),
        "LIB_DEPS": env.get("LIB_DEPS", []),
        "LIB_IGNORE": env.get("LIB_IGNORE", []),
        
        # Include-Pfade und Preprocessor
        "CPPPATH": normalize_path_list(env.get("CPPPATH", [])),
        "CPPDEFINES": env.get("CPPDEFINES", []),
        
        # Build-Flags
        "BUILD_FLAGS": env.get("BUILD_FLAGS", []),
        "CCFLAGS": env.get("CCFLAGS", []),
        "CXXFLAGS": env.get("CXXFLAGS", []),
        "LINKFLAGS": env.get("LINKFLAGS", []),
        
        # Framework und Platform
        "FRAMEWORK_DIR": env.get("FRAMEWORK_DIR", ""),
        "PLATFORM_DIR": env.get("PLATFORM_DIR", ""),
        "PLATFORM_PACKAGES": env.get("PLATFORM_PACKAGES", {}),
        
        # Compiler-Konfiguration
        "CC": env.get("CC", ""),
        "CXX": env.get("CXX", ""),
        "AR": env.get("AR", ""),
        "RANLIB": env.get("RANLIB", ""),
        
        # Source-Filter
        "SRC_FILTER": env.get("SRC_FILTER", ""),
        "SRC_BUILD_FLAGS": env.get("SRC_BUILD_FLAGS", []),
        
        # Upload-Konfiguration
        "UPLOAD_PROTOCOL": env.get("UPLOAD_PROTOCOL", ""),
        "UPLOAD_PORT": env.get("UPLOAD_PORT", ""),
        
        # Board-spezifische Einstellungen
        "BOARD": env.get("BOARD", ""),
        "BOARD_MCU": env.get("BOARD_MCU", ""),
        "BOARD_F_CPU": env.get("BOARD_F_CPU", ""),
        "BOARD_F_FLASH": env.get("BOARD_F_FLASH", ""),
        "BOARD_FLASH_MODE": env.get("BOARD_FLASH_MODE", ""),
    }
    
    # Zusätzliche Pfad-Analyse für Libraries
    active_lib_paths = []
    for path in env.get("CPPPATH", []):
        path_str = str(path)
        if any(keyword in path_str.lower() for keyword in ["lib", "libraries", "framework"]):
            active_lib_paths.append(path_str)
    
    ldf_environment["active_lib_paths"] = normalize_path_list(active_lib_paths)
    
    # Erfasse verfügbare lokale Libraries
    project_dir = env.get("PROJECT_DIR")
    lib_dir = os.path.join(project_dir, "lib")
    available_local_libs = []
    
    if os.path.exists(lib_dir):
        for item in os.listdir(lib_dir):
            lib_path = os.path.join(lib_dir, item)
            if os.path.isdir(lib_path):
                # Prüfe ob es eine gültige Library ist
                has_code = False
                for root, dirs, files in os.walk(lib_path):
                    if any(f.endswith(('.h', '.hpp', '.cpp', '.c', '.ino')) for f in files):
                        has_code = True
                        break
                
                if has_code:
                    available_local_libs.append(item)
    
    ldf_environment["available_local_libs"] = sorted(available_local_libs)
    
    # Debug-Ausgabe
    critical_counts = {
        "LIBS": len(ldf_environment.get("LIBS", [])),
        "LIBPATH": len(ldf_environment.get("LIBPATH", [])),
        "CPPPATH": len(ldf_environment.get("CPPPATH", [])),
        "BUILD_FLAGS": len(ldf_environment.get("BUILD_FLAGS", [])),
        "LIB_DEPS": len(ldf_environment.get("LIB_DEPS", [])),
        "active_lib_paths": len(ldf_environment.get("active_lib_paths", []))
    }
    
    print(f"📊 LDF-Environment erfasst:")
    for key, count in critical_counts.items():
        print(f"   {key}: {count} Einträge")
    
    return ldf_environment

def restore_complete_ldf_environment(cached_data):
    """Stellt ALLE LDF-Environment-Daten vollständig wieder her"""
    print(f"🔄 Stelle vollständige LDF-Environment wieder her...")
    
    # Kritische Environment-Variablen in der richtigen Reihenfolge setzen
    restoration_order = [
        "FRAMEWORK_DIR", "PLATFORM_DIR", "PLATFORM_PACKAGES",
        "BOARD", "BOARD_MCU", "BOARD_F_CPU", "BOARD_F_FLASH", "BOARD_FLASH_MODE",
        "CC", "CXX", "AR", "RANLIB",
        "CPPPATH", "LIBPATH", "LIBS",
        "CPPDEFINES", "BUILD_FLAGS", "CCFLAGS", "CXXFLAGS", "LINKFLAGS",
        "LIB_DEPS", "LIB_IGNORE",
        "SRC_FILTER", "SRC_BUILD_FLAGS",
        "UPLOAD_PROTOCOL", "UPLOAD_PORT"
    ]
    
    restored_count = 0
    
    for var_name in restoration_order:
        if var_name in cached_data and cached_data[var_name]:
            cached_value = cached_data[var_name]
            
            # Spezielle Behandlung für verschiedene Datentypen
            if var_name in ["CPPPATH", "LIBPATH", "active_lib_paths"]:
                # Pfad-Listen: Merge mit existierenden Pfaden
                current_paths = env.get(var_name, [])
                if isinstance(current_paths, str):
                    current_paths = [current_paths]
                
                # Kombiniere und dedupliziere
                all_paths = list(current_paths) + list(cached_value)
                unique_paths = []
                seen = set()
                for path in all_paths:
                    norm_path = os.path.normpath(str(path))
                    if norm_path not in seen:
                        seen.add(norm_path)
                        unique_paths.append(path)
                
                env.Replace(**{var_name: unique_paths})
                
            elif var_name in ["BUILD_FLAGS", "CCFLAGS", "CXXFLAGS", "LINKFLAGS", "LIB_DEPS"]:
                # Flag-Listen: Merge mit existierenden Flags
                current_flags = env.get(var_name, [])
                if isinstance(current_flags, str):
                    current_flags = [current_flags]
                
                all_flags = list(current_flags) + list(cached_value)
                unique_flags = list(dict.fromkeys(all_flags))  # Preserve order, remove duplicates
                
                env.Replace(**{var_name: unique_flags})
                
            else:
                # Direkte Zuweisung für andere Variablen
                env.Replace(**{var_name: cached_value})
            
            restored_count += 1
            
            # Debug-Ausgabe für wichtige Variablen
            if var_name in ["LIBS", "LIBPATH", "CPPPATH", "BUILD_FLAGS"]:
                value_count = len(cached_value) if isinstance(cached_value, (list, dict)) else 1
                print(f"   ✓ {var_name}: {value_count} Einträge wiederhergestellt")
    
    print(f"✅ {restored_count} Environment-Variablen wiederhergestellt")
    
    # Zusätzliche Validierung
    verify_environment_completeness()
    
    return True

def verify_environment_completeness():
    """Prüft ob alle notwendigen Build-Komponenten verfügbar sind"""
    critical_checks = {
        "Framework verfügbar": bool(env.get("FRAMEWORK_DIR")),
        "Libraries gefunden": len(env.get("LIBS", [])) > 0 or len(env.get("LIB_DEPS", [])) > 0,
        "Include-Pfade gesetzt": len(env.get("CPPPATH", [])) > 0,
        "Build-Flags vorhanden": len(env.get("BUILD_FLAGS", [])) > 0,
        "Compiler konfiguriert": bool(env.get("CC")) and bool(env.get("CXX")),
        "Board definiert": bool(env.get("BOARD"))
    }
    
    print(f"🔍 Environment-Verifikation:")
    all_ok = True
    for check, status in critical_checks.items():
        status_icon = "✅" if status else "❌"
        print(f"   {status_icon} {check}")
        if not status:
            all_ok = False
    
    if not all_ok:
        print(f"⚠️  Unvollständige Build-Environment erkannt!")
        print(f"💡 Tipp: Löschen Sie '.pio/ldf_cache/' und führen Sie einen Clean-Build durch")
        return False
    
    print(f"✅ Build-Environment vollständig - Compile sollte erfolgreich sein")
    return True

def calculate_final_config_hash():
    """Berechnet Hash NACH allen Konfigurationsänderungen"""
    relevant_values = [
        f"BOARD:{env.get('BOARD', '')}",
        f"PLATFORM:{env.get('PLATFORM', '')}",
        f"PIOENV:{env.get('PIOENV', '')}",
        f"BUILD_FLAGS:{str(sorted(env.get('BUILD_FLAGS', [])))}",
        f"LIB_DEPS:{str(sorted(env.get('LIB_DEPS', [])))}"
    ]
    
    # Lese AKTUELLE Konfiguration (nach Änderungen)
    ini_files = find_all_platformio_files()
    
    for ini_file in sorted(ini_files):
        if os.path.exists(ini_file) and not ini_file.endswith('.ldf_backup'):
            try:
                config = configparser.ConfigParser(allow_no_value=True)
                config.read(ini_file, encoding='utf-8')
                
                env_section = f"env:{env.get('PIOENV')}"
                if config.has_section(env_section):
                    relevant_options = ['board', 'platform', 'framework', 'build_flags', 'lib_deps', 'lib_ignore', 'lib_ldf_mode']
                    for option in relevant_options:
                        if config.has_option(env_section, option):
                            value = config.get(env_section, option)
                            relevant_values.append(f"{os.path.basename(ini_file)}:{option}:{value}")
            except Exception:
                pass
    
    relevant_values.sort()
    config_string = "|".join(relevant_values)
    hash_value = hashlib.md5(config_string.encode()).hexdigest()
    
    return hash_value

def save_complete_ldf_cache(ldf_environment):
    """Speichert vollständige LDF-Environment-Daten"""
    cache_file = get_cache_file_path()
    
    final_hash = calculate_final_config_hash()
    
    cache_data = {
        "config_hash": final_hash,
        "ldf_environment": ldf_environment,
        "env_name": env.get("PIOENV"),
        "cache_version": "2.0",
        "timestamp": str(env.get("BUILD_TIME", "unknown"))
    }
    
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
        
        env_vars_count = len([k for k, v in ldf_environment.items() if v])
        print(f"✓ Vollständiger LDF-Cache gespeichert: {env_vars_count} Environment-Variablen")
        return True
        
    except Exception as e:
        print(f"⚠ Fehler beim Speichern des LDF-Cache: {e}")
        return False

def load_complete_ldf_cache():
    """Lädt vollständigen LDF-Cache und vergleicht Hash"""
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        print(f"📝 Kein LDF-Cache gefunden - erster Build-Durchlauf")
        return None
    
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        # Prüfe Cache-Version
        cache_version = cache_data.get("cache_version", "1.0")
        if cache_version != "2.0":
            print(f"⚠ Veraltete Cache-Version ({cache_version}) - wird ignoriert")
            return None
        
        # Hash-Vergleich
        current_hash = calculate_final_config_hash()
        cached_hash = cache_data.get("config_hash")
        
        if cached_hash == current_hash:
            ldf_environment = cache_data.get("ldf_environment")
            if ldf_environment:
                env_vars_count = len([k for k, v in ldf_environment.items() if v])
                print(f"✓ Vollständiger LDF-Cache geladen: {env_vars_count} Environment-Variablen")
                return ldf_environment
        else:
            print(f"⚠ LDF-Cache ungültig - Konfiguration hat sich geändert")
            print(f"  Aktueller Hash: {current_hash[:8]}...")
            print(f"  Gecachter Hash: {cached_hash[:8] if cached_hash else 'None'}...")
            
    except (json.JSONDecodeError, KeyError) as e:
        print(f"⚠ LDF-Cache beschädigt: {e}")
    
    return None

# =============================================================================
# HAUPTLOGIK - VOLLSTÄNDIGE LDF-ENVIRONMENT-WIEDERHERSTELLUNG
# =============================================================================

print(f"\n🚀 Tasmota LDF-Optimierung für Environment: {env.get('PIOENV')}")

env_name = env.get("PIOENV")
current_ldf_mode = get_current_ldf_mode(env_name)
print(f"📊 Aktueller LDF-Modus: {current_ldf_mode}")

# Lade vollständigen LDF-Cache
cached_ldf_environment = load_complete_ldf_cache()

if cached_ldf_environment and current_ldf_mode == 'off':
    # Cache verfügbar UND LDF deaktiviert - vollständige Environment-Wiederherstellung
    print(f"⚡ LDF-Cache verfügbar - stelle vollständige Build-Environment wieder her")
    
    if restore_complete_ldf_environment(cached_ldf_environment):
        print(f"✅ Build-Environment vollständig wiederhergestellt - optimierter Build läuft")
    else:
        print(f"⚠ Fehler bei Environment-Wiederherstellung - Build könnte fehlschlagen")

else:
    # Kein Cache oder LDF noch aktiv - sammle vollständige Environment-Daten
    if cached_ldf_environment:
        print(f"🔄 LDF-Cache vorhanden aber LDF noch aktiv - sammle aktualisierte Daten")
    else:
        print(f"📝 Erster Build-Durchlauf - sammle vollständige LDF-Environment-Daten")
    
    def complete_post_build_action(source, target, env):
        """SCons Post-Action: Sammle ALLE LDF-Environment-Daten"""
        print(f"\n🔄 Post-Build: Sammle vollständige LDF-Environment-Daten...")
        
        # Erfasse vollständige LDF-Environment
        ldf_environment = capture_complete_ldf_environment()
        
        if ldf_environment and len([k for k, v in ldf_environment.items() if v]) > 10:
            # Setze lib_ldf_mode = off für nächsten Build
            env_name = env.get("PIOENV")
            if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                print(f"✓ lib_ldf_mode = off für nächsten Build gesetzt")
            
            # Speichere vollständige Environment-Daten
            if save_complete_ldf_cache(ldf_environment):
                print(f"📊 LDF-Environment-Analyse erfolgreich abgeschlossen")
                print(f"\n💡 Führen Sie 'pio run' erneut aus für optimierten Build")
                print(f"   Nächster Build wird alle Dependencies aus dem Cache laden")
                print(f"   und den LDF-Scanner komplett überspringen")
            else:
                print(f"⚠ Fehler beim Speichern der Environment-Daten")
        else:
            print(f"⚠ Unvollständige LDF-Environment-Daten erfasst")
    
    # Registriere SCons Post-Action
    env.AddPostAction("buildprog", complete_post_build_action)

print(f"🏁 LDF-Optimierung Setup abgeschlossen für {env_name}")
print(f"💡 Tipp: Löschen Sie '.pio/ldf_cache/' um den Cache zurückzusetzen\n")
