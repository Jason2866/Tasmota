Import("env")
import os
import hashlib
import configparser
import shutil
import glob
import time
import importlib.util
import json
import re
from datetime import datetime

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

def convert_scons_objects_selective(value, key="", depth=0):
    """Konvertiert NUR SCons-Objekte zu Pfaden, String-Pfade bleiben unverändert"""
    
    if depth > 10:
        return str(value)
    
    if hasattr(value, 'abspath'):
        return str(value.abspath)
    elif hasattr(value, 'path'):
        return str(value.path)
    elif hasattr(value, 'get_path'):
        try:
            return str(value.get_path())
        except:
            return str(value)
    elif hasattr(value, '__class__') and 'SCons.Builder' in str(value.__class__):
        return f"<Builder:{getattr(value, 'name', 'Unknown')}>"
    elif hasattr(value, '__class__') and 'SCons.Scanner' in str(value.__class__):
        return f"<Scanner:{getattr(value, 'name', 'Unknown')}>"
    elif hasattr(value, '__class__') and 'SCons.Environment' in str(value.__class__):
        return "<Environment>"
    elif hasattr(value, '__class__') and 'SCons.Defaults' in str(value.__class__):
        return f"<Default:{value.__class__.__name__}>"
    elif callable(value):
        if hasattr(value, '__name__'):
            return f"<Function:{value.__name__}>"
        else:
            return f"<Callable:{value.__class__.__name__}>"
    elif isinstance(value, list):
        return [convert_scons_objects_selective(item, key, depth + 1) for item in value]
    elif isinstance(value, tuple):
        return tuple(convert_scons_objects_selective(item, key, depth + 1) for item in value)
    elif isinstance(value, dict):
        return {convert_scons_objects_selective(k, key, depth + 1): convert_scons_objects_selective(v, key, depth + 1) for k, v in value.items()}
    elif hasattr(value, '__class__') and value.__class__.__name__ == 'deque':
        return list(value)
    elif hasattr(value, '__class__') and 'environ' in str(value.__class__).lower():
        return dict(value)
    elif hasattr(value, '__class__') and 'SCons' in str(value.__class__):
        return str(value)
    elif isinstance(value, (str, int, float, bool, type(None))):
        return value
    else:
        return str(value)

def debug_environment_restoration_detailed():
    """Detaillierte Debug-Analyse der Environment-Wiederherstellung"""
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        print(f"❌ Cache-Datei existiert nicht: {cache_file}")
        return False
    
    print(f"\n🔍 DETAILLIERTE ENVIRONMENT-WIEDERHERSTELLUNG-DEBUG:")
    print(f"   📁 Cache-Datei: {os.path.basename(cache_file)}")
    print(f"   📊 Cache-Größe: {os.path.getsize(cache_file)} Bytes")
    
    try:
        # CPPPATH vor Wiederherstellung erfassen
        cpppath_before = list(env.get('CPPPATH', []))
        print(f"   📊 CPPPATH vor Wiederherstellung: {len(cpppath_before)} Einträge")
        
        # Zeige aktuelle CPPPATH-Einträge
        if len(cpppath_before) > 0:
            print(f"   📄 Aktuelle CPPPATH (erste 3):")
            for i, path in enumerate(cpppath_before[:3]):
                path_str = str(path.abspath) if hasattr(path, 'abspath') else str(path)
                print(f"      {i+1}: {path_str}")
        
        # Cache laden und analysieren
        print(f"   🔄 Lade Cache-Modul...")
        spec = importlib.util.spec_from_file_location("scons_env_cache", cache_file)
        env_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(env_module)
        print(f"   ✅ Cache-Modul erfolgreich geladen")
        
        # Cache-Inhalt analysieren
        comprehensive_data = getattr(env_module, 'COMPREHENSIVE_DATA', {})
        all_env_vars = comprehensive_data.get('all_environment_vars', {})
        cached_cpppath = all_env_vars.get('CPPPATH', [])
        
        print(f"   💾 Cache-Analyse:")
        print(f"      📊 Gespeicherte Environment-Variablen: {len(all_env_vars)}")
        print(f"      📊 Gespeicherte CPPPATH-Einträge: {len(cached_cpppath)}")
        
        # Zeige gespeicherte CPPPATH-Einträge
        if len(cached_cpppath) > 0:
            print(f"   📄 Gespeicherte CPPPATH (erste 5):")
            for i, path in enumerate(cached_cpppath[:5]):
                print(f"      {i+1}: {path} ({type(path).__name__})")
        
        # Prüfe auf lib-Pfade im Cache
        project_dir = env.get('PROJECT_DIR', '')
        cached_lib_paths = []
        if project_dir:
            for path in cached_cpppath:
                path_str = str(path)
                if '/lib/' in path_str and project_dir in path_str:
                    cached_lib_paths.append(path_str)
        
        print(f"   📚 Lib-Pfade im Cache: {len(cached_lib_paths)}")
        for i, lib_path in enumerate(cached_lib_paths[:3]):
            rel_path = os.path.relpath(lib_path, project_dir) if project_dir else lib_path
            print(f"      {i+1}: {rel_path}")
        
        # Wiederherstellung ausführen
        print(f"   🔄 Führe Environment-Wiederherstellung aus...")
        
        # Prüfe restore_environment Funktion
        if hasattr(env_module, 'restore_environment'):
            print(f"   ✅ restore_environment Funktion gefunden")
            
            try:
                success = env_module.restore_environment(env)
                print(f"   📊 Wiederherstellung Return-Wert: {success}")
            except Exception as e:
                print(f"   ❌ Wiederherstellung-Fehler: {e}")
                return False
        else:
            print(f"   ❌ restore_environment Funktion NICHT gefunden!")
            return False
        
        # CPPPATH nach Wiederherstellung prüfen
        cpppath_after = list(env.get('CPPPATH', []))
        print(f"   📊 CPPPATH nach Wiederherstellung: {len(cpppath_after)} Einträge")
        
        # Detaillierter Vergleich
        if len(cpppath_after) > len(cpppath_before):
            added_count = len(cpppath_after) - len(cpppath_before)
            print(f"   ✅ CPPPATH wurde erweitert: +{added_count} Pfade")
            
            # Zeige hinzugefügte Pfade
            if len(cpppath_after) > len(cpppath_before):
                added_paths = cpppath_after[len(cpppath_before):]
                print(f"   📄 Hinzugefügte Pfade:")
                for i, path in enumerate(added_paths[:5]):
                    path_str = str(path.abspath) if hasattr(path, 'abspath') else str(path)
                    print(f"      +{i+1}: {path_str}")
            
            return True
        elif len(cpppath_after) == len(cpppath_before):
            print(f"   ⚠ CPPPATH-Länge unverändert - prüfe Inhalt...")
            
            # Prüfe ob Inhalte unterschiedlich sind
            before_set = set(str(p.abspath) if hasattr(p, 'abspath') else str(p) for p in cpppath_before)
            after_set = set(str(p.abspath) if hasattr(p, 'abspath') else str(p) for p in cpppath_after)
            
            if before_set != after_set:
                print(f"   ✅ CPPPATH-Inhalte wurden geändert")
                new_paths = after_set - before_set
                print(f"   📄 Neue Pfade: {len(new_paths)}")
                for i, path in enumerate(list(new_paths)[:3]):
                    print(f"      +{i+1}: {path}")
                return True
            else:
                print(f"   ❌ CPPPATH-Inhalte unverändert!")
                return False
        else:
            print(f"   ❌ CPPPATH wurde verkürzt! ({len(cpppath_before)} -> {len(cpppath_after)})")
            return False
        
    except Exception as e:
        print(f"   ❌ Debug-Wiederherstellung fehlgeschlagen: {e}")
        import traceback
        print(f"   📄 Traceback: {traceback.format_exc()}")
        return False

def debug_scons_variable_types_detailed():
    """Detaillierte Debug-Analyse der SCons-Variable-Typen"""
    
    print(f"\n🔍 DETAILLIERTE SCONS-VARIABLE-TYPEN-DEBUG:")
    
    # Aktuelle CPPPATH analysieren
    current_cpppath = env.get('CPPPATH', [])
    print(f"   📊 Aktuelle CPPPATH: {len(current_cpppath)} Einträge")
    print(f"   📊 CPPPATH-Typ: {type(current_cpppath).__name__}")
    
    if current_cpppath:
        # Analysiere Typen der ersten 5 Einträge
        print(f"   📄 CPPPATH-Einträge-Typen:")
        for i, item in enumerate(current_cpppath[:5]):
            item_type = type(item).__name__
            item_class = str(item.__class__)
            
            if hasattr(item, 'abspath'):
                item_value = str(item.abspath)
                print(f"      {i+1}: {item_type} ({item_class})")
                print(f"          -> abspath: {item_value}")
                print(f"          -> str: {str(item)}")
            else:
                item_value = str(item)
                print(f"      {i+1}: {item_type} -> {item_value}")
    
    # Prüfe andere kritische Variablen
    critical_vars = ['LIBS', 'LIBPATH', 'CCFLAGS', 'CXXFLAGS', 'BUILD_FLAGS']
    for var in critical_vars:
        value = env.get(var, None)
        if value is not None:
            if hasattr(value, '__len__'):
                print(f"   📊 {var}: {type(value).__name__} mit {len(value)} Einträgen")
            else:
                print(f"   📊 {var}: {type(value).__name__} = {value}")
    
    # Prüfe Cache-Datei-Inhalt
    cache_file = get_cache_file_path()
    if os.path.exists(cache_file):
        try:
            spec = importlib.util.spec_from_file_location("scons_env_cache", cache_file)
            env_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(env_module)
            
            comprehensive_data = getattr(env_module, 'COMPREHENSIVE_DATA', {})
            all_env_vars = comprehensive_data.get('all_environment_vars', {})
            cached_cpppath = all_env_vars.get('CPPPATH', [])
            
            print(f"   💾 Cache-CPPPATH-Typen:")
            print(f"      📊 Cache-CPPPATH: {type(cached_cpppath).__name__} mit {len(cached_cpppath)} Einträgen")
            
            for i, item in enumerate(cached_cpppath[:5]):
                item_type = type(item).__name__
                print(f"      {i+1}: {item_type} -> {item}")
                
                # Problem: Sind alle Cache-Einträge Strings?
                if not isinstance(item, str):
                    print(f"         ⚠ Nicht-String-Typ im Cache: {item_type}")
        
        except Exception as e:
            print(f"   ❌ Cache-Analyse fehlgeschlagen: {e}")

def test_manual_cpppath_extension():
    """Testet manuelle CPPPATH-Erweiterung"""
    
    print(f"\n🧪 TEST: MANUELLE CPPPATH-ERWEITERUNG:")
    
    # Aktuelle CPPPATH
    current_cpppath = list(env.get('CPPPATH', []))
    print(f"   📊 Aktuelle CPPPATH: {len(current_cpppath)} Einträge")
    
    # Füge Test-Pfad hinzu
    project_dir = env.get('PROJECT_DIR', '')
    test_lib_path = os.path.join(project_dir, 'lib', 'test_lib_debug')
    
    print(f"   🧪 Füge Test-Pfad hinzu: {test_lib_path}")
    
    try:
        # Verschiedene Methoden testen
        print(f"   🔄 Teste verschiedene CPPPATH-Erweiterungsmethoden:")
        
        # Methode 1: Direkte Zuweisung
        print(f"      1. Direkte Zuweisung...")
        extended_cpppath = current_cpppath + [test_lib_path]
        env['CPPPATH'] = extended_cpppath
        
        new_cpppath_1 = list(env.get('CPPPATH', []))
        success_1 = len(new_cpppath_1) > len(current_cpppath)
        print(f"         Erfolg: {success_1} ({len(current_cpppath)} -> {len(new_cpppath_1)})")
        
        # Methode 2: Append
        if not success_1:
            print(f"      2. env.Append...")
            env.Append(CPPPATH=[test_lib_path + "_append"])
            
            new_cpppath_2 = list(env.get('CPPPATH', []))
            success_2 = len(new_cpppath_2) > len(new_cpppath_1)
            print(f"         Erfolg: {success_2} ({len(new_cpppath_1)} -> {len(new_cpppath_2)})")
        
        # Methode 3: PrependUnique
        if not success_1:
            print(f"      3. env.PrependUnique...")
            env.PrependUnique(CPPPATH=[test_lib_path + "_prepend"])
            
            new_cpppath_3 = list(env.get('CPPPATH', []))
            success_3 = len(new_cpppath_3) > len(current_cpppath)
            print(f"         Erfolg: {success_3} ({len(current_cpppath)} -> {len(new_cpppath_3)})")
        
        # Finale CPPPATH prüfen
        final_cpppath = list(env.get('CPPPATH', []))
        final_success = len(final_cpppath) > len(current_cpppath)
        
        print(f"   📊 Finale CPPPATH: {len(final_cpppath)} Einträge")
        print(f"   ✅ Manuelle CPPPATH-Erweiterung funktioniert: {final_success}")
        
        if final_success:
            # Zeige hinzugefügte Pfade
            added_paths = final_cpppath[len(current_cpppath):]
            print(f"   📄 Hinzugefügte Test-Pfade:")
            for i, path in enumerate(added_paths):
                path_str = str(path.abspath) if hasattr(path, 'abspath') else str(path)
                print(f"      +{i+1}: {path_str}")
        
        return final_success
        
    except Exception as e:
        print(f"   ❌ Manuelle CPPPATH-Erweiterung fehlgeschlagen: {e}")
        return False

def debug_cache_file_content():
    """Debuggt den Cache-Datei-Inhalt im Detail"""
    
    cache_file = get_cache_file_path()
    if not os.path.exists(cache_file):
        print(f"❌ Cache-Datei existiert nicht für Debug")
        return
    
    print(f"\n📄 CACHE-DATEI-INHALT-DEBUG:")
    print(f"   📁 Datei: {cache_file}")
    print(f"   📊 Größe: {os.path.getsize(cache_file)} Bytes")
    
    try:
        # Erste 20 Zeilen der Cache-Datei lesen
        with open(cache_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        print(f"   📄 Erste 10 Zeilen:")
        for i, line in enumerate(lines[:10]):
            print(f"      {i+1:2d}: {line.rstrip()}")
        
        # Suche nach COMPREHENSIVE_DATA
        comprehensive_line = None
        for i, line in enumerate(lines):
            if 'COMPREHENSIVE_DATA' in line:
                comprehensive_line = i
                break
        
        if comprehensive_line:
            print(f"   📊 COMPREHENSIVE_DATA gefunden in Zeile {comprehensive_line + 1}")
        else:
            print(f"   ❌ COMPREHENSIVE_DATA NICHT gefunden!")
        
        # Suche nach restore_environment
        restore_line = None
        for i, line in enumerate(lines):
            if 'def restore_environment' in line:
                restore_line = i
                break
        
        if restore_line:
            print(f"   📊 restore_environment Funktion gefunden in Zeile {restore_line + 1}")
            # Zeige die Funktion
            print(f"   📄 restore_environment (erste 5 Zeilen):")
            for j in range(5):
                if restore_line + j < len(lines):
                    print(f"      {restore_line + j + 1:2d}: {lines[restore_line + j].rstrip()}")
        else:
            print(f"   ❌ restore_environment Funktion NICHT gefunden!")
    
    except Exception as e:
        print(f"   ❌ Cache-Datei-Lesen fehlgeschlagen: {e}")

def focused_debug_analysis():
    """Fokussierte Debug-Analyse auf Problem 1 (Environment-Wiederherstellung)"""
    
    print(f"\n🎯 FOKUSSIERTE DEBUG-ANALYSE (Environment-Wiederherstellung):")
    
    # Debug 1: Cache-Datei-Inhalt
    debug_cache_file_content()
    
    # Debug 2: SCons-Variable-Typen
    debug_scons_variable_types_detailed()
    
    # Debug 3: Manuelle CPPPATH-Erweiterung
    manual_works = test_manual_cpppath_extension()
    
    # Debug 4: Environment-Wiederherstellung (Haupttest)
    restoration_works = debug_environment_restoration_detailed()
    
    print(f"\n📊 FOKUSSIERTE DEBUG-ZUSAMMENFASSUNG:")
    print(f"   🧪 Manuelle CPPPATH-Erweiterung funktioniert: {manual_works}")
    print(f"   🔄 Environment-Wiederherstellung funktioniert: {restoration_works}")
    
    if not manual_works:
        print(f"   🎯 GRUNDPROBLEM: SCons-CPPPATH kann nicht erweitert werden!")
        print(f"      -> SCons-Environment ist read-only oder gesperrt")
    elif not restoration_works:
        print(f"   🎯 HAUPTPROBLEM: Environment-Wiederherstellung funktioniert nicht!")
        print(f"      -> Cache-Daten werden nicht korrekt in Environment geladen")
    else:
        print(f"   ✅ Beide Tests funktionieren - Problem liegt woanders")
        print(f"      -> Möglicherweise Timing oder andere Ursache")

def capture_all_include_related_variables():
    """Erfasst ALLE möglichen SCons-Variablen mit Include-Informationen"""
    
    # Alle potentiellen Include-Variablen
    include_vars = [
        # Primäre Include-Variablen
        'CPPPATH', 'CCFLAGS', 'CXXFLAGS', 'CPPFLAGS',
        
        # Interne SCons Include-Variablen
        '_CPPINCFLAGS', 'INCPREFIX', 'INCSUFFIX',
        
        # Build-Flags die Include-Pfade enthalten können
        'BUILD_FLAGS', 'SRC_BUILD_FLAGS',
        
        # Framework-spezifische Variablen
        'FRAMEWORK_DIR', 'FRAMEWORKPATH',
        
        # Library-Variablen
        'LIBPATH', 'LIBS', '_LIBFLAGS', '_LIBDIRFLAGS',
        
        # PlatformIO-spezifische Variablen
        'PIOBUILDFILES', 'LIB_DEPS', 'LIB_EXTRA_DIRS',
        'LIBSOURCE_DIRS', 'PROJECT_LIBDEPS_DIR',
        
        # Weitere potentielle Variablen
        'ASFLAGS', 'LINKFLAGS', 'SHLINKFLAGS',
        
        # Compiler-spezifische Variablen
        'CFLAGS', 'CXXFLAGS', 'ASFLAGS',
        
        # Preprocessor-Variablen
        'CPPDEFINES', 'CPPDEFPREFIX', 'CPPDEFSUFFIX'
    ]
    
    print(f"\n🔍 VOLLSTÄNDIGE INCLUDE-VARIABLE-ANALYSE:")
    
    all_include_paths = set()
    project_dir = env.get('PROJECT_DIR', '')
    variable_analysis = {}
    
    for var in include_vars:
        raw_value = env.get(var, None)
        
        if raw_value is None:
            continue
            
        print(f"\n   📊 {var}:")
        variable_info = {
            'type': type(raw_value).__name__,
            'content': [],
            'lib_paths_found': []
        }
        
        # Analysiere verschiedene Datentypen
        if isinstance(raw_value, list):
            print(f"      Typ: Liste mit {len(raw_value)} Einträgen")
            variable_info['count'] = len(raw_value)
            
            for i, item in enumerate(raw_value):
                item_str = str(item.abspath) if hasattr(item, 'abspath') else str(item)
                variable_info['content'].append(item_str)
                
                # Suche nach Include-Pfaden (weniger restriktiv für Debug)
                if any(pattern in item_str for pattern in ['/include', '/lib/', '-I']):
                    is_project_lib = project_dir and '/lib/' in item_str and project_dir in item_str
                    marker = "📚 PROJEKT-LIB" if is_project_lib else "📁 INCLUDE"
                    
                    if i < 10:  # Nur erste 10 anzeigen
                        print(f"         {i}: {marker} {item_str}")
                    
                    if is_project_lib:
                        all_include_paths.add(item_str)
                        variable_info['lib_paths_found'].append(item_str)
                else:
                    if i < 5:  # Nur erste 5 andere anzeigen
                        print(f"         {i}: {item_str}")
        
        elif isinstance(raw_value, str):
            print(f"      Typ: String")
            variable_info['content'] = raw_value
            print(f"         {raw_value}")
            
            # Suche nach -I Flags in String
            if '-I' in raw_value:
                include_matches = re.findall(r'-I\s*([^\s]+)', raw_value)
                for match in include_matches:
                    if project_dir and '/lib/' in match and project_dir in match:
                        print(f"         📚 PROJEKT-LIB in String: {match}")
                        all_include_paths.add(match)
                        variable_info['lib_paths_found'].append(match)
        
        else:
            print(f"      Typ: {type(raw_value).__name__}")
            variable_info['content'] = str(raw_value)
            
            # Versuche String-Konvertierung für Pfad-Suche
            try:
                value_str = str(raw_value)
                if project_dir and '/lib/' in value_str and project_dir in value_str:
                    print(f"         📚 PROJEKT-LIB gefunden: {value_str}")
                    all_include_paths.add(value_str)
                    variable_info['lib_paths_found'].append(value_str)
                else:
                    print(f"         {value_str}")
            except:
                print(f"         <Nicht konvertierbar>")
        
        variable_analysis[var] = variable_info
    
    print(f"\n   📚 GEFUNDENE PROJEKT-LIB-PFADE: {len(all_include_paths)}")
    for path in sorted(all_include_paths):
        rel_path = os.path.relpath(path, project_dir) if project_dir else path
        print(f"      ✓ {rel_path}")
    
    return all_include_paths, variable_analysis

def capture_internal_scons_variables():
    """Erfasst auch interne SCons-Variablen"""
    
    print(f"\n🔧 INTERNE SCONS-VARIABLEN:")
    
    # Interne Variablen die aufbereitete Flags enthalten
    internal_vars = [
        '_CPPINCFLAGS',    # Aufbereitete Include-Flags
        '_LIBFLAGS',       # Aufbereitete Library-Flags  
        '_LIBDIRFLAGS',    # Library-Directory-Flags
        'SPAWN',           # Command-Spawning-Funktion
        'TEMPFILE',        # Temporary-File-Handling
        '_CPPDEFFLAGS',    # Define-Flags
        '_FRAMEWORKPATH',  # Framework-Pfade
    ]
    
    internal_analysis = {}
    
    for var in internal_vars:
        value = env.get(var, None)
        if value is not None:
            print(f"   {var}: {type(value).__name__}")
            
            # Spezielle Behandlung für _CPPINCFLAGS
            if var == '_CPPINCFLAGS':
                try:
                    # _CPPINCFLAGS ist oft eine Funktion/Callable
                    if callable(value):
                        print(f"      Callable - versuche Aufruf...")
                        try:
                            cpppath = env.get('CPPPATH', [])
                            incprefix = env.get('INCPREFIX', '-I')
                            incsuffix = env.get('INCSUFFIX', '')
                            result = value(cpppath, incprefix, incsuffix, env)
                            print(f"      Ergebnis: {result}")
                            internal_analysis[var] = str(result)
                        except Exception as e:
                            print(f"      Aufruf fehlgeschlagen: {e}")
                            internal_analysis[var] = f"<Callable-Error: {e}>"
                    else:
                        print(f"      Wert: {value}")
                        internal_analysis[var] = str(value)
                except Exception as e:
                    print(f"      Fehler beim Verarbeiten: {e}")
                    internal_analysis[var] = f"<Error: {e}>"
            else:
                try:
                    internal_analysis[var] = convert_scons_objects_selective(value, var)
                    if isinstance(value, (list, tuple)) and len(value) > 0:
                        print(f"      {len(value)} Einträge")
                    else:
                        print(f"      {value}")
                except Exception as e:
                    print(f"      Konvertierungsfehler: {e}")
                    internal_analysis[var] = f"<Conversion-Error: {e}>"
    
    return internal_analysis

def comprehensive_environment_scan():
    """Vollständige Environment-Durchsuchung nach lib-Pfaden"""
    
    print(f"\n🔍 VOLLSTÄNDIGE ENVIRONMENT-DURCHSUCHUNG:")
    
    project_dir = env.get('PROJECT_DIR', '')
    additional_lib_paths = set()
    environment_vars = {}
    
    # Durchsuche ALLE Environment-Variablen
    try:
        env_dict = dict(env)
        total_vars = len(env_dict)
        print(f"   📊 Durchsuche {total_vars} Environment-Variablen...")
        
        lib_containing_vars = []
        
        for key, value in env_dict.items():
            try:
                # Konvertiere Wert zu String für Suche
                if hasattr(value, 'abspath'):
                    value_str = str(value.abspath)
                elif isinstance(value, (list, tuple)):
                    value_str = ' '.join(str(item.abspath) if hasattr(item, 'abspath') else str(item) for item in value)
                else:
                    value_str = str(value)
                
                # Suche nach Projekt-lib-Pfaden (weniger restriktiv für Debug)
                if project_dir and '/lib/' in value_str and project_dir in value_str:
                    lib_containing_vars.append(key)
                    
                    # Extrahiere spezifische Pfade
                    if isinstance(value, (list, tuple)):
                        for item in value:
                            item_str = str(item.abspath) if hasattr(item, 'abspath') else str(item)
                            if project_dir in item_str and '/lib/' in item_str:
                                additional_lib_paths.add(item_str)
                    else:
                        if project_dir in value_str and '/lib/' in value_str:
                            additional_lib_paths.add(value_str)
                
                # Speichere alle Variablen für späteren Export
                environment_vars[key] = convert_scons_objects_selective(value, key)
                
            except Exception as e:
                # Fehlerhafte Variablen überspringen
                environment_vars[key] = f"<Error: {e}>"
                continue
        
        print(f"   📚 Variablen mit lib-Pfaden: {len(lib_containing_vars)}")
        for var in lib_containing_vars:
            print(f"      📦 {var}")
        
        print(f"   📊 ZUSÄTZLICHE LIB-PFADE: {len(additional_lib_paths)}")
        for path in sorted(additional_lib_paths):
            rel_path = os.path.relpath(path, project_dir) if project_dir else path
            print(f"      ✓ {rel_path}")
    
    except Exception as e:
        print(f"   ❌ Environment-Durchsuchung fehlgeschlagen: {e}")
    
    return additional_lib_paths, environment_vars

def comprehensive_variable_capture():
    """Umfassende Erfassung aller relevanten SCons-Variablen"""
    
    print(f"\n🎯 UMFASSENDE SCONS-VARIABLE-ERFASSUNG:")
    
    # 1. Standard Include-Analyse
    project_lib_paths, variable_analysis = capture_all_include_related_variables()
    
    # 2. Interne SCons-Variablen
    internal_analysis = capture_internal_scons_variables()
    
    # 3. Vollständige Environment-Durchsuchung
    additional_lib_paths, all_environment_vars = comprehensive_environment_scan()
    
    # 4. Kombiniere alle gefundenen lib-Pfade
    all_lib_paths = project_lib_paths.union(additional_lib_paths)
    
    print(f"\n   📊 ZUSAMMENFASSUNG:")
    print(f"      📚 Gesamt lib-Pfade gefunden: {len(all_lib_paths)}")
    print(f"      📋 Analysierte Variablen: {len(variable_analysis)}")
    print(f"      🔧 Interne Variablen: {len(internal_analysis)}")
    print(f"      🌐 Gesamt Environment-Variablen: {len(all_environment_vars)}")
    
    return {
        'lib_paths': all_lib_paths,
        'variable_analysis': variable_analysis,
        'internal_analysis': internal_analysis,
        'all_environment_vars': all_environment_vars
    }

def freeze_comprehensive_scons_configuration(comprehensive_data):
    """Speichert umfassende SCons-Environment-Daten"""
    cache_file = get_cache_file_path()
    temp_file = cache_file + ".tmp"
    
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write("#!/usr/bin/env python3\n")
            f.write("# -*- coding: utf-8 -*-\n")
            f.write('"""\n')
            f.write('PlatformIO LDF SCons Variables Export - Umfassende Erfassung mit Debug\n')
            f.write(f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'Environment: {env.get("PIOENV")}\n')
            f.write('"""\n\n')
            
            # Umfassende Daten
            f.write('# Umfassende SCons Environment Daten\n')
            f.write('COMPREHENSIVE_DATA = ')
            f.write(repr(comprehensive_data))
            f.write('\n\n')
            
            # Verbesserte Restore-Funktion mit Debug
            f.write('def restore_environment(target_env):\n')
            f.write('    """Stellt umfassende SCons-Environment wieder her (mit Debug)"""\n')
            f.write('    restored_count = 0\n')
            f.write('    failed_count = 0\n')
            f.write('    \n')
            f.write('    print("🔄 Starte Environment-Wiederherstellung...")\n')
            f.write('    \n')
            f.write('    # Alle Environment-Variablen wiederherstellen\n')
            f.write('    all_vars = COMPREHENSIVE_DATA.get("all_environment_vars", {})\n')
            f.write('    print(f"   📊 Wiederherzustellende Variablen: {len(all_vars)}")\n')
            f.write('    \n')
            f.write('    for key, value in all_vars.items():\n')
            f.write('        try:\n')
            f.write('            # Überspringe problematische Variablen\n')
            f.write('            if key.startswith("__") or "function" in str(type(value)).lower():\n')
            f.write('                continue\n')
            f.write('            \n')
            f.write('            # Spezielle Behandlung für CPPPATH\n')
            f.write('            if key == "CPPPATH":\n')
            f.write('                print(f"   📁 Stelle CPPPATH wieder her: {len(value)} Einträge")\n')
            f.write('                target_env[key] = value\n')
            f.write('                restored_count += 1\n')
            f.write('            # Andere wichtige Variablen\n')
            f.write('            elif key in ["LIBS", "LIBPATH", "CCFLAGS", "CXXFLAGS", "BUILD_FLAGS"]:\n')
            f.write('                target_env[key] = value\n')
            f.write('                restored_count += 1\n')
            f.write('            # Alle anderen Variablen\n')
            f.write('            elif not key.startswith("_") or key in ["_CPPINCFLAGS", "_LIBFLAGS"]:\n')
            f.write('                target_env[key] = value\n')
            f.write('                restored_count += 1\n')
            f.write('        except Exception as e:\n')
            f.write('            failed_count += 1\n')
            f.write('            if key == "CPPPATH":\n')
            f.write('                print(f"   ❌ CPPPATH-Wiederherstellung fehlgeschlagen: {e}")\n')
            f.write('    \n')
            f.write('    lib_paths = COMPREHENSIVE_DATA.get("lib_paths", [])\n')
            f.write('    print(f"   ✅ {restored_count} Variablen wiederhergestellt")\n')
            f.write('    print(f"   ❌ {failed_count} Variablen fehlgeschlagen")\n')
            f.write('    print(f"   📚 {len(lib_paths)} Projekt-lib-Pfade verfügbar")\n')
            f.write('    \n')
            f.write('    # Prüfe ob CPPPATH erfolgreich wiederhergestellt wurde\n')
            f.write('    final_cpppath = target_env.get("CPPPATH", [])\n')
            f.write('    print(f"   📊 Finale CPPPATH: {len(final_cpppath)} Einträge")\n')
            f.write('    \n')
            f.write('    return restored_count > 10 and len(final_cpppath) > 5\n')
            f.write('\n')
            
            # Convenience-Funktionen
            f.write('def get_all_lib_paths():\n')
            f.write('    """Gibt alle gefundenen lib-Pfade zurück"""\n')
            f.write('    return list(COMPREHENSIVE_DATA.get("lib_paths", []))\n\n')
            
            f.write('def get_variable_analysis():\n')
            f.write('    """Gibt Variable-Analyse zurück"""\n')
            f.write('    return COMPREHENSIVE_DATA.get("variable_analysis", {})\n\n')
            
            f.write('def get_internal_analysis():\n')
            f.write('    """Gibt interne Variable-Analyse zurück"""\n')
            f.write('    return COMPREHENSIVE_DATA.get("internal_analysis", {})\n\n')
            
            # Metadaten
            f.write('# Metadata\n')
            f.write(f'CONFIG_HASH = {repr(calculate_config_hash())}\n')
            f.write(f'ENV_NAME = {repr(env.get("PIOENV"))}\n')
            f.write(f'TOTAL_VARIABLES = {len(comprehensive_data.get("all_environment_vars", {}))}\n')
            f.write(f'LIB_PATHS_FOUND = {len(comprehensive_data.get("lib_paths", []))}\n')
            f.write(f'COMPREHENSIVE_CAPTURE = True\n')
            f.write(f'DEBUG_VERSION = True\n')
            
            # Main-Block
            f.write('\nif __name__ == "__main__":\n')
            f.write('    print("PlatformIO LDF SCons Variables Export (Umfassend mit Debug)")\n')
            f.write('    lib_paths = get_all_lib_paths()\n')
            f.write('    var_analysis = get_variable_analysis()\n')
            f.write('    print(f"Projekt-lib-Pfade: {len(lib_paths)}")\n')
            f.write('    print(f"Analysierte Variablen: {len(var_analysis)}")\n')
            f.write('    if lib_paths:\n')
            f.write('        print("Gefundene lib-Pfade:")\n')
            f.write('        for path in lib_paths:\n')
            f.write('            print(f"  {path}")\n')
        
        # Atomarer Move
        shutil.move(temp_file, cache_file)
        
        # JSON-Export zusätzlich
        json_file = cache_file.replace('.py', '.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(comprehensive_data, f, indent=2, ensure_ascii=False, default=str)
        
        file_size = os.path.getsize(cache_file)
        lib_paths_count = len(comprehensive_data.get('lib_paths', []))
        
        print(f"✓ Umfassende SCons-Environment gespeichert:")
        print(f"   📁 {os.path.basename(cache_file)} ({file_size} Bytes)")
        print(f"   📊 {len(comprehensive_data.get('all_environment_vars', {}))} Environment-Variablen")
        print(f"   📚 {lib_paths_count} Projekt-lib-Pfade")
        print(f"   📋 JSON-Export: {os.path.basename(json_file)}")
        print(f"   🔍 Debug-Version mit verbesserter Wiederherstellung")
        
        return True
        
    except Exception as e:
        print(f"❌ Umfassende Environment-Speicherung fehlgeschlagen: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def restore_comprehensive_scons_configuration():
    """Lädt umfassende Environment aus Python-Datei"""
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
        
        # Prüfe ob umfassende Erfassung
        comprehensive_capture = getattr(env_module, 'COMPREHENSIVE_CAPTURE', False)
        debug_version = getattr(env_module, 'DEBUG_VERSION', False)
        
        if comprehensive_capture:
            print("✅ Cache stammt von umfassender SCons-Variable-Erfassung")
        if debug_version:
            print("✅ Cache enthält Debug-Version mit verbesserter Wiederherstellung")
        
        # Environment wiederherstellen
        success = env_module.restore_environment(env)
        
        if success:
            total_vars = getattr(env_module, 'TOTAL_VARIABLES', 0)
            lib_paths_found = getattr(env_module, 'LIB_PATHS_FOUND', 0)
            
            print(f"✓ Umfassende Environment wiederhergestellt:")
            print(f"   📊 {total_vars} Environment-Variablen")
            print(f"   📚 {lib_paths_found} Projekt-lib-Pfade")
            print(f"   ✅ Umfassende SCons-Variable-Erfassung mit Debug")
        
        return success
        
    except Exception as e:
        print(f"❌ Umfassende Cache-Wiederherstellung fehlgeschlagen: {e}")
        return False

def early_cache_check_and_restore():
    """Prüft Cache und stellt umfassende SCons-Environment wieder her"""
    print(f"🔍 Cache-Prüfung (umfassende SCons-Variable-Erfassung mit Debug)...")
    
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        print(f"📝 Kein umfassender Cache - LDF wird normal ausgeführt")
        return False
    
    current_ldf_mode = get_current_ldf_mode(env.get("PIOENV"))
    
    if current_ldf_mode != 'off':
        print(f"🔄 LDF noch aktiv - umfassender Cache wird nach Build erstellt")
        return False
    
    print(f"⚡ Umfassender Cache verfügbar - stelle Environment wieder her")
    
    success = restore_comprehensive_scons_configuration()
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

def comprehensive_environment_capture(target, source, env):
    """Umfassende Environment-Erfassung mit allen SCons-Variablen"""
    global _backup_created
    
    if _backup_created:
        print("✓ Environment bereits erfasst - überspringe umfassende Erfassung")
        return None
    
    try:
        print(f"\n🎯 UMFASSENDE ENVIRONMENT-ERFASSUNG MIT DEBUG:")
        print(f"   Target: {[str(t) for t in target]}")
        print(f"   🕐 Timing: VOR Linken - alle SCons-Variablen verfügbar")
        
        # Umfassende Variable-Erfassung
        comprehensive_data = comprehensive_variable_capture()
        
        lib_paths_count = len(comprehensive_data.get('lib_paths', []))
        total_vars = len(comprehensive_data.get('all_environment_vars', {}))
        
        print(f"\n   📊 ERFASSUNG ABGESCHLOSSEN:")
        print(f"      📚 Projekt-lib-Pfade: {lib_paths_count}")
        print(f"      📋 Environment-Variablen: {total_vars}")
        
        if total_vars > 50:  # Realistische Anzahl für vollständiges Environment
            if freeze_comprehensive_scons_configuration(comprehensive_data):
                env_name = env.get("PIOENV")
                if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                    print(f"🚀 Umfassende Environment-Erfassung mit Debug erfolgreich!")
                    _backup_created = True
                else:
                    print(f"⚠ lib_ldf_mode konnte nicht gesetzt werden")
            else:
                print(f"❌ Environment-Speicherung fehlgeschlagen")
        else:
            print(f"⚠ Zu wenige Environment-Variablen ({total_vars})")
        
    except Exception as e:
        print(f"❌ Umfassende Environment-Erfassung Fehler: {e}")
    
    return None

# =============================================================================
# HAUPTLOGIK - UMFASSENDE SCONS-VARIABLE-ERFASSUNG MIT DEBUG
# =============================================================================

print(f"\n🎯 Umfassende SCons-Variable-Erfassung mit Debug für: {env.get('PIOENV')}")

# Cache-Prüfung und umfassende SCons-Environment-Wiederherstellung
cache_restored = early_cache_check_and_restore()

if cache_restored:
    print(f"🚀 Build mit umfassender Environment-Cache - LDF übersprungen!")
    
    # Führe fokussierte Debug-Analyse durch
    focused_debug_analysis()

else:
    print(f"📝 Normaler LDF-Durchlauf - umfassende Variable-Erfassung mit Debug...")
    
    # Pre-Link Hook für umfassende Environment-Erfassung
    env.AddPreAction("$BUILD_DIR/${PROGNAME}.elf", comprehensive_environment_capture)
    print(f"✅ Pre-Link Hook für umfassende SCons-Variable-Erfassung registriert")
    print(f"🔍 Erfasst ALLE SCons-Variablen inkl. interne und lib-spezifische")

print(f"🏁 Umfassende SCons-Variable-Erfassung mit Debug initialisiert")
print(f"💡 Reset: rm -rf .pio/ldf_cache/")
print(f"📊 Erfasst: Alle Environment-Variablen + Include-Variablen + interne SCons-Variablen")
print(f"🔍 Sucht: Projekt-lib-Pfade in ALLEN verfügbaren SCons-Variablen")
print(f"🐛 Debug: Detaillierte Analyse der Environment-Wiederherstellung\n")
