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

def capture_dynamic_include_paths():
    """Erfasst zur Laufzeit generierte Include-Pfade"""
    print(f"\n🔄 DYNAMISCHE INCLUDE-PFAD-ERFASSUNG:")
    
    dynamic_paths = set()
    
    # Prüfe ob CPPPATH-Modifier existieren
    cpppath_modifiers = [
        'PrependUnique', 'AppendUnique', 'Prepend', 'Append'
    ]
    
    for modifier in cpppath_modifiers:
        if hasattr(env, modifier):
            print(f"   🔄 CPPPATH-Modifier gefunden: {modifier}")
    
    # Erfasse aktuelle CPPPATH nach allen Modifikationen
    final_cpppath = env.get('CPPPATH', [])
    if isinstance(final_cpppath, list):
        print(f"   📊 Finale CPPPATH-Einträge: {len(final_cpppath)}")
        for i, path in enumerate(final_cpppath):
            path_str = str(path.abspath) if hasattr(path, 'abspath') else str(path)
            dynamic_paths.add(path_str)
            if i < 5:  # Zeige erste 5
                print(f"      {i}: {path_str}")
    
    # Prüfe auf dynamisch generierte Framework-Pfade
    framework_dirs = env.get('FRAMEWORK_DIR', [])
    if framework_dirs:
        if isinstance(framework_dirs, list):
            for fdir in framework_dirs:
                fdir_str = str(fdir.abspath) if hasattr(fdir, 'abspath') else str(fdir)
                dynamic_paths.add(fdir_str)
        else:
            fdir_str = str(framework_dirs.abspath) if hasattr(framework_dirs, 'abspath') else str(framework_dirs)
            dynamic_paths.add(fdir_str)
    
    print(f"   ✅ Dynamische Pfade erfasst: {len(dynamic_paths)}")
    return dynamic_paths

def capture_all_include_related_variables():
    """Erfasst ALLE möglichen SCons-Variablen mit Include-Informationen - ERWEITERT"""
    
    # Erweiterte Include-Variablen-Liste
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
        
        # KRITISCH: Neue wichtige Variablen
        'CPPPATH_DYNAMIC',      # Dynamisch generierte Include-Pfade
        'EXTRA_LIB_DIRS',       # Zusätzliche Library-Verzeichnisse
        'BUILD_UNFLAGS',        # Entfernte Flags (wichtig!)
        'SRC_FILTER',           # Source-Filter (kann Pfade beeinflussen)
        'LIB_IGNORE',           # Ignorierte Libraries
        'UPLOAD_PROTOCOL',      # Kann Include-Pfade beeinflussen
        
        # ESP32-spezifische Variablen
        'ESP32_EXCEPTION_DEBUG', 
        'ARDUINO_VARIANT',
        'BOARD_MCU',
        
        # Compiler-Toolchain-Variablen
        'CC', 'CXX', 'AR', 'RANLIB',
        'CCCOM', 'CXXCOM', 'LINKCOM',
        
        # Weitere potentielle Variablen
        'ASFLAGS', 'LINKFLAGS', 'SHLINKFLAGS',
        
        # Compiler-spezifische Variablen
        'CFLAGS', 'CXXFLAGS', 'ASFLAGS',
        
        # Preprocessor-Variablen
        'CPPDEFINES', 'CPPDEFPREFIX', 'CPPDEFSUFFIX'
    ]
    
    print(f"\n🔍 ERWEITERTE INCLUDE-VARIABLE-ANALYSE:")
    
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
                
                # Suche nach Include-Pfaden
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
    
    # Erweiterte interne Variablen
    internal_vars = [
        '_CPPINCFLAGS',    # Aufbereitete Include-Flags
        '_LIBFLAGS',       # Aufbereitete Library-Flags  
        '_LIBDIRFLAGS',    # Library-Directory-Flags
        'SPAWN',           # Command-Spawning-Funktion
        'TEMPFILE',        # Temporary-File-Handling
        '_CPPDEFFLAGS',    # Define-Flags
        '_FRAMEWORKPATH',  # Framework-Pfade
        '_CCCOMCOM',       # Compiler-Command-Common
        '_CXXCOMCOM',      # CXX-Compiler-Command-Common
        '_LINKCOM',        # Linker-Command
        'BUILDERS',        # SCons-Builder
        'SCANNERS',        # SCons-Scanner
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
                
                # Suche nach Projekt-lib-Pfaden
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

def validate_restored_include_paths():
    """Validiert wiederhergestellte Include-Pfade"""
    print(f"\n🔍 INCLUDE-PFAD-VALIDIERUNG:")
    
    cpppath = env.get('CPPPATH', [])
    project_dir = env.get('PROJECT_DIR', '')
    
    valid_paths = 0
    invalid_paths = 0
    
    for path in cpppath:
        path_str = str(path.abspath) if hasattr(path, 'abspath') else str(path)
        
        if os.path.exists(path_str):
            valid_paths += 1
            if project_dir in path_str:
                print(f"   ✅ Projekt-Pfad: {os.path.relpath(path_str, project_dir)}")
        else:
            invalid_paths += 1
            print(f"   ❌ Ungültig: {path_str}")
    
    print(f"   📊 Gültige Pfade: {valid_paths}, Ungültige: {invalid_paths}")
    return invalid_paths == 0

def comprehensive_variable_capture():
    """Erweiterte umfassende Erfassung aller relevanten SCons-Variablen"""
    
    print(f"\n🎯 ERWEITERTE UMFASSENDE SCONS-VARIABLE-ERFASSUNG:")
    
    # 1. Erweiterte Include-Analyse
    project_lib_paths, variable_analysis = capture_all_include_related_variables()
    
    # 2. NEU: Dynamische Include-Pfade
    dynamic_paths = capture_dynamic_include_paths()
    
    # 3. Interne SCons-Variablen
    internal_analysis = capture_internal_scons_variables()
    
    # 4. Vollständige Environment-Durchsuchung
    additional_lib_paths, all_environment_vars = comprehensive_environment_scan()
    
    # 5. NEU: Include-Pfad-Validierung
    validate_restored_include_paths()
    
    # Kombiniere alle gefundenen lib-Pfade
    all_lib_paths = project_lib_paths.union(additional_lib_paths).union(dynamic_paths)
    
    print(f"\n   📊 ERWEITERTE ZUSAMMENFASSUNG:")
    print(f"      📚 Gesamt lib-Pfade gefunden: {len(all_lib_paths)}")
    print(f"      🔄 Dynamische Pfade: {len(dynamic_paths)}")
    print(f"      📋 Analysierte Variablen: {len(variable_analysis)}")
    print(f"      🔧 Interne Variablen: {len(internal_analysis)}")
    print(f"      🌐 Gesamt Environment-Variablen: {len(all_environment_vars)}")
    
    return {
        'lib_paths': all_lib_paths,
        'dynamic_paths': dynamic_paths,  # NEU
        'variable_analysis': variable_analysis,
        'internal_analysis': internal_analysis,
        'all_environment_vars': all_environment_vars
    }

def freeze_comprehensive_scons_configuration(comprehensive_data):
    """Speichert umfassende SCons-Environment-Daten mit verbesserter Restore-Funktion"""
    cache_file = get_cache_file_path()
    temp_file = cache_file + ".tmp"
    
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write("#!/usr/bin/env python3\n")
            f.write("# -*- coding: utf-8 -*-\n")
            f.write('"""\n')
            f.write('PlatformIO LDF SCons Variables Export - Erweiterte umfassende Erfassung\n')
            f.write(f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'Environment: {env.get("PIOENV")}\n')
            f.write('"""\n\n')
            
            f.write('import os\n\n')
            
            # Umfassende Daten
            f.write('# Erweiterte umfassende SCons Environment Daten\n')
            f.write('COMPREHENSIVE_DATA = ')
            f.write(repr(comprehensive_data))
            f.write('\n\n')
            
            # Verbesserte Restore-Funktion
            f.write('def restore_environment(target_env):\n')
            f.write('    """Stellt erweiterte umfassende SCons-Environment wieder her"""\n')
            f.write('    restored_count = 0\n')
            f.write('    critical_restored = 0\n')
            f.write('    \n')
            f.write('    # Kritische Variablen zuerst wiederherstellen\n')
            f.write('    critical_vars = [\n')
            f.write('        "CPPPATH", "CCFLAGS", "CXXFLAGS", "CPPFLAGS",\n')
            f.write('        "_CPPINCFLAGS", "INCPREFIX", "INCSUFFIX",\n')
            f.write('        "LIBPATH", "LIBS", "_LIBFLAGS",\n')
            f.write('        "FRAMEWORK_DIR", "FRAMEWORKPATH",\n')
            f.write('        "BUILD_FLAGS", "SRC_BUILD_FLAGS",\n')
            f.write('        "BOARD", "PLATFORM", "PIOENV",\n')
            f.write('        "CC", "CXX", "AR", "RANLIB"\n')
            f.write('    ]\n')
            f.write('    \n')
            f.write('    all_vars = COMPREHENSIVE_DATA.get("all_environment_vars", {})\n')
            f.write('    \n')
            f.write('    # 1. Kritische Variablen zuerst\n')
            f.write('    print("   🎯 Kritische Variablen wiederherstellen:")\n')
            f.write('    for var in critical_vars:\n')
            f.write('        if var in all_vars:\n')
            f.write('            try:\n')
            f.write('                target_env[var] = all_vars[var]\n')
            f.write('                critical_restored += 1\n')
            f.write('                print(f"      ✓ Kritisch: {var}")\n')
            f.write('            except Exception as e:\n')
            f.write('                print(f"      ❌ Kritisch fehlgeschlagen: {var} - {e}")\n')
            f.write('    \n')
            f.write('    # 2. Alle anderen Variablen\n')
            f.write('    print("   🌐 Weitere Variablen wiederherstellen:")\n')
            f.write('    for key, value in all_vars.items():\n')
            f.write('        if key not in critical_vars:\n')
            f.write('            try:\n')
            f.write('                if not key.startswith("__") and not callable(value):\n')
            f.write('                    target_env[key] = value\n')
            f.write('                    restored_count += 1\n')
            f.write('            except:\n')
            f.write('                pass  # Überspringe problematische Variablen\n')
            f.write('    \n')
            f.write('    # 3. Include-Pfad-Validierung\n')
            f.write('    print("   🔍 Include-Pfad-Validierung:")\n')
            f.write('    cpppath = target_env.get("CPPPATH", [])\n')
            f.write('    valid_paths = 0\n')
            f.write('    invalid_paths = 0\n')
            f.write('    \n')
            f.write('    for path in cpppath:\n')
            f.write('        path_str = str(path.abspath) if hasattr(path, "abspath") else str(path)\n')
            f.write('        if os.path.exists(path_str):\n')
            f.write('            valid_paths += 1\n')
            f.write('        else:\n')
            f.write('            invalid_paths += 1\n')
            f.write('    \n')
            f.write('    lib_paths = COMPREHENSIVE_DATA.get("lib_paths", [])\n')
            f.write('    dynamic_paths = COMPREHENSIVE_DATA.get("dynamic_paths", [])\n')
            f.write('    \n')
            f.write('    print(f"✓ {critical_restored} kritische SCons-Variablen wiederhergestellt")\n')
            f.write('    print(f"✓ {restored_count} weitere SCons-Variablen wiederhergestellt")\n')
            f.write('    print(f"✓ {len(lib_paths)} Projekt-lib-Pfade verfügbar")\n')
            f.write('    print(f"✓ {len(dynamic_paths)} dynamische Pfade verfügbar")\n')
            f.write('    print(f"✓ Include-Pfade: {valid_paths} gültig, {invalid_paths} ungültig")\n')
            f.write('    \n')
            f.write('    return critical_restored >= 5 and restored_count > 10\n')
            f.write('\n')
            
            # Convenience-Funktionen
            f.write('def get_all_lib_paths():\n')
            f.write('    """Gibt alle gefundenen lib-Pfade zurück"""\n')
            f.write('    return list(COMPREHENSIVE_DATA.get("lib_paths", []))\n\n')
            
            f.write('def get_dynamic_paths():\n')
            f.write('    """Gibt dynamische Include-Pfade zurück"""\n')
            f.write('    return list(COMPREHENSIVE_DATA.get("dynamic_paths", []))\n\n')
            
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
            f.write(f'DYNAMIC_PATHS_FOUND = {len(comprehensive_data.get("dynamic_paths", []))}\n')
            f.write(f'COMPREHENSIVE_CAPTURE = True\n')
            f.write(f'ENHANCED_VERSION = True\n')
            
            # Main-Block
            f.write('\nif __name__ == "__main__":\n')
            f.write('    print("PlatformIO LDF SCons Variables Export (Erweitert umfassend)")\n')
            f.write('    lib_paths = get_all_lib_paths()\n')
            f.write('    dynamic_paths = get_dynamic_paths()\n')
            f.write('    var_analysis = get_variable_analysis()\n')
            f.write('    print(f"Projekt-lib-Pfade: {len(lib_paths)}")\n')
            f.write('    print(f"Dynamische Pfade: {len(dynamic_paths)}")\n')
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
        dynamic_paths_count = len(comprehensive_data.get('dynamic_paths', []))
        
        print(f"✓ Erweiterte umfassende SCons-Environment gespeichert:")
        print(f"   📁 {os.path.basename(cache_file)} ({file_size} Bytes)")
        print(f"   📊 {len(comprehensive_data.get('all_environment_vars', {}))} Environment-Variablen")
        print(f"   📚 {lib_paths_count} Projekt-lib-Pfade")
        print(f"   🔄 {dynamic_paths_count} dynamische Pfade")
        print(f"   📋 JSON-Export: {os.path.basename(json_file)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Erweiterte umfassende Environment-Speicherung fehlgeschlagen: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def enhanced_cache_validation():
    """Erweiterte Cache-Gültigkeitsprüfung"""
    print(f"🔍 Erweiterte Cache-Validierung...")
    
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        print(f"📝 Kein Cache vorhanden")
        return False
    
    try:
        # Lade Cache-Modul
        spec = importlib.util.spec_from_file_location("scons_env_cache", cache_file)
        env_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(env_module)
        
        # Prüfe ob erweiterte Version
        enhanced_version = getattr(env_module, 'ENHANCED_VERSION', False)
        if not enhanced_version:
            print("⚠️ Cache ist nicht von erweiterter Version")
            return False
        
        # Prüfe kritische Variablen
        comprehensive_data = getattr(env_module, 'COMPREHENSIVE_DATA', {})
        all_vars = comprehensive_data.get('all_environment_vars', {})
        
        critical_vars_present = all([
            var in all_vars for var in [
                'CPPPATH', 'CCFLAGS', 'LIBPATH', 'BOARD'
            ]
        ])
        
        if not critical_vars_present:
            print("⚠️ Cache fehlen kritische Variablen")
            return False
        
        # Prüfe Include-Pfad-Anzahl
        lib_paths = comprehensive_data.get('lib_paths', [])
        dynamic_paths = comprehensive_data.get('dynamic_paths', [])
        
        if len(lib_paths) == 0:
            print("⚠️ Cache enthält keine lib-Pfade")
            return False
        
        print(f"✅ Erweiterte Cache-Validierung erfolgreich:")
        print(f"   📊 {len(all_vars)} Variablen")
        print(f"   📚 {len(lib_paths)} lib-Pfade")
        print(f"   🔄 {len(dynamic_paths)} dynamische Pfade")
        print(f"   ✨ Erweiterte Version")
        
        return True
        
    except Exception as e:
        print(f"❌ Erweiterte Cache-Validierung fehlgeschlagen: {e}")
        return False

def restore_comprehensive_scons_configuration():
    """Lädt erweiterte umfassende Environment aus Python-Datei"""
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
        
        # Prüfe ob erweiterte umfassende Erfassung
        comprehensive_capture = getattr(env_module, 'COMPREHENSIVE_CAPTURE', False)
        enhanced_version = getattr(env_module, 'ENHANCED_VERSION', False)
        
        if comprehensive_capture and enhanced_version:
            print("✅ Cache stammt von erweiterter umfassender SCons-Variable-Erfassung")
        elif comprehensive_capture:
            print("✅ Cache stammt von umfassender SCons-Variable-Erfassung")
        else:
            print("⚠️ Cache stammt von älterer Version")
        
        # Environment wiederherstellen
        success = env_module.restore_environment(env)
        
        if success:
            total_vars = getattr(env_module, 'TOTAL_VARIABLES', 0)
            lib_paths_found = getattr(env_module, 'LIB_PATHS_FOUND', 0)
            dynamic_paths_found = getattr(env_module, 'DYNAMIC_PATHS_FOUND', 0)
            
            print(f"✓ Erweiterte umfassende Environment wiederhergestellt:")
            print(f"   📊 {total_vars} Environment-Variablen")
            print(f"   📚 {lib_paths_found} Projekt-lib-Pfade")
            print(f"   🔄 {dynamic_paths_found} dynamische Pfade")
            print(f"   ✅ Erweiterte umfassende SCons-Variable-Erfassung")
        
        return success
        
    except Exception as e:
        print(f"❌ Erweiterte umfassende Cache-Wiederherstellung fehlgeschlagen: {e}")
        return False

def early_cache_check_and_restore():
    """Prüft Cache und stellt erweiterte umfassende SCons-Environment wieder her"""
    print(f"🔍 Erweiterte Cache-Prüfung (umfassende SCons-Variable-Erfassung)...")
    
    # Erweiterte Cache-Validierung
    if not enhanced_cache_validation():
        return False
    
    current_ldf_mode = get_current_ldf_mode(env.get("PIOENV"))
    
    if current_ldf_mode != 'off':
        print(f"🔄 LDF noch aktiv - erweiterte umfassende Cache wird nach Build erstellt")
        return False
    
    print(f"⚡ Erweiterte umfassende Cache verfügbar - stelle Environment wieder her")
    
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
    """Erweiterte umfassende Environment-Erfassung mit allen SCons-Variablen"""
    global _backup_created
    
    if _backup_created:
        print("✓ Environment bereits erfasst - überspringe erweiterte umfassende Erfassung")
        return None
    
    try:
        print(f"\n🎯 ERWEITERTE UMFASSENDE ENVIRONMENT-ERFASSUNG:")
        print(f"   Target: {[str(t) for t in target]}")
        print(f"   🕐 Timing: VOR Linken - alle SCons-Variablen verfügbar")
        
        # Erweiterte umfassende Variable-Erfassung
        comprehensive_data = comprehensive_variable_capture()
        
        lib_paths_count = len(comprehensive_data.get('lib_paths', []))
        dynamic_paths_count = len(comprehensive_data.get('dynamic_paths', []))
        total_vars = len(comprehensive_data.get('all_environment_vars', {}))
        
        print(f"\n   📊 ERWEITERTE ERFASSUNG ABGESCHLOSSEN:")
        print(f"      📚 Projekt-lib-Pfade: {lib_paths_count}")
        print(f"      🔄 Dynamische Pfade: {dynamic_paths_count}")
        print(f"      📋 Environment-Variablen: {total_vars}")
        
        if total_vars > 50:  # Realistische Anzahl für vollständiges Environment
            if freeze_comprehensive_scons_configuration(comprehensive_data):
                env_name = env.get("PIOENV")
                if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                    print(f"🚀 Erweiterte umfassende Environment-Erfassung erfolgreich!")
                    _backup_created = True
                else:
                    print(f"⚠ lib_ldf_mode konnte nicht gesetzt werden")
            else:
                print(f"❌ Environment-Speicherung fehlgeschlagen")
        else:
            print(f"⚠ Zu wenige Environment-Variablen ({total_vars})")
        
    except Exception as e:
        print(f"❌ Erweiterte umfassende Environment-Erfassung Fehler: {e}")
    
    return None

# =============================================================================
# HAUPTLOGIK - ERWEITERTE UMFASSENDE SCONS-VARIABLE-ERFASSUNG
# =============================================================================

print(f"\n🎯 Erweiterte umfassende SCons-Variable-Erfassung für: {env.get('PIOENV')}")

# Cache-Prüfung und erweiterte umfassende SCons-Environment-Wiederherstellung
cache_restored = early_cache_check_and_restore()

if cache_restored:
    print(f"🚀 Build mit erweiterter umfassender Environment-Cache - LDF übersprungen!")

else:
    print(f"📝 Normaler LDF-Durchlauf - erweiterte umfassende Variable-Erfassung...")
    
    # Pre-Link Hook für erweiterte umfassende Environment-Erfassung
    env.AddPreAction("$BUILD_DIR/${PROGNAME}.elf", comprehensive_environment_capture)
    print(f"✅ Pre-Link Hook für erweiterte umfassende SCons-Variable-Erfassung registriert")
    print(f"🔍 Erfasst ALLE SCons-Variablen inkl. interne, dynamische und lib-spezifische")

print(f"🏁 Erweiterte umfassende SCons-Variable-Erfassung initialisiert")
print(f"💡 Reset: rm -rf .pio/ldf_cache/")
print(f"📊 Erfasst: Alle Environment-Variablen + Include-Variablen + interne + dynamische SCons-Variablen")
print(f"🔍 Sucht: Projekt-lib-Pfade in ALLEN verfügbaren SCons-Variablen")
print(f"✨ Erweiterte Version mit verbesserter Validierung und kritischer Variable-Wiederherstellung\n")
