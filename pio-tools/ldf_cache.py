Import("env")
import os
import hashlib
import configparser
import shutil
import glob
import time
import importlib.util
import json
from datetime import datetime

# Globale Variablen
_backup_created = False
original_object_builder = None

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

def capture_ldf_cpppath():
    """
    Erfasst CPPPATH-Einträge nach LDF-Verarbeitung
    """
    # Sammle CPPPATH aus verschiedenen Quellen
    cpppath_sources = {
        'original_env': list(env.get('CPPPATH', [])),
        'project_include_dirs': [],
        'lib_include_dirs': [],
        'dependency_include_dirs': [],
        'framework_include_dirs': [],
    }
    
    # Project Include Directories
    try:
        project_builder = None
        lib_builders = env.GetLibBuilders()
        for lb in lib_builders:
            if hasattr(lb, '__class__') and 'ProjectAsLibBuilder' in lb.__class__.__name__:
                project_builder = lb
                break
        
        if project_builder:
            cpppath_sources['project_include_dirs'] = project_builder.get_include_dirs()
    except:
        pass
    
    # Library Include Directories (nach LDF-Verarbeitung)
    try:
        lib_builders = env.GetLibBuilders()
        for lb in lib_builders:
            try:
                # Erzwinge LDF-Verarbeitung falls noch nicht geschehen
                if not getattr(lb, '_deps_are_processed', False):
                    lb.search_deps_recursive()
                
                # Sammle Include-Verzeichnisse
                include_dirs = lb.get_include_dirs()
                cpppath_sources['lib_include_dirs'].extend(include_dirs)
                
                # Sammle auch CPPPATH aus dem Library Environment
                lib_cpppath = lb.env.get('CPPPATH', [])
                cpppath_sources['dependency_include_dirs'].extend(lib_cpppath)
                
            except Exception as e:
                print(f"Warnung: Konnte Include-Dirs für {getattr(lb, 'name', 'Unknown')} nicht erfassen: {e}")
    except:
        pass
    
    # Framework Include Directories
    framework_paths = []
    for key in ['CPPPATH', 'CCFLAGS', 'CXXFLAGS']:
        values = env.get(key, [])
        if isinstance(values, str):
            values = [values]
        for value in values:
            if isinstance(value, str) and ('-I' in value or 'include' in value.lower()):
                framework_paths.append(value)
    cpppath_sources['framework_include_dirs'] = framework_paths
    
    return cpppath_sources

def export_ldf_variables_extended():
    """
    Erweiterte Exportfunktion mit vollständiger CPPPATH-Erfassung
    """
    # Erzwinge LDF-Verarbeitung für alle Libraries
    try:
        lib_builders = env.GetLibBuilders()
        for lb in lib_builders:
            if not getattr(lb, 'is_built', False):
                try:
                    # Triggere Dependency-Suche
                    lb.search_deps_recursive()
                    # Triggere Build-Prozess (ohne tatsächliches Kompilieren)
                    if hasattr(lb, 'process_dependencies'):
                        lb.process_dependencies()
                except:
                    pass
    except:
        pass
    
    # Erfasse CPPPATH nach LDF-Verarbeitung
    cpppath_data = capture_ldf_cpppath()
    
    # Sammle alle eindeutigen CPPPATH-Einträge
    all_cpppath = set()
    for source, paths in cpppath_data.items():
        if isinstance(paths, (list, tuple)):
            for path in paths:
                if isinstance(path, str):
                    all_cpppath.add(env.subst(path))
                elif hasattr(path, 'abspath'):
                    all_cpppath.add(str(path.abspath))
                else:
                    all_cpppath.add(str(path))
    
    # Aktualisierte LDF-Variablen
    ldf_variables = {}
    
    # Build-Environment Variablen (mit aktualisierter CPPPATH)
    ldf_variables['BUILD_VARS'] = {
        'BUILD_DIR': env.get('BUILD_DIR', ''),
        'PROJECT_DIR': env.get('PROJECT_DIR', ''),
        'PROJECT_SRC_DIR': env.get('PROJECT_SRC_DIR', ''),
        'PROJECT_INCLUDE_DIR': env.get('PROJECT_INCLUDE_DIR', ''),
        'PROJECT_LIBDEPS_DIR': env.get('PROJECT_LIBDEPS_DIR', ''),
        'PIOENV': env.get('PIOENV', ''),
        'PIOPLATFORM': env.get('PIOPLATFORM', ''),
        'PIOFRAMEWORK': env.get('PIOFRAMEWORK', []),
        'BUILD_TYPE': env.get('BUILD_TYPE', ''),
    }
    
    # Erweiterte Library-Variablen mit detaillierter CPPPATH-Analyse
    ldf_variables['LIB_VARS'] = {
        'LIBSOURCE_DIRS': env.get('LIBSOURCE_DIRS', []),
        'CPPPATH_ORIGINAL': [str(p.abspath) if hasattr(p, 'abspath') else str(p) for p in env.get('CPPPATH', [])],
        'CPPPATH_COMPLETE': sorted(list(all_cpppath)),
        'CPPPATH_SOURCES': {k: [str(p.abspath) if hasattr(p, 'abspath') else str(p) for p in v] for k, v in cpppath_data.items()},
        'LIBPATH': [str(p.abspath) if hasattr(p, 'abspath') else str(p) for p in env.get('LIBPATH', [])],
        'LIBS': env.get('LIBS', []),
        'LINKFLAGS': env.get('LINKFLAGS', []),
        'CPPDEFINES': list(env.get('CPPDEFINES', [])),
        'SRC_FILTER': env.get('SRC_FILTER', ''),
        'SRC_BUILD_FLAGS': env.get('SRC_BUILD_FLAGS', ''),
    }
    
    # Project Options
    project_options = {}
    try:
        project_options = {
            'lib_deps': env.GetProjectOption('lib_deps', []),
            'lib_ignore': env.GetProjectOption('lib_ignore', []),
            'lib_extra_dirs': env.GetProjectOption('lib_extra_dirs', []),
            'lib_ldf_mode': env.GetProjectOption('lib_ldf_mode', 'chain'),
            'lib_compat_mode': env.GetProjectOption('lib_compat_mode', 'soft'),
            'lib_archive': env.GetProjectOption('lib_archive', True),
            'test_build_src': env.GetProjectOption('test_build_src', False),
        }
    except:
        pass
    
    ldf_variables['PROJECT_OPTIONS'] = project_options
    
    # Detaillierte Library Builders Information
    lib_builders_info = []
    try:
        lib_builders = env.GetLibBuilders()
        for lb in lib_builders:
            # Erfasse Environment-Zustand nach LDF-Verarbeitung
            lib_env_cpppath = lb.env.get('CPPPATH', []) if hasattr(lb, 'env') else []
            
            builder_info = {
                'name': getattr(lb, 'name', 'Unknown'),
                'path': getattr(lb, 'path', ''),
                'version': getattr(lb, 'version', None),
                'is_dependent': getattr(lb, 'is_dependent', False),
                'is_built': getattr(lb, 'is_built', False),
                'deps_processed': getattr(lb, '_deps_are_processed', False),
                'lib_ldf_mode': getattr(lb, 'lib_ldf_mode', 'chain'),
                'lib_compat_mode': getattr(lb, 'lib_compat_mode', 'soft'),
                'lib_archive': getattr(lb, 'lib_archive', True),
                'include_dirs': [str(p.abspath) if hasattr(p, 'abspath') else str(p) for p in getattr(lb, 'get_include_dirs', lambda: [])()],
                'src_dir': getattr(lb, 'src_dir', ''),
                'build_dir': getattr(lb, 'build_dir', ''),
                'dependencies': getattr(lb, 'dependencies', None),
                'depbuilders_count': len(getattr(lb, 'depbuilders', [])),
                'circular_deps_count': len(getattr(lb, '_circular_deps', [])),
                'env_cpppath': [str(p.abspath) if hasattr(p, 'abspath') else str(p) for p in lib_env_cpppath],
                'class_name': lb.__class__.__name__,
            }
            lib_builders_info.append(builder_info)
    except Exception as e:
        print(f"Fehler beim Erfassen der Library Builders: {e}")
    
    ldf_variables['LIB_BUILDERS'] = lib_builders_info
    
    # Erweiterte Metadaten
    ldf_variables['METADATA'] = {
        'export_timestamp': datetime.now().isoformat(),
        'platformio_version': env.get('PLATFORMIO_VERSION', 'Unknown'),
        'python_version': env.get('PYTHONVERSION', 'Unknown'),
        'total_lib_builders': len(lib_builders_info),
        'total_cpppath_entries': len(all_cpppath),
        'ldf_processing_triggered': True,
    }
    
    return ldf_variables

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

def capture_complete_scons_environment():
    """Erfasst vollständige SCons-Environment mit LDF-Daten"""
    
    print(f"\n🎯 VOLLSTÄNDIGE SCons-Environment-Erfassung mit LDF-Daten:")
    
    # 1. Erweiterte LDF-Variablen erfassen
    ldf_variables = export_ldf_variables_extended()
    
    # 2. Kritische SCons-Variablen direkt erfassen
    critical_vars = [
        'CPPPATH', 'CPPDEFINES', 'LIBS', 'LIBPATH', 
        'BUILD_FLAGS', 'CCFLAGS', 'CXXFLAGS', 'LINKFLAGS',
        'PIOBUILDFILES', 'LIB_DEPS', 'LIB_EXTRA_DIRS',
        'FRAMEWORK_DIR', 'PLATFORM_PACKAGES_DIR',
        'LIBSOURCE_DIRS', 'PROJECT_LIBDEPS_DIR'
    ]
    
    scons_data = {}
    conversion_stats = {"file_paths": 0, "builders": 0, "functions": 0, "other": 0}
    
    for var in critical_vars:
        raw_value = env.get(var, [])
        
        if var == 'CPPPATH':
            print(f"   📁 CPPPATH: {len(raw_value)} Einträge (vollständig erfasst)")
            
            # Zeige erste 5 zur Verifikation
            for i, path in enumerate(raw_value[:5]):
                path_str = str(path.abspath) if hasattr(path, 'abspath') else str(path)
                exists = os.path.exists(path_str)
                print(f"      {i:2d}: {'✓' if exists else '✗'} {path_str}")
        
        elif isinstance(raw_value, list):
            print(f"   📊 {var}: {len(raw_value)} Einträge")
        else:
            print(f"   📊 {var}: {type(raw_value).__name__}")
        
        # Konvertiere SCons-Objekte zu wiederverwendbaren Daten
        converted_value = convert_scons_objects_selective(raw_value, var)
        scons_data[var] = converted_value
        
        # Zähle Konvertierungen
        if var == 'CPPPATH' and isinstance(raw_value, list):
            for item in raw_value:
                if hasattr(item, 'abspath'):
                    conversion_stats["file_paths"] += 1
    
    # 3. Kombiniere SCons-Daten mit LDF-Variablen
    complete_data = {
        'SCONS_VARS': scons_data,
        'LDF_VARS': ldf_variables,
        'CONVERSION_STATS': conversion_stats
    }
    
    print(f"   🔄 {conversion_stats['file_paths']} SCons-Pfad-Objekte konvertiert")
    print(f"   ✅ String-Pfade blieben unverändert")
    print(f"   📊 LDF-Variablen: {len(ldf_variables)} Kategorien")
    
    return complete_data

def freeze_complete_scons_configuration(complete_data):
    """Speichert vollständige SCons-Environment mit LDF-Daten"""
    cache_file = get_cache_file_path()
    temp_file = cache_file + ".tmp"
    
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write("#!/usr/bin/env python3\n")
            f.write("# -*- coding: utf-8 -*-\n")
            f.write('"""\n')
            f.write('PlatformIO LDF SCons Variables Export - Vollständige Erfassung\n')
            f.write(f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'Environment: {env.get("PIOENV")}\n')
            f.write('"""\n\n')
            
            # SCons-Daten
            f.write('# SCons Environment Variables\n')
            f.write('SCONS_VARS = ')
            f.write(repr(complete_data['SCONS_VARS']))
            f.write('\n\n')
            
            # LDF-Daten
            f.write('# LDF Variables (vollständig)\n')
            f.write('LDF_VARS = ')
            f.write(repr(complete_data['LDF_VARS']))
            f.write('\n\n')
            
            # Restore-Funktion
            f.write('def restore_environment(target_env):\n')
            f.write('    """Stellt vollständige SCons-Environment wieder her"""\n')
            f.write('    restored_count = 0\n')
            f.write('    \n')
            f.write('    # SCons-Variablen wiederherstellen\n')
            f.write('    for key, value in SCONS_VARS.items():\n')
            f.write('        try:\n')
            f.write('            target_env[key] = value\n')
            f.write('            restored_count += 1\n')
            f.write('        except Exception as e:\n')
            f.write('            print(f"⚠ Fehler bei {key}: {e}")\n')
            f.write('    \n')
            f.write('    # LDF-spezifische CPPPATH wiederherstellen\n')
            f.write('    try:\n')
            f.write('        complete_cpppath = LDF_VARS.get("LIB_VARS", {}).get("CPPPATH_COMPLETE", [])\n')
            f.write('        if complete_cpppath:\n')
            f.write('            target_env["CPPPATH"] = complete_cpppath\n')
            f.write('            print(f"✓ Vollständige CPPPATH wiederhergestellt: {len(complete_cpppath)} Pfade")\n')
            f.write('    except Exception as e:\n')
            f.write('        print(f"⚠ CPPPATH-Wiederherstellung fehlgeschlagen: {e}")\n')
            f.write('    \n')
            f.write('    print(f"✓ {restored_count} SCons-Variablen wiederhergestellt")\n')
            f.write('    print(f"✓ LDF-Daten verfügbar: {len(LDF_VARS)} Kategorien")\n')
            f.write('    return restored_count > 5\n')
            f.write('\n')
            
            # Convenience-Funktionen
            f.write('def get_complete_cpppath():\n')
            f.write('    """Gibt alle CPPPATH-Einträge (inkl. LDF-generierte) zurück"""\n')
            f.write('    return LDF_VARS.get("LIB_VARS", {}).get("CPPPATH_COMPLETE", [])\n\n')
            
            f.write('def get_cpppath_sources():\n')
            f.write('    """Gibt CPPPATH-Einträge nach Quelle gruppiert zurück"""\n')
            f.write('    return LDF_VARS.get("LIB_VARS", {}).get("CPPPATH_SOURCES", {})\n\n')
            
            f.write('def analyze_cpppath_diff():\n')
            f.write('    """Analysiert Unterschiede zwischen Original- und vollständiger CPPPATH"""\n')
            f.write('    original = set(LDF_VARS.get("LIB_VARS", {}).get("CPPPATH_ORIGINAL", []))\n')
            f.write('    complete = set(get_complete_cpppath())\n')
            f.write('    return {\n')
            f.write('        "original_count": len(original),\n')
            f.write('        "complete_count": len(complete),\n')
            f.write('        "ldf_added": sorted(list(complete - original)),\n')
            f.write('        "ldf_added_count": len(complete - original)\n')
            f.write('    }\n\n')
            
            f.write('def get_lib_builders_info():\n')
            f.write('    """Gibt detaillierte Library Builder Information zurück"""\n')
            f.write('    return LDF_VARS.get("LIB_BUILDERS", [])\n\n')
            
            # Metadaten
            f.write('# Metadata\n')
            f.write(f'CONFIG_HASH = {repr(calculate_config_hash())}\n')
            f.write(f'ENV_NAME = {repr(env.get("PIOENV"))}\n')
            f.write(f'SCONS_VAR_COUNT = {len(complete_data["SCONS_VARS"])}\n')
            f.write(f'LDF_CATEGORIES = {len(complete_data["LDF_VARS"])}\n')
            f.write(f'COMPLETE_CAPTURE = True\n')
            f.write(f'CONVERTED_FILE_PATHS = {complete_data["CONVERSION_STATS"]["file_paths"]}\n')
            
            # Main-Block
            f.write('\nif __name__ == "__main__":\n')
            f.write('    print("PlatformIO LDF SCons Variables Export (Vollständig)")\n')
            f.write('    diff = analyze_cpppath_diff()\n')
            f.write('    print(f"Original CPPPATH: {diff[\\"original_count\\"]} Einträge")\n')
            f.write('    print(f"Vollständige CPPPATH: {diff[\\"complete_count\\"]} Einträge")\n')
            f.write('    print(f"Vom LDF hinzugefügt: {diff[\\"ldf_added_count\\"]} Einträge")\n')
            f.write('    lib_builders = get_lib_builders_info()\n')
            f.write('    print(f"Library Builders: {len(lib_builders)}")\n')
            f.write('    if diff["ldf_added"]:\n')
            f.write('        print("LDF-hinzugefügte Pfade:")\n')
            f.write('        for path in diff["ldf_added"][:10]:  # Erste 10\n')
            f.write('            print(f"  {path}")\n')
        
        # Atomarer Move
        shutil.move(temp_file, cache_file)
        
        # JSON-Export zusätzlich
        json_file = cache_file.replace('.py', '.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(complete_data, f, indent=2, ensure_ascii=False, default=str)
        
        file_size = os.path.getsize(cache_file)
        cpppath_count = len(complete_data['LDF_VARS'].get('LIB_VARS', {}).get('CPPPATH_COMPLETE', []))
        
        print(f"✓ Vollständige SCons-Environment gespeichert:")
        print(f"   📁 {os.path.basename(cache_file)} ({file_size} Bytes)")
        print(f"   📊 {len(complete_data['SCONS_VARS'])} SCons-Variablen")
        print(f"   📄 {cpppath_count} CPPPATH-Einträge (vollständig)")
        print(f"   🔄 {complete_data['CONVERSION_STATS']['file_paths']} SCons-Objekte konvertiert")
        print(f"   📋 JSON-Export: {os.path.basename(json_file)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Vollständige Environment-Erfassung fehlgeschlagen: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def trigger_complete_environment_capture():
    """Triggert vollständige Environment-Erfassung mit LDF-Daten"""
    global _backup_created
    
    if _backup_created:
        return
    
    try:
        print(f"🎯 Triggere vollständige Environment-Erfassung mit LDF-Daten...")
        
        # Vollständige Environment-Erfassung
        complete_data = capture_complete_scons_environment()
        
        cpppath_count = len(complete_data['LDF_VARS'].get('LIB_VARS', {}).get('CPPPATH_COMPLETE', []))
        
        if cpppath_count > 5:
            if freeze_complete_scons_configuration(complete_data):
                env_name = env.get("PIOENV")
                if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                    print(f"🚀 Vollständige Environment erfolgreich erfasst!")
                    _backup_created = True
                else:
                    print(f"⚠ lib_ldf_mode konnte nicht gesetzt werden")
            else:
                print(f"❌ Environment-Speicherung fehlgeschlagen")
        else:
            print(f"⚠ Zu wenige CPPPATH-Einträge ({cpppath_count})")
    
    except Exception as e:
        print(f"❌ Vollständige Environment-Erfassung Fehler: {e}")

def restore_complete_scons_configuration():
    """Lädt vollständige Environment aus Python-Datei"""
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
        
        # Prüfe ob vollständige Erfassung
        complete_capture = getattr(env_module, 'COMPLETE_CAPTURE', False)
        if complete_capture:
            print("✅ Cache stammt von vollständiger LDF-Erfassung")
        
        # Environment wiederherstellen
        success = env_module.restore_environment(env)
        
        if success:
            scons_var_count = getattr(env_module, 'SCONS_VAR_COUNT', 0)
            ldf_categories = getattr(env_module, 'LDF_CATEGORIES', 0)
            converted_file_paths = getattr(env_module, 'CONVERTED_FILE_PATHS', 0)
            
            print(f"✓ Vollständige Environment wiederhergestellt:")
            print(f"   📊 {scons_var_count} SCons-Variablen")
            print(f"   📋 {ldf_categories} LDF-Kategorien")
            print(f"   📄 {converted_file_paths} SCons-Pfad-Objekte konvertiert")
            print(f"   ✅ Vollständige LDF-Erfassung verwendet")
        
        return success
        
    except Exception as e:
        print(f"❌ Vollständige Cache-Wiederherstellung fehlgeschlagen: {e}")
        return False

def early_cache_check_and_restore():
    """Prüft Cache und stellt vollständige SCons-Environment wieder her"""
    print(f"🔍 Cache-Prüfung (vollständige LDF-Environment)...")
    
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        print(f"📝 Kein vollständiger Cache - LDF wird normal ausgeführt")
        return False
    
    current_ldf_mode = get_current_ldf_mode(env.get("PIOENV"))
    
    if current_ldf_mode != 'off':
        print(f"🔄 LDF noch aktiv - vollständiger Cache wird nach Build erstellt")
        return False
    
    print(f"⚡ Vollständiger Cache verfügbar - stelle Environment wieder her")
    
    success = restore_complete_scons_configuration()
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

def post_build_complete_capture(target, source, env):
    """Post-Build Hook: Vollständige SCons-Environment-Erfassung mit LDF-Daten"""
    global _backup_created
    
    if _backup_created:
        print("✓ Vollständige Environment bereits erfasst - überspringe Post-Build Action")
        return None
    
    try:
        print(f"\n🎯 POST-BUILD: Vollständige SCons-Environment-Erfassung mit LDF-Daten")
        print(f"   Target: {[str(t) for t in target]}")
        print(f"   Source: {len(source)} Dateien")
        
        # Vollständige Environment-Erfassung mit LDF-Daten
        trigger_complete_environment_capture()
        
    except Exception as e:
        print(f"❌ Post-Build vollständige Erfassung Fehler: {e}")
    
    return None

# =============================================================================
# HAUPTLOGIK - VOLLSTÄNDIGE LDF-SCONS-ENVIRONMENT-ERFASSUNG (1-STUFIG)
# =============================================================================

print(f"\n🎯 Vollständige LDF-SCons-Environment-Erfassung für: {env.get('PIOENV')}")

# Cache-Prüfung und vollständige SCons-Environment-Wiederherstellung
cache_restored = early_cache_check_and_restore()

if cache_restored:
    print(f"🚀 Build mit vollständigem LDF-Environment-Cache - LDF übersprungen!")

else:
    print(f"📝 Normaler LDF-Durchlauf - vollständige Erfassung nach Build...")
    
    # Post-Build Hook für vollständige Environment-Erfassung
    env.AddPostAction("$BUILD_DIR/${PROGNAME}.elf", post_build_complete_capture)
    print(f"✅ Post-Build Hook für vollständige LDF-Erfassung registriert")

print(f"🏁 Vollständige LDF-SCons-Environment-Erfassung initialisiert")
print(f"💡 Reset: rm -rf .pio/ldf_cache/")
print(f"💡 Nach erfolgreichem Build: lib_ldf_mode = off für nachfolgende Builds\n")
