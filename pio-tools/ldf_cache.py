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
    
    print(f"📁 Gefundene PlatformIO Konfigurationsdateien:")
    for ini_file in ini_files:
        print(f"   - {os.path.basename(ini_file)}")
    
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

def handle_special_scons_objects(obj):
    """Spezialbehandlung für bekannte SCons-Objekttypen"""
    obj_type = str(type(obj))
    
    if 'Scanner' in obj_type:
        # Scanner-Objekte: Extrahiere wichtige Attribute
        scanner_data = {
            '__scons_type__': 'Scanner',
            'name': getattr(obj, 'name', 'unknown'),
            'suffixes': getattr(obj, 'skeys', []),
            'function': str(getattr(obj, 'function', 'unknown')),
            'original_type': obj_type
        }
        return scanner_data
    elif 'Builder' in obj_type:
        # Builder-Objekte: Extrahiere Konfiguration
        builder_data = {
            '__scons_type__': 'Builder',
            'name': str(obj),
            'action': str(getattr(obj, 'action', 'unknown')),
            'suffix': getattr(obj, 'suffix', ''),
            'original_type': obj_type
        }
        return builder_data
    elif 'NodeList' in obj_type:
        # NodeList: Konvertiere zu String-Liste
        return {
            '__scons_type__': 'NodeList',
            'nodes': [str(node) for node in obj],
            'original_type': obj_type
        }
    elif 'Node' in obj_type:
        # Einzelne Nodes
        return {
            '__scons_type__': 'Node',
            'path': str(obj),
            'original_type': obj_type
        }
    else:
        return {
            '__scons_type__': 'Unknown',
            'string_repr': str(obj),
            'original_type': obj_type
        }

def safe_deep_convert_for_pickle(obj, max_depth=15, current_depth=0, seen_objects=None):
    """Konvertiert SCons-Objekte rekursiv zu pickle-baren Datenstrukturen"""
    if seen_objects is None:
        seen_objects = set()
    
    # Schutz vor Endlosschleifen
    obj_id = id(obj)
    if obj_id in seen_objects or current_depth > max_depth:
        return f"<CIRCULAR_REF_OR_MAX_DEPTH:{str(obj)[:50]}>"
    
    seen_objects.add(obj_id)
    
    try:
        # Test ob bereits pickle-bar
        pickle.dumps(obj)
        seen_objects.remove(obj_id)
        return obj
    except:
        pass
    
    try:
        # Konvertierung basierend auf Typ
        if obj is None:
            result = None
        elif isinstance(obj, (str, int, float, bool)):
            result = obj
        elif isinstance(obj, (list, tuple)):
            converted = []
            for i, item in enumerate(obj):
                if i > 1000:  # Schutz vor sehr großen Listen
                    converted.append(f"<TRUNCATED_AT_{i}_ITEMS>")
                    break
                converted.append(safe_deep_convert_for_pickle(item, max_depth, current_depth + 1, seen_objects.copy()))
            result = converted
        elif isinstance(obj, dict):
            converted = {}
            item_count = 0
            for key, value in obj.items():
                if item_count > 500:  # Schutz vor sehr großen Dictionaries
                    converted["<TRUNCATED>"] = f"<TRUNCATED_AT_{item_count}_ITEMS>"
                    break
                try:
                    safe_key = str(key)
                    converted[safe_key] = safe_deep_convert_for_pickle(value, max_depth, current_depth + 1, seen_objects.copy())
                    item_count += 1
                except:
                    converted[f"<FAILED_KEY_{item_count}>"] = str(value)[:100]
                    item_count += 1
            result = converted
        elif hasattr(obj, '__dict__'):
            # Objekt mit Attributen - versuche SCons-spezifische Behandlung
            if any(keyword in str(type(obj)) for keyword in ['Scanner', 'Builder', 'Node']):
                result = handle_special_scons_objects(obj)
            else:
                # Generische Objekt-Konvertierung
                try:
                    obj_dict = {'__original_type__': str(type(obj))}
                    attr_count = 0
                    for attr_name in dir(obj):
                        if attr_count > 100:  # Begrenze Attribute
                            break
                        if not attr_name.startswith('_') and attr_name not in ['im_func', 'im_self']:
                            try:
                                attr_value = getattr(obj, attr_name)
                                if not callable(attr_value):
                                    obj_dict[attr_name] = safe_deep_convert_for_pickle(attr_value, max_depth, current_depth + 1, seen_objects.copy())
                                    attr_count += 1
                            except:
                                pass
                    result = obj_dict
                except:
                    result = handle_special_scons_objects(obj)
        elif hasattr(obj, '__iter__') and not isinstance(obj, str):
            # Iterable Objekte (NodeList, etc.)
            if any(keyword in str(type(obj)) for keyword in ['NodeList', 'Scanner', 'Builder']):
                result = handle_special_scons_objects(obj)
            else:
                try:
                    converted = []
                    item_count = 0
                    for item in obj:
                        if item_count > 500:  # Begrenze Iterationen
                            converted.append(f"<TRUNCATED_AT_{item_count}_ITEMS>")
                            break
                        converted.append(safe_deep_convert_for_pickle(item, max_depth, current_depth + 1, seen_objects.copy()))
                        item_count += 1
                    result = converted
                except:
                    result = handle_special_scons_objects(obj)
        else:
            # Fallback: SCons-spezifische Behandlung oder String
            result = handle_special_scons_objects(obj)
        
        seen_objects.remove(obj_id)
        return result
        
    except Exception as e:
        seen_objects.discard(obj_id)
        return f"<CONVERSION_ERROR:{str(e)[:100]}:{str(obj)[:50]}>"

def capture_complete_ldf_environment():
    """Erfasst ALLE LDF-Environment-Daten mit rekursiver Deep-Conversion"""
    print(f"🔍 Erfasse vollständige LDF-Environment-Daten (rekursive Deep-Conversion)...")
    
    # ALLE Environment-Variablen erfassen
    all_vars = [
        "LIBS", "LIBPATH", "CPPPATH", "CPPDEFINES", 
        "BUILD_FLAGS", "CCFLAGS", "CXXFLAGS", "LINKFLAGS",
        "LIB_DEPS", "LIB_IGNORE", "FRAMEWORK_DIR", "PLATFORM_DIR",
        "PLATFORM_PACKAGES", "CC", "CXX", "AR", "RANLIB",
        "LIBSOURCE_DIRS", "EXTRA_LIB_DIRS", "PIOENV", 
        "BOARD", "PLATFORM", "FRAMEWORK", "SCANNERS",
        "BUILDERS", "TOOLS", "ENV", "CPPFLAGS", "ASFLAGS"
    ]
    
    ldf_environment = {}
    conversion_stats = {'success': 0, 'failed': 0, 'converted': 0}
    
    for var in all_vars:
        if var in env:
            original_value = env[var]
            
            print(f"   🔄 Konvertiere {var}: {type(original_value).__name__}...")
            
            try:
                # Rekursive Deep-Conversion
                converted_value = safe_deep_convert_for_pickle(original_value)
                
                # Test ob konvertierter Wert pickle-bar ist
                pickle.dumps(converted_value)
                
                ldf_environment[var] = converted_value
                conversion_stats['success'] += 1
                
                if hasattr(converted_value, '__len__') and not isinstance(converted_value, str):
                    print(f"   ✓ {var}: {len(converted_value)} Elemente erfolgreich konvertiert")
                else:
                    print(f"   ✓ {var}: Erfolgreich konvertiert")
                    
            except Exception as e:
                print(f"   ⚠ {var}: Konvertierungsfehler - {e}")
                # Notfall-Fallback
                ldf_environment[var] = {
                    '__conversion_failed__': True,
                    'error': str(e),
                    'string_repr': str(original_value)[:500],
                    'type': str(type(original_value))
                }
                conversion_stats['failed'] += 1
    
    # Zusätzliche SCons-Environment-Metadaten
    try:
        env_keys = list(env.keys())
        ldf_environment["_ENV_KEYS"] = env_keys
        ldf_environment["_CONVERSION_STATS"] = conversion_stats
        print(f"   📊 Environment-Schlüssel: {len(env_keys)} erfasst")
    except:
        pass
    
    print(f"✅ {len(ldf_environment)} Environment-Variablen vollständig konvertiert")
    print(f"   📊 Erfolgreich: {conversion_stats['success']}, Fehlgeschlagen: {conversion_stats['failed']}")
    return ldf_environment

def restore_complete_ldf_environment(cached_env_data):
    """Stellt ALLE konvertierten Environment-Daten wieder her"""
    print(f"🔄 Stelle vollständige LDF-Environment wieder her...")
    
    restored_count = 0
    failed_count = 0
    
    for var_name, cached_value in cached_env_data.items():
        if var_name.startswith('_'):
            continue  # Skip Metadaten
            
        try:
            # Prüfe ob Konvertierung fehlgeschlagen war
            if isinstance(cached_value, dict) and cached_value.get('__conversion_failed__'):
                print(f"   ⚠ {var_name}: War nicht konvertierbar - überspringe")
                failed_count += 1
                continue
            
            # Direkte Zuweisung der konvertierten Daten
            env[var_name] = cached_value
            restored_count += 1
            
            if hasattr(cached_value, '__len__') and not isinstance(cached_value, str):
                print(f"   ✓ {var_name}: {len(cached_value)} Elemente wiederhergestellt")
            else:
                print(f"   ✓ {var_name}: Wiederhergestellt")
                
        except Exception as e:
            print(f"   ⚠ {var_name}: Wiederherstellungsfehler - {e}")
            failed_count += 1
    
    print(f"✅ {restored_count} Environment-Variablen wiederhergestellt, {failed_count} übersprungen")
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
    """Berechnet Hash NACH allen Konfigurationsänderungen (ohne SCons-Objekte)"""
    relevant_values = [
        f"BOARD:{env.get('BOARD', '')}",
        f"PLATFORM:{env.get('PLATFORM', '')}",
        f"PIOENV:{env.get('PIOENV', '')}"
    ]
    
    # Nur INI-Dateien für Hash verwenden (keine Environment-Variablen mit SCons-Objekten)
    ini_files = find_all_platformio_files()
    
    for ini_file in sorted(ini_files):
        if os.path.exists(ini_file) and not ini_file.endswith('.ldf_backup'):
            try:
                with open(ini_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Hash des Dateiinhalts
                    file_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
                    relevant_values.append(f"{os.path.basename(ini_file)}:{file_hash}")
            except Exception:
                pass
    
    relevant_values.sort()
    config_string = "|".join(relevant_values)
    hash_value = hashlib.md5(config_string.encode('utf-8')).hexdigest()
    
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
            "ldf_environment": ldf_environment,  # Konvertierte SCons-Objekte!
            "env_name": env.get("PIOENV"),
            "cache_version": "2.1"  # Neue Version für rekursive Konvertierung
        }
        
        # Test der kompletten Serialisierung
        test_data = pickle.dumps(cache_data)
        print(f"   🔍 Pickle-Test erfolgreich: {len(test_data)} Bytes")
        
        # Komprimiert mit Pickle speichern
        with gzip.open(cache_file, 'wb') as f:
            pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        # Statistiken
        env_var_count = len(ldf_environment)
        conversion_stats = ldf_environment.get("_CONVERSION_STATS", {})
        
        print(f"✓ LDF-Cache (Pickle) erfolgreich gespeichert:")
        print(f"   📁 Datei: {os.path.basename(cache_file)}")
        print(f"   📊 Environment-Variablen: {env_var_count}")
        print(f"   ✅ Erfolgreich konvertiert: {conversion_stats.get('success', 0)}")
        print(f"   ⚠ Fehlgeschlagen: {conversion_stats.get('failed', 0)}")
        
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
        if cache_version not in ["2.0", "2.1"]:
            print(f"⚠ Veraltete Cache-Version {cache_version} - wird ignoriert")
            return None
        
        # Hash-Vergleich
        current_hash = calculate_final_config_hash()
        cached_hash = cache_data.get("config_hash")
        
        if cached_hash == current_hash:
            ldf_environment = cache_data.get("ldf_environment")
            if ldf_environment:
                env_var_count = len(ldf_environment)
                conversion_stats = ldf_environment.get("_CONVERSION_STATS", {})
                
                print(f"✓ LDF-Cache (Pickle) erfolgreich geladen:")
                print(f"   📊 Environment-Variablen: {env_var_count}")
                print(f"   ✅ Erfolgreich konvertiert: {conversion_stats.get('success', 0)}")
                print(f"   ⚠ Fehlgeschlagen: {conversion_stats.get('failed', 0)}")
                
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
# HAUPTLOGIK - VOLLSTÄNDIGE LDF-ENVIRONMENT-WIEDERHERSTELLUNG MIT REKURSIVER CONVERSION
# =============================================================================

print(f"\n🚀 Tasmota LDF-Optimierung für Environment: {env.get('PIOENV')}")

env_name = env.get("PIOENV")
current_ldf_mode = get_current_ldf_mode(env_name)
print(f"📊 Aktueller LDF-Modus: {current_ldf_mode}")

cached_ldf_env = load_complete_ldf_cache()

# Prüfe ob vollständiger Cache verfügbar ist
cache_is_complete = (cached_ldf_env is not None and 
                    len(cached_ldf_env) > 5 and
                    cached_ldf_env.get("CPPPATH") is not None)

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
        """SCons Post-Action: Erfasse ALLE LDF-Daten mit rekursiver Pickle-Conversion"""
        print(f"\n🔄 Post-Build: Erfasse vollständige LDF-Environment (rekursive Conversion)...")
        
        # Erfasse ALLE LDF-Environment-Daten mit rekursiver Deep-Conversion
        complete_ldf_env = capture_complete_ldf_environment()
        
        if len(complete_ldf_env) > 5:
            # Setze lib_ldf_mode = off für nächsten Build
            env_name = env.get("PIOENV")
            if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                print(f"✓ lib_ldf_mode = off für nächsten Build gesetzt")
            
            # Speichere vollständige Environment-Daten mit Pickle
            if save_complete_ldf_cache(complete_ldf_env):
                conversion_stats = complete_ldf_env.get("_CONVERSION_STATS", {})
                
                print(f"\n📊 LDF-Environment erfolgreich erfasst:")
                print(f"   📚 Variablen erfasst: {len(complete_ldf_env)}")
                print(f"   ✅ Erfolgreich: {conversion_stats.get('success', 0)}")
                print(f"   ⚠ Fehlgeschlagen: {conversion_stats.get('failed', 0)}")
                
                print(f"\n💡 Führen Sie 'pio run' erneut aus für optimierten Build")
                print(f"   Nächster Build verwendet gespeicherte LDF-Environment (rekursive Pickle)")
            else:
                print(f"⚠ Fehler beim Speichern der LDF-Environment")
        else:
            print(f"⚠ Unvollständige LDF-Environment erfasst")
    
    # Registriere SCons Post-Action
    env.AddPostAction("buildprog", complete_post_build_action)

print(f"🏁 LDF-Optimierung Setup abgeschlossen für {env_name}")
print(f"💡 Tipp: Löschen Sie '.pio/ldf_cache/' um den Cache zurückzusetzen\n")
