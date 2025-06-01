Import("env")
import os
import pickle
import gzip
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

def capture_complete_ldf_environment():
    """Erfasst ALLE vom LDF generierten Build-Environment-Daten (ohne Konvertierung)"""
    print(f"🔍 Erfasse vollständige LDF-Environment-Daten...")
    
    # Alle kritischen Environment-Variablen direkt erfassen (keine String-Konvertierung!)
    critical_vars = [
        "LIBS", "LIBPATH", "CPPPATH", "CPPDEFINES", 
        "BUILD_FLAGS", "CCFLAGS", "CXXFLAGS", "LINKFLAGS",
        "LIB_DEPS", "LIB_IGNORE", "FRAMEWORK_DIR", "PLATFORM_DIR",
        "PLATFORM_PACKAGES", "CC", "CXX", "AR", "RANLIB",
        "LIBSOURCE_DIRS", "EXTRA_LIB_DIRS", "PIOENV", 
        "BOARD", "PLATFORM", "FRAMEWORK"
    ]
    
    ldf_environment = {}
    
    for var in critical_vars:
        if var in env:
            value = env[var]
            ldf_environment[var] = value
            
            # Debug-Info über erfasste Daten
            if hasattr(value, '__len__') and not isinstance(value, str):
                print(f"   📊 {var}: {type(value).__name__} mit {len(value)} Elementen")
            else:
                print(f"   📊 {var}: {type(value).__name__}")
    
    # Zusätzliche Library-Pfad-Analyse
    lib_include_paths = []
    for path in env.get("CPPPATH", []):
        path_str = str(path)
        if any(keyword in path_str.lower() for keyword in ['lib', 'libraries', 'framework']):
            lib_include_paths.append(path)
    
    if lib_include_paths:
        ldf_environment["LIB_INCLUDE_PATHS"] = lib_include_paths
        print(f"   📊 LIB_INCLUDE_PATHS: {len(lib_include_paths)} Pfade")
    
    # Framework-spezifische Defines erfassen
    framework_defines = []
    for define in env.get("CPPDEFINES", []):
        define_str = str(define)
        if any(keyword in define_str.upper() for keyword in ['ARDUINO', 'ESP32', 'FRAMEWORK']):
            framework_defines.append(define)
    
    if framework_defines:
        ldf_environment["FRAMEWORK_DEFINES"] = framework_defines
        print(f"   📊 FRAMEWORK_DEFINES: {len(framework_defines)} Defines")
    
    print(f"✅ {len(ldf_environment)} Environment-Variablen erfasst")
    return ldf_environment

def restore_complete_ldf_environment(cached_env_data):
    """Stellt ALLE LDF-Environment-Daten vollständig wieder her"""
    print(f"🔄 Stelle vollständige LDF-Environment wieder her...")
    
    # Kritische Variablen die direkt gesetzt werden müssen
    critical_vars = [
        "LIBS", "LIBPATH", "CPPPATH", "CPPDEFINES", 
        "BUILD_FLAGS", "CCFLAGS", "CXXFLAGS", "LINKFLAGS",
        "LIB_DEPS", "LIB_IGNORE"
    ]
    
    restored_count = 0
    
    for var_name in critical_vars:
        if var_name in cached_env_data:
            cached_value = cached_env_data[var_name]
            
            try:
                # Direkte Zuweisung - keine Konvertierung!
                env[var_name] = cached_value
                restored_count += 1
                
                # Debug-Info
                if hasattr(cached_value, '__len__') and not isinstance(cached_value, str):
                    print(f"   ✓ {var_name}: {type(cached_value).__name__} mit {len(cached_value)} Elementen")
                else:
                    print(f"   ✓ {var_name}: {type(cached_value).__name__}")
                    
            except Exception as e:
                print(f"   ⚠ {var_name}: Fehler bei Wiederherstellung - {e}")
    
    # Framework-Verzeichnis explizit setzen
    if "FRAMEWORK_DIR" in cached_env_data and cached_env_data["FRAMEWORK_DIR"]:
        env["FRAMEWORK_DIR"] = cached_env_data["FRAMEWORK_DIR"]
        print(f"   ✓ FRAMEWORK_DIR: {cached_env_data['FRAMEWORK_DIR']}")
    
    # Platform-Verzeichnis setzen
    if "PLATFORM_DIR" in cached_env_data and cached_env_data["PLATFORM_DIR"]:
        env["PLATFORM_DIR"] = cached_env_data["PLATFORM_DIR"]
        print(f"   ✓ PLATFORM_DIR: {cached_env_data['PLATFORM_DIR']}")
    
    # Compiler-Pfade setzen
    compiler_vars = ["CC", "CXX", "AR", "RANLIB"]
    for var in compiler_vars:
        if var in cached_env_data and cached_env_data[var]:
            env[var] = cached_env_data[var]
            print(f"   ✓ {var}: {cached_env_data[var]}")
    
    print(f"✅ {restored_count} kritische Environment-Variablen wiederhergestellt")
    return True

def verify_environment_completeness():
    """Prüft ob alle notwendigen Build-Komponenten verfügbar sind"""
    print(f"\n🔍 Verifikation der Build-Environment...")
    
    critical_checks = {
        "Framework verfügbar": bool(env.get("FRAMEWORK_DIR")),
        "Libraries gefunden": len(env.get("LIBS", [])) > 0,
        "Include-Pfade gesetzt": len(env.get("CPPPATH", [])) > 5,
        "Build-Flags vorhanden": len(env.get("BUILD_FLAGS", [])) > 0,
        "Library-Pfade gesetzt": len(env.get("LIBPATH", [])) > 0,
        "Defines gesetzt": len(env.get("CPPDEFINES", [])) > 0,
        "Compiler konfiguriert": bool(env.get("CC")) and bool(env.get("CXX"))
    }
    
    all_ok = True
    for check, status in critical_checks.items():
        status_icon = "✅" if status else "❌"
        print(f"   {status_icon} {check}")
        if not status:
            all_ok = False
    
    if all_ok:
        print(f"✅ Build-Environment vollständig - Compile sollte erfolgreich sein")
    else:
        print(f"⚠️  Unvollständige Build-Environment - mögliche Compile-Fehler")
    
    return all_ok

def calculate_final_config_hash():
    """Berechnet Hash NACH allen Konfigurationsänderungen"""
    relevant_values = [
        f"BOARD:{env.get('BOARD', '')}",
        f"PLATFORM:{env.get('PLATFORM', '')}",
        f"PIOENV:{env.get('PIOENV', '')}",
        f"BUILD_FLAGS:{str(sorted([str(f) for f in env.get('BUILD_FLAGS', [])]))}", 
        f"LIB_DEPS:{str(sorted([str(d) for d in env.get('LIB_DEPS', [])]))}"
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
    
    print(f"🔍 Finaler Hash: {hash_value[:8]}...")
    return hash_value

def save_complete_ldf_cache(ldf_environment):
    """Speichert vollständige LDF-Environment-Daten mit Pickle (komprimiert)"""
    cache_file = get_cache_file_path()
    
    try:
        # Prüfe und erstelle Verzeichnis
        cache_dir = os.path.dirname(cache_file)
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
            print(f"✓ Cache-Verzeichnis erstellt: {cache_dir}")
        
        final_hash = calculate_final_config_hash()
        
        cache_data = {
            "config_hash": final_hash,
            "ldf_environment": ldf_environment,  # Originale SCons-Objekte!
            "env_name": env.get("PIOENV"),
            "cache_version": "2.0"
        }
        
        # Komprimiert mit Pickle speichern
        with gzip.open(cache_file, 'wb') as f:
            pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        # Statistiken
        env_var_count = len(ldf_environment)
        lib_count = len(ldf_environment.get("LIBS", []))
        path_count = len(ldf_environment.get("CPPPATH", []))
        
        print(f"✓ LDF-Cache (Pickle) erfolgreich gespeichert:")
        print(f"   📁 Datei: {os.path.basename(cache_file)}")
        print(f"   📊 Environment-Variablen: {env_var_count}")
        print(f"   📚 Libraries: {lib_count}")
        print(f"   📂 Include-Pfade: {path_count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Pickle-Speicherfehler: {e}")
        print(f"   Cache-Datei: {cache_file}")
        return False

def load_complete_ldf_cache():
    """Lädt vollständige LDF-Cache-Daten mit Pickle"""
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        print(f"📝 Kein LDF-Cache gefunden - erster Durchlauf")
        return None
    
    try:
        with gzip.open(cache_file, 'rb') as f:
            cache_data = pickle.load(f)
        
        # Prüfe Cache-Version
        cache_version = cache_data.get("cache_version", "1.0")
        if cache_version != "2.0":
            print(f"⚠ Veraltete Cache-Version {cache_version} - wird ignoriert")
            return None
        
        # Hash-Vergleich
        current_hash = calculate_final_config_hash()
        cached_hash = cache_data.get("config_hash")
        
        if cached_hash == current_hash:
            ldf_environment = cache_data.get("ldf_environment")
            if ldf_environment:
                env_var_count = len(ldf_environment)
                lib_count = len(ldf_environment.get("LIBS", []))
                path_count = len(ldf_environment.get("CPPPATH", []))
                
                print(f"✓ LDF-Cache (Pickle) erfolgreich geladen:")
                print(f"   📊 Environment-Variablen: {env_var_count}")
                print(f"   📚 Libraries: {lib_count}")
                print(f"   📂 Include-Pfade: {path_count}")
                
                return ldf_environment
        else:
            print(f"⚠ LDF-Cache ungültig - Hash-Mismatch")
            print(f"  Aktueller Hash: {current_hash[:8]}...")
            print(f"  Gecachter Hash: {cached_hash[:8] if cached_hash else 'None'}...")
            
    except Exception as e:
        print(f"⚠ Pickle-Ladefehler: {e}")
        print(f"   Cache-Datei: {cache_file}")
    
    return None

# =============================================================================
# HAUPTLOGIK - VOLLSTÄNDIGE LDF-ENVIRONMENT-WIEDERHERSTELLUNG MIT PICKLE
# =============================================================================

print(f"\n🚀 Tasmota LDF-Optimierung für Environment: {env.get('PIOENV')}")

env_name = env.get("PIOENV")
current_ldf_mode = get_current_ldf_mode(env_name)
print(f"📊 Aktueller LDF-Modus: {current_ldf_mode}")

cached_ldf_env = load_complete_ldf_cache()

# Prüfe ob vollständiger Cache verfügbar ist
cache_is_complete = (cached_ldf_env is not None and 
                    cached_ldf_env.get("LIBS") is not None and 
                    cached_ldf_env.get("CPPPATH") is not None and
                    len(cached_ldf_env.get("CPPPATH", [])) > 0)

if cache_is_complete and current_ldf_mode == 'off':
    # Cache ist vollständig UND LDF bereits deaktiviert
    print(f"⚡ LDF-Cache verfügbar - stelle Build-Environment wieder her")
    
    # Vollständige Environment-Wiederherstellung
    if restore_complete_ldf_environment(cached_ldf_env):
        # Verifikation der wiederhergestellten Environment
        verify_environment_completeness()
        print(f"🚀 Build läuft mit wiederhergestellter LDF-Environment - optimiert!")
    else:
        print(f"⚠ Fehler bei Environment-Wiederherstellung - LDF läuft normal")

else:
    # Kein vollständiger Cache ODER LDF noch nicht deaktiviert
    if cached_ldf_env:
        print(f"🔄 LDF-Cache vorhanden aber LDF noch aktiv - sammle aktualisierte Daten")
    else:
        print(f"📝 Erster Build-Durchlauf - sammle vollständige LDF-Environment-Daten")
    
    def complete_post_build_action(source, target, env):
        """SCons Post-Action: Erfasse ALLE LDF-Daten mit Pickle"""
        print(f"\n🔄 Post-Build: Erfasse vollständige LDF-Environment (Pickle)...")
        
        # Erfasse ALLE LDF-Environment-Daten (originale SCons-Objekte!)
        complete_ldf_env = capture_complete_ldf_environment()
        
        if len(complete_ldf_env.get("CPPPATH", [])) > 0:
            # Setze lib_ldf_mode = off für nächsten Build
            env_name = env.get("PIOENV")
            if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                print(f"✓ lib_ldf_mode = off für nächsten Build gesetzt")
            
            # Speichere vollständige Environment-Daten mit Pickle
            if save_complete_ldf_cache(complete_ldf_env):
                lib_count = len(complete_ldf_env.get("LIBS", []))
                path_count = len(complete_ldf_env.get("CPPPATH", []))
                define_count = len(complete_ldf_env.get("CPPDEFINES", []))
                
                print(f"\n📊 LDF-Environment erfolgreich erfasst:")
                print(f"   📚 Libraries: {lib_count}")
                print(f"   📂 Include-Pfade: {path_count}")
                print(f"   🏷️  Defines: {define_count}")
                print(f"   🔧 Framework: {complete_ldf_env.get('FRAMEWORK_DIR', 'N/A')}")
                
                print(f"\n💡 Führen Sie 'pio run' erneut aus für optimierten Build")
                print(f"   Nächster Build verwendet gespeicherte LDF-Environment (Pickle)")
            else:
                print(f"⚠ Fehler beim Speichern der LDF-Environment")
        else:
            print(f"⚠ Unvollständige LDF-Environment erfasst")
    
    # Registriere SCons Post-Action
    env.AddPostAction("buildprog", complete_post_build_action)

print(f"🏁 LDF-Optimierung Setup abgeschlossen für {env_name}")
print(f"💡 Tipp: Löschen Sie '.pio/ldf_cache/' um den Cache zurückzusetzen\n")
