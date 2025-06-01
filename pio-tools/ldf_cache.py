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

def normalize_and_validate_path(path, project_dir):
    """Normalisiert und validiert Pfade für Cache-Speicherung"""
    if not path:
        return None
    
    path_str = str(path)
    normalized = os.path.normpath(path_str)
    
    # Konvertiere zu relativem Pfad wenn innerhalb des Projekts
    try:
        if normalized.startswith(project_dir):
            relative_path = os.path.relpath(normalized, project_dir)
            return {
                'type': 'relative',
                'path': relative_path,
                'original': normalized
            }
    except:
        pass
    
    # Prüfe ob Pfad existiert
    if os.path.exists(normalized):
        return {
            'type': 'absolute',
            'path': normalized,
            'exists': True
        }
    else:
        return {
            'type': 'absolute',
            'path': normalized,
            'exists': False
        }

def restore_validated_path(path_data, project_dir):
    """Stellt Pfade sicher wieder her"""
    if not path_data or not isinstance(path_data, dict):
        return str(path_data) if path_data else None
    
    if path_data.get('type') == 'relative':
        restored_path = os.path.join(project_dir, path_data['path'])
        if os.path.exists(restored_path):
            return restored_path
        elif os.path.exists(path_data.get('original', '')):
            return path_data['original']
    
    elif path_data.get('type') == 'absolute':
        if os.path.exists(path_data['path']):
            return path_data['path']
    
    return None

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
        except Exception:
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
    
    try:
        config = configparser.ConfigParser(allow_no_value=True)
        config.read(env_file, encoding='utf-8')
        
        section_name = f"env:{env_name}"
        
        if not config.has_section(section_name):
            return False
        
        if set_ldf_off:
            config.set(section_name, "lib_ldf_mode", "off")
        else:
            if config.has_option(section_name, "lib_ldf_mode"):
                config.remove_option(section_name, "lib_ldf_mode")
        
        with open(env_file, 'w', encoding='utf-8') as f:
            config.write(f, space_around_delimiters=True)
        
        return True
        
    except Exception:
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
        except Exception:
            continue
    
    section_name = f"env:{env_name}"
    if merged_config.has_section(section_name):
        if merged_config.has_option(section_name, 'lib_ldf_mode'):
            return merged_config.get(section_name, 'lib_ldf_mode')
    
    if merged_config.has_section('env'):
        if merged_config.has_option('env', 'lib_ldf_mode'):
            return merged_config.get('env', 'lib_ldf_mode')
    
    return 'chain'

def safe_convert_for_pickle(obj, project_dir, max_depth=10, current_depth=0):
    """Konvertiert Objekte sicher für Pickle mit Pfad-Validierung"""
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
        for item in obj:
            converted.append(safe_convert_for_pickle(item, project_dir, max_depth, current_depth + 1))
        return converted
    elif isinstance(obj, dict):
        converted = {}
        for key, value in obj.items():
            safe_key = str(key)
            converted[safe_key] = safe_convert_for_pickle(value, project_dir, max_depth, current_depth + 1)
        return converted
    else:
        obj_str = str(obj)
        if ('/' in obj_str or '\\' in obj_str) and len(obj_str) > 3:
            return normalize_and_validate_path(obj_str, project_dir)
        else:
            return obj_str

def scan_library_includes(lib_path):
    """Scannt Library nach Include-Dependencies"""
    includes = set()
    
    for root, dirs, files in os.walk(lib_path):
        for file in files:
            if file.endswith(('.h', '.hpp', '.cpp', '.c')):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        includes_found = re.findall(r'#include\s*[<"]([\w\/\.\-]+)[>"]', content)
                        includes.update(includes_found)
                except:
                    pass
    
    return list(includes)

def read_library_manifest(lib_path):
    """Liest Library-Manifest (library.json/properties)"""
    manifest = {}
    
    # library.json
    json_path = os.path.join(lib_path, "library.json")
    if os.path.exists(json_path):
        try:
            import json
            with open(json_path, 'r') as f:
                manifest = json.load(f)
        except:
            pass
    
    # library.properties
    props_path = os.path.join(lib_path, "library.properties")
    if os.path.exists(props_path):
        try:
            with open(props_path, 'r') as f:
                for line in f:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        manifest[key] = value
        except:
            pass
    
    return manifest

def analyze_library_dependencies():
    """Analysiert den kompletten Library-Dependency-Graph"""
    dependency_graph = {}
    
    lib_dirs = env.get("LIBSOURCE_DIRS", [])
    project_lib_dir = os.path.join(env.get("PROJECT_DIR"), "lib")
    if os.path.exists(project_lib_dir):
        lib_dirs.append(project_lib_dir)
    
    for lib_dir in lib_dirs:
        if not os.path.exists(str(lib_dir)):
            continue
            
        for lib_name in os.listdir(str(lib_dir)):
            lib_path = os.path.join(str(lib_dir), lib_name)
            if os.path.isdir(lib_path):
                lib_info = {
                    "path": lib_path,
                    "includes": scan_library_includes(lib_path),
                    "manifest": read_library_manifest(lib_path)
                }
                dependency_graph[lib_name] = lib_info
    
    return dependency_graph

def capture_framework_manifest():
    """Erfasst Framework-Manifest-Daten"""
    framework_data = {}
    
    framework_dir = env.get("FRAMEWORK_DIR")
    if not framework_dir or not os.path.exists(framework_dir):
        return framework_data
    
    try:
        # Framework-Libraries erfassen
        libs_dir = os.path.join(framework_dir, "libraries")
        if os.path.exists(libs_dir):
            framework_libs = {}
            for lib_name in os.listdir(libs_dir):
                lib_path = os.path.join(libs_dir, lib_name)
                if os.path.isdir(lib_path):
                    framework_libs[lib_name] = {
                        "path": lib_path,
                        "includes": scan_library_includes(lib_path)
                    }
            framework_data["libraries"] = framework_libs
        
        # Variants erfassen
        variants_dir = os.path.join(framework_dir, "variants")
        if os.path.exists(variants_dir):
            variants = {}
            for variant_name in os.listdir(variants_dir):
                variant_path = os.path.join(variants_dir, variant_name)
                if os.path.isdir(variant_path):
                    variants[variant_name] = variant_path
            framework_data["variants"] = variants
            
    except Exception:
        pass
    
    return framework_data

def capture_complete_ldf_data():
    """Erfasst ALLE vom LDF generierten Daten"""
    print(f"🔍 Erfasse vollständige LDF-Environment-Daten...")
    
    project_dir = env.get("PROJECT_DIR")
    
    # Alle kritischen Environment-Variablen
    all_vars = [
        # Pfad-Variablen (kritisch)
        "FRAMEWORK_DIR", "PLATFORM_DIR", "PROJECT_DIR",
        "CPPPATH", "LIBPATH", "LIBSOURCE_DIRS", "EXTRA_LIB_DIRS",
        
        # Compiler und Tools
        "CC", "CXX", "AR", "RANLIB", "OBJCOPY", "SIZE",
        
        # Build-Konfiguration
        "BUILD_FLAGS", "CCFLAGS", "CXXFLAGS", "LINKFLAGS",
        "CPPDEFINES", "LIBS", "LIB_DEPS", "LIB_IGNORE",
        
        # Platform-spezifisch
        "PLATFORM_PACKAGES", "BOARD", "PLATFORM", "FRAMEWORK",
        "PIOENV", "BOARD_MCU", "BOARD_F_CPU", "BOARD_F_FLASH",
        
        # Upload-Konfiguration
        "UPLOAD_PROTOCOL", "UPLOAD_PORT", "UPLOAD_FLAGS"
    ]
    
    ldf_environment = {}
    
    for var in all_vars:
        if var in env:
            original_value = env[var]
            
            try:
                if var in ["FRAMEWORK_DIR", "PLATFORM_DIR", "PROJECT_DIR"]:
                    if original_value:
                        validated_path = normalize_and_validate_path(original_value, project_dir)
                        ldf_environment[var] = validated_path
                
                elif var in ["CPPPATH", "LIBPATH", "LIBSOURCE_DIRS", "EXTRA_LIB_DIRS"]:
                    if original_value:
                        validated_paths = []
                        for path in original_value:
                            validated = normalize_and_validate_path(path, project_dir)
                            if validated:
                                validated_paths.append(validated)
                        ldf_environment[var] = validated_paths
                
                else:
                    converted_value = safe_convert_for_pickle(original_value, project_dir)
                    ldf_environment[var] = converted_value
                        
            except Exception:
                ldf_environment[var] = str(original_value)[:500]
    
    # Erweiterte LDF-Daten erfassen
    try:
        # Library-Dependencies
        lib_deps_analysis = analyze_library_dependencies()
        ldf_environment["_LIB_DEPENDENCY_GRAPH"] = lib_deps_analysis
        
        # Framework-Manifest
        framework_data = capture_framework_manifest()
        ldf_environment["_FRAMEWORK_MANIFEST"] = framework_data
        
        # Metadaten
        ldf_environment["_PROJECT_DIR"] = project_dir
        ldf_environment["_WORKING_DIR"] = os.getcwd()
        ldf_environment["_PLATFORMIO_VERSION"] = env.get("PLATFORMIO_VERSION", "unknown")
        
    except Exception:
        pass
    
    print(f"✅ {len(ldf_environment)} Environment-Variablen erfasst")
    return ldf_environment

def early_cache_check_and_restore():
    """Prüft Cache und stellt Daten VOR LDF-Scan wieder her"""
    print(f"🔍 Frühe Cache-Prüfung...")
    
    # Cache laden BEVOR irgendetwas anderes passiert
    cached_data = load_complete_ldf_cache()
    
    if not cached_data:
        print(f"📝 Kein Cache - LDF wird normal ausgeführt")
        return False
    
    current_ldf_mode = get_current_ldf_mode(env.get("PIOENV"))
    
    if current_ldf_mode != 'off':
        print(f"🔄 LDF noch aktiv - Cache wird nach Build erstellt")
        return False
    
    # KRITISCH: Wiederherstellung VOR LDF-Scan
    print(f"⚡ Cache verfügbar - stelle Environment SOFORT wieder her")
    
    project_dir = env.get("PROJECT_DIR")
    
    # 1. Basis-Verzeichnisse ZUERST
    critical_paths = ["PROJECT_DIR", "FRAMEWORK_DIR", "PLATFORM_DIR"]
    for path_var in critical_paths:
        if path_var in cached_data:
            restored_path = restore_validated_path(cached_data[path_var], project_dir)
            if restored_path and os.path.exists(restored_path):
                env[path_var] = restored_path
                print(f"   ✓ {path_var}: {restored_path}")
            else:
                print(f"   ❌ {path_var}: Pfad ungültig - Cache wird ignoriert")
                return False
    
    # 2. Include-Pfade SOFORT setzen
    if "CPPPATH" in cached_data:
        valid_includes = []
        for path_data in cached_data["CPPPATH"]:
            restored_path = restore_validated_path(path_data, project_dir)
            if restored_path and os.path.exists(restored_path):
                valid_includes.append(restored_path)
        
        if len(valid_includes) > 5:  # Mindestens Framework-Includes
            env["CPPPATH"] = valid_includes
            print(f"   ✓ CPPPATH: {len(valid_includes)} Include-Pfade sofort gesetzt")
        else:
            print(f"   ❌ CPPPATH: Zu wenige gültige Pfade - Cache wird ignoriert")
            return False
    
    # 3. Compiler-Tools setzen
    compiler_tools = ["CC", "CXX", "AR", "RANLIB"]
    for tool in compiler_tools:
        if tool in cached_data:
            tool_path = cached_data[tool]
            if isinstance(tool_path, str) and (os.path.exists(tool_path) or shutil.which(tool_path)):
                env[tool] = tool_path
                print(f"   ✓ {tool}: {tool_path}")
    
    # 4. Defines und Build-Flags
    flag_vars = ["CPPDEFINES", "BUILD_FLAGS", "CCFLAGS", "CXXFLAGS", "LINKFLAGS"]
    for flag_var in flag_vars:
        if flag_var in cached_data:
            env[flag_var] = cached_data[flag_var]
            if hasattr(cached_data[flag_var], '__len__'):
                print(f"   ✓ {flag_var}: {len(cached_data[flag_var])} Einträge")
            else:
                print(f"   ✓ {flag_var}: Gesetzt")
    
    # 5. Libraries ZULETZT
    lib_vars = ["LIBS", "LIB_DEPS", "LIBPATH"]
    for lib_var in lib_vars:
        if lib_var in cached_data:
            if lib_var == "LIBPATH":
                valid_lib_paths = []
                for path_data in cached_data[lib_var]:
                    restored_path = restore_validated_path(path_data, project_dir)
                    if restored_path and os.path.exists(restored_path):
                        valid_lib_paths.append(restored_path)
                env[lib_var] = valid_lib_paths
                print(f"   ✓ {lib_var}: {len(valid_lib_paths)} Library-Pfade")
            else:
                env[lib_var] = cached_data[lib_var]
                if hasattr(cached_data[lib_var], '__len__'):
                    print(f"   ✓ {lib_var}: {len(cached_data[lib_var])} Einträge")
                else:
                    print(f"   ✓ {lib_var}: Wiederhergestellt")
    
    print(f"✅ Environment vollständig wiederhergestellt - LDF wird übersprungen")
    return True

def verify_environment_completeness():
    """Verifikation der Build-Environment"""
    print(f"\n🔍 Build-Environment-Verifikation...")
    
    critical_checks = {
        "Framework verfügbar": bool(env.get("FRAMEWORK_DIR")) and os.path.exists(env.get("FRAMEWORK_DIR", "")),
        "Include-Pfade gesetzt": len(env.get("CPPPATH", [])) > 5,
        "Include-Pfade existieren": all(os.path.exists(str(p)) for p in env.get("CPPPATH", [])[:5]),
        "Build-Flags vorhanden": len(env.get("BUILD_FLAGS", [])) > 0,
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
        print(f"✅ Build-Environment vollständig und gültig")
    else:
        print(f"⚠️  Build-Environment unvollständig")
    
    return all_ok

def calculate_final_config_hash():
    """Berechnet Hash NACH allen Konfigurationsänderungen"""
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
            except Exception:
                pass
    
    relevant_values.sort()
    config_string = "|".join(relevant_values)
    hash_value = hashlib.md5(config_string.encode('utf-8')).hexdigest()
    
    return hash_value

def save_complete_ldf_cache(ldf_environment):
    """Speichert LDF-Cache mit vollständigen Daten"""
    cache_file = get_cache_file_path()
    
    try:
        cache_dir = os.path.dirname(cache_file)
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
        
        final_hash = calculate_final_config_hash()
        
        cache_data = {
            "config_hash": final_hash,
            "ldf_environment": ldf_environment,
            "env_name": env.get("PIOENV"),
            "cache_version": "3.0",  # Neue Version mit korrektem Timing
            "project_dir": env.get("PROJECT_DIR")
        }
        
        # Test der Serialisierung
        test_data = pickle.dumps(cache_data, protocol=pickle.HIGHEST_PROTOCOL)
        
        with gzip.open(cache_file, 'wb') as f:
            pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        env_var_count = len(ldf_environment)
        file_size = os.path.getsize(cache_file)
        
        print(f"✓ LDF-Cache (Timing-korrigiert) erfolgreich gespeichert:")
        print(f"   📁 Datei: {os.path.basename(cache_file)} ({file_size} Bytes)")
        print(f"   📊 Environment-Variablen: {env_var_count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Cache-Speicherfehler: {e}")
        return False

def load_complete_ldf_cache():
    """Lädt LDF-Cache mit vollständigen Daten"""
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        return None
    
    try:
        with gzip.open(cache_file, 'rb') as f:
            cache_data = pickle.load(f)
        
        cache_version = cache_data.get("cache_version", "1.0")
        if cache_version not in ["2.0", "2.1", "2.2", "3.0"]:
            return None
        
        # Prüfe ob Cache für das gleiche Projekt ist
        cached_project_dir = cache_data.get("project_dir")
        current_project_dir = env.get("PROJECT_DIR")
        if cached_project_dir != current_project_dir:
            return None
        
        current_hash = calculate_final_config_hash()
        cached_hash = cache_data.get("config_hash")
        
        if cached_hash == current_hash:
            return cache_data.get("ldf_environment")
        
    except Exception:
        pass
    
    return None

# =============================================================================
# HAUPTLOGIK - TIMING-KORRIGIERTE LDF-OPTIMIERUNG
# =============================================================================

print(f"\n🚀 Tasmota LDF-Optimierung (Timing-korrigiert) für Environment: {env.get('PIOENV')}")

# KRITISCH: Cache-Prüfung und Wiederherstellung SOFORT
cache_restored = early_cache_check_and_restore()

if cache_restored:
    # Cache erfolgreich wiederhergestellt - LDF überspringen
    print(f"🚀 Build läuft mit Cache - LDF übersprungen!")
    
    # Verifikation der wiederhergestellten Environment
    if not verify_environment_completeness():
        print(f"❌ Environment-Verifikation fehlgeschlagen - Fallback zu normalem LDF")
        cache_restored = False

if not cache_restored:
    # Normaler LDF-Durchlauf mit Cache-Erstellung
    print(f"📝 Führe normalen LDF-Durchlauf durch...")
    
    def post_build_cache_creation(source, target, env):
        """Post-Build: Erstelle Cache für nächsten Durchlauf"""
        print(f"\n🔄 Post-Build: Erstelle LDF-Cache...")
        
        complete_ldf_data = capture_complete_ldf_data()
        
        if len(complete_ldf_data) > 10:
            env_name = env.get("PIOENV")
            if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                print(f"✓ lib_ldf_mode = off für nächsten Build gesetzt")
            
            if save_complete_ldf_cache(complete_ldf_data):
                print(f"✓ Cache erstellt - nächster Build wird optimiert")
                print(f"\n💡 Führen Sie 'pio run' erneut aus für optimierten Build")
                print(f"   Nächster Build überspringt LDF komplett")
    
    env.AddPostAction("buildprog", post_build_cache_creation)

print(f"🏁 LDF-Optimierung (Timing-korrigiert) Setup abgeschlossen")
print(f"💡 Tipp: Löschen Sie '.pio/ldf_cache/' um den Cache zurückzusetzen\n")
