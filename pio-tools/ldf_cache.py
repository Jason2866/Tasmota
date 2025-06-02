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
original_compile_action = None

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

def capture_compile_time_environment(compile_env):
    """Erfasst Environment-Daten zur COMPILE-ZEIT"""
    
    print(f"\n🎯 COMPILE-TIME Environment-Erfassung:")
    
    # Kritische Variablen direkt aus Compile-Environment lesen
    critical_vars = [
        'CPPPATH', 'CPPDEFINES', 'LIBS', 'LIBPATH', 
        'BUILD_FLAGS', 'CCFLAGS', 'CXXFLAGS', 'LINKFLAGS',
        'PIOBUILDFILES', 'LIB_DEPS', 'LIB_EXTRA_DIRS',
        'FRAMEWORK_DIR', 'PLATFORM_PACKAGES_DIR'
    ]
    
    compile_data = {}
    conversion_stats = {"file_paths": 0, "builders": 0, "functions": 0, "other": 0}
    
    for var in critical_vars:
        # DIREKTER Zugriff auf Compile-Environment
        raw_value = compile_env.get(var, [])
        
        if var == 'CPPPATH':
            print(f"   📁 COMPILE-TIME CPPPATH: {len(raw_value)} Einträge")
            
            # Analysiere Pfad-Quellen
            source_stats = {}
            for i, path in enumerate(raw_value):
                path_str = str(path.abspath) if hasattr(path, 'abspath') else str(path)
                source = determine_path_source(path_str)
                exists = os.path.exists(path_str)
                
                if source not in source_stats:
                    source_stats[source] = 0
                source_stats[source] += 1
                
                # Zeige erste 10 zur Verifikation
                if i < 10:
                    print(f"      {i:2d}: {source:12s} {'✓' if exists else '✗'} {path_str}")
            
            print(f"   📊 Pfad-Quellen-Verteilung:")
            for source, count in sorted(source_stats.items()):
                print(f"      {source:12s}: {count} Pfade")
        
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
        compile_data[var] = converted_value
        
        # Zähle Konvertierungen
        if var == 'CPPPATH' and isinstance(raw_value, list):
            for item in raw_value:
                if hasattr(item, 'abspath'):
                    conversion_stats["file_paths"] += 1
    
    print(f"   🔄 {conversion_stats['file_paths']} SCons-Pfad-Objekte konvertiert")
    print(f"   ✅ String-Pfade blieben unverändert")
    
    return compile_data, conversion_stats

def freeze_compile_time_configuration(compile_data, conversion_stats):
    """Speichert Compile-Time erfasste Environment-Daten"""
    cache_file = get_cache_file_path()
    temp_file = cache_file + ".tmp"
    
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write("# SCons Environment - COMPILE-TIME Erfassung\n")
            f.write("# SCons objects → paths, String paths unchanged\n")
            f.write("# Auto-generated - do not edit manually\n")
            f.write(f"# Generated: {time.ctime()}\n")
            f.write(f"# Environment: {env.get('PIOENV')}\n")
            f.write(f"# Captured during ACTUAL COMPILATION\n\n")
            
            f.write("def restore_environment(target_env):\n")
            f.write('    """Stellt das Compile-Time erfasste SCons-Environment wieder her"""\n')
            f.write('    restored_count = 0\n')
            f.write('    \n')
            
            var_count = 0
            
            for key, value in sorted(compile_data.items()):
                try:
                    f.write(f'    # {key} (Compile-Time erfasst)\n')
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
            f.write('    # === COMPILE-TIME INTERCEPTOR STATISTIKEN ===\n')
            f.write(f'    conversion_stats = {repr(conversion_stats)}\n')
            f.write('    \n')
            
            f.write('    print(f"✓ {{restored_count}} SCons-Variablen wiederhergestellt (Compile-Time)")\n')
            f.write('    print(f"✓ {{conversion_stats[\'file_paths\']}} SCons-Pfad-Objekte konvertiert")\n')
            f.write('    print(f"✓ String-Pfade blieben unverändert")\n')
            f.write('    print("✓ Erfasst während tatsächlicher Kompilierung")\n')
            f.write('    return restored_count > 10\n')
            f.write('\n')
            f.write('# Metadata\n')
            f.write(f'CONFIG_HASH = {repr(calculate_config_hash())}\n')
            f.write(f'ENV_NAME = {repr(env.get("PIOENV"))}\n')
            f.write(f'VARIABLE_COUNT = {var_count}\n')
            f.write(f'COMPILE_TIME_INTERCEPTOR = True\n')
            f.write(f'CONVERTED_FILE_PATHS = {conversion_stats["file_paths"]}\n')
        
        # Atomarer Move
        shutil.move(temp_file, cache_file)
        
        file_size = os.path.getsize(cache_file)
        cpppath_count = len(compile_data.get('CPPPATH', []))
        
        print(f"✓ Compile-Time Environment-Erfassung gespeichert:")
        print(f"   📁 {os.path.basename(cache_file)} ({file_size} Bytes)")
        print(f"   📊 {var_count} SCons-Variablen (Compile-Time)")
        print(f"   📄 {cpppath_count} CPPPATH-Einträge")
        print(f"   🔄 {conversion_stats['file_paths']} SCons-Objekte konvertiert")
        print(f"   ✅ Compile-Time Interceptor verwendet")
        
        return True
        
    except Exception as e:
        print(f"❌ Compile-Time Environment-Erfassung fehlgeschlagen: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def install_compile_time_interceptor():
    """Installiert Compile-Time Environment Interceptor"""
    
    global _backup_created, original_compile_action
    
    def compile_time_interceptor(target, source, env):
        """Interceptor für Compile-Time Environment - hier ist CPPPATH vollständig"""
        
        if not _backup_created:
            try:
                compile_cpppath = env.get('CPPPATH', [])
                
                print(f"🎯 COMPILE-TIME INTERCEPTOR: {len(compile_cpppath)} CPPPATH-Einträge")
                
                # Zeige LDF-spezifische Pfade
                ldf_paths = [p for p in compile_cpppath if any(x in str(p) for x in ['.pio/', 'lib/'])]
                framework_paths = [p for p in compile_cpppath if 'framework-' in str(p)]
                
                print(f"   📚 LDF-Pfade: {len(ldf_paths)}")
                print(f"   🔧 Framework-Pfade: {len(framework_paths)}")
                
                # Prüfe ob vollständige CPPPATH (> 50 erwartet)
                if len(compile_cpppath) > 50:
                    print(f"✅ VOLLSTÄNDIGE CPPPATH zur Compile-Zeit erfasst!")
                    
                    # Compile-Time Environment erfassen
                    compile_data, conversion_stats = capture_compile_time_environment(env)
                    
                    if freeze_compile_time_configuration(compile_data, conversion_stats):
                        env_name = env.get("PIOENV")
                        if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                            print(f"🚀 Compile-Time Interceptor: Environment erfolgreich erfasst!")
                            _backup_created = True
                        else:
                            print(f"⚠ lib_ldf_mode konnte nicht gesetzt werden")
                    else:
                        print(f"❌ Compile-Time Environment-Speicherung fehlgeschlagen")
                        
                elif len(compile_cpppath) > 10:
                    print(f"⚠ Unvollständige CPPPATH ({len(compile_cpppath)}) - erwarte > 50")
                    
                    # Erfasse trotzdem für Debugging
                    compile_data, conversion_stats = capture_compile_time_environment(env)
                    
                else:
                    print(f"❌ Zu wenige CPPPATH-Einträge ({len(compile_cpppath)}) zur Compile-Zeit")
            
            except Exception as e:
                print(f"❌ Compile-Time Interceptor Fehler: {e}")
        
        # Original Compile-Action aufrufen
        return original_compile_action(target, source, env)
    
    # Hook in Object-Builder Compile-Action integrieren
    try:
        object_builder = env['BUILDERS']['Object']
        
        if hasattr(object_builder, 'action'):
            # Original Action speichern
            original_compile_action = object_builder.action
            
            # Action durch Interceptor ersetzen
            object_builder.action = compile_time_interceptor
            
            print(f"✅ Compile-Time Interceptor erfolgreich installiert")
            return True
        else:
            print(f"❌ Object-Builder hat keine action-Attribute")
            return False
        
    except Exception as e:
        print(f"❌ Compile-Time Interceptor Installation fehlgeschlagen: {e}")
        return False

def debug_compile_environment():
    """Debuggt die Compile-Environment-Struktur"""
    
    print(f"\n🔍 Compile-Environment-Debug:")
    
    try:
        object_builder = env['BUILDERS']['Object']
        print(f"   Object Builder: {type(object_builder)}")
        
        if hasattr(object_builder, 'action'):
            action = object_builder.action
            print(f"   Compile Action: {type(action)}")
            print(f"   Action ist callable: {callable(action)}")
            
            # Zeige Action-Attribute
            if hasattr(action, '__dict__'):
                action_attrs = [attr for attr in dir(action) if not attr.startswith('_')]
                print(f"   Action Attribute: {action_attrs[:10]}...")
        else:
            print(f"   ❌ Keine Compile-Action gefunden")
        
        # Zeige Environment-Variablen zur Compile-Zeit
        current_cpppath = env.get('CPPPATH', [])
        print(f"   Aktuelle CPPPATH: {len(current_cpppath)} Einträge")
        
        # Zeige Compiler-Konfiguration
        cc = env.get('CC', 'unbekannt')
        cxx = env.get('CXX', 'unbekannt')
        print(f"   C Compiler: {cc}")
        print(f"   C++ Compiler: {cxx}")
        
    except Exception as e:
        print(f"   ❌ Compile-Environment-Debug Fehler: {e}")

def post_compile_action(target, source, env):
    """Fallback SCons Action: Erfasst Environment nach Compile, vor Linking"""
    global _backup_created
    
    if _backup_created:
        print("✓ Environment bereits erfasst - überspringe Post-Compile Action")
        return None
    
    try:
        print(f"\n🎯 FALLBACK Post-Compile Action: Erfasse SCons-Environment")
        print(f"   Target: {[str(t) for t in target]}")
        print(f"   Source: {len(source)} Dateien")
        
        # DIREKTE Environment-Erfassung als Fallback
        compile_data, conversion_stats = capture_compile_time_environment(env)
        
        # Prüfe ob realistische Werte vorhanden sind
        cpppath_count = len(compile_data.get('CPPPATH', []))
        
        print(f"   📊 Fallback Environment-Statistik:")
        print(f"      CPPPATH: {cpppath_count} Pfade")
        
        if cpppath_count > 5:  # Mindestens Framework-Pfade
            print(f"✅ Environment-Werte erfasst - speichere Fallback-Daten")
            
            if freeze_compile_time_configuration(compile_data, conversion_stats):
                env_name = env.get("PIOENV")
                if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                    print(f"✓ lib_ldf_mode = off für Lauf 2 gesetzt")
                    print(f"🚀 FALLBACK SCons-Environment-Erfassung abgeschlossen!")
                    _backup_created = True
                else:
                    print(f"⚠ lib_ldf_mode konnte nicht gesetzt werden")
            else:
                print(f"❌ Fallback Environment-Erfassung fehlgeschlagen")
        else:
            print(f"⚠ Zu wenige CPPPATH-Einträge - überspringe Fallback-Erfassung")
    
    except Exception as e:
        print(f"❌ Fallback Post-Compile Action Fehler: {e}")
    
    return None

def restore_exact_scons_configuration():
    """Lädt Environment aus Python-Datei (Compile-Time)"""
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
        
        # Prüfe ob Compile-Time Interceptor verwendet wurde
        compile_time_interceptor = getattr(env_module, 'COMPILE_TIME_INTERCEPTOR', False)
        if compile_time_interceptor:
            print("✅ Cache stammt von Compile-Time Interceptor")
        
        # Environment wiederherstellen
        success = env_module.restore_environment(env)
        
        if success:
            var_count = getattr(env_module, 'VARIABLE_COUNT', 0)
            converted_file_paths = getattr(env_module, 'CONVERTED_FILE_PATHS', 0)
            
            print(f"✓ Compile-Time Environment wiederhergestellt:")
            print(f"   📊 {var_count} Variablen")
            print(f"   📄 {converted_file_paths} SCons-Pfad-Objekte konvertiert")
            print(f"   ✅ Compile-Time Interceptor verwendet")
        
        return success
        
    except Exception as e:
        print(f"❌ Compile-Time Cache-Wiederherstellung fehlgeschlagen: {e}")
        return False

def early_cache_check_and_restore():
    """Prüft Cache und stellt SCons-Environment wieder her"""
    print(f"🔍 Cache-Prüfung (Compile-Time Environment)...")
    
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        print(f"📝 Kein Compile-Time Cache - LDF wird normal ausgeführt")
        return False
    
    current_ldf_mode = get_current_ldf_mode(env.get("PIOENV"))
    
    if current_ldf_mode != 'off':
        print(f"🔄 LDF noch aktiv - Compile-Time Interceptor wird nach Build erstellt")
        return False
    
    print(f"⚡ Compile-Time Cache verfügbar - stelle Environment wieder her")
    
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
# HAUPTLOGIK - COMPILE-TIME ENVIRONMENT INTERCEPTOR
# =============================================================================

print(f"\n🎯 Compile-Time Environment Interceptor für: {env.get('PIOENV')}")

# Cache-Prüfung und SCons-Environment-Wiederherstellung
cache_restored = early_cache_check_and_restore()

if cache_restored:
    print(f"🚀 Build mit Compile-Time Environment-Cache - LDF übersprungen!")

else:
    print(f"📝 Normaler LDF-Durchlauf - installiere Compile-Time Interceptor...")
    
    # Debug Compile-Environment-Struktur
    debug_compile_environment()
    
    # Installiere Compile-Time Interceptor
    interceptor_success = install_compile_time_interceptor()
    
    if interceptor_success:
        print(f"✅ Compile-Time Interceptor erfolgreich installiert")
        print(f"🎯 Interceptor wird während tatsächlicher Kompilierung aktiv")
        print(f"📊 Erwartet: > 50 CPPPATH-Einträge zur Compile-Zeit")
    else:
        print(f"❌ Compile-Time Interceptor Installation fehlgeschlagen")
        print(f"💡 Fallback: Verwende Post-Action Hook")
        
        # Fallback auf Post-Action
        env.AddPostAction("$BUILD_DIR/${PROGNAME}.elf", post_compile_action)
        print(f"✅ Fallback Post-Action Hook registriert")

print(f"🏁 Compile-Time Environment Interceptor initialisiert")
print(f"💡 Reset: rm -rf .pio/ldf_cache/\n")
