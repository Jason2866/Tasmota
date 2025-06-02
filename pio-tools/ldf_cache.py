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

def safe_convert_to_string(value, context=""):
    """Sichere Konvertierung von SCons-Objekten zu Strings"""
    if isinstance(value, str):
        return value
    elif hasattr(value, 'abspath'):
        return str(value.abspath)
    elif hasattr(value, 'path'):
        return str(value.path)
    elif hasattr(value, 'get_path'):
        try:
            return str(value.get_path())
        except:
            return str(value)
    elif hasattr(value, '__class__') and 'SCons' in str(value.__class__):
        print(f"⚠ SCons-Objekt in {context}: {value.__class__.__name__}")
        return str(value)
    else:
        return str(value)

def capture_recursive_lib_directories():
    """Erfasst ALLE rekursiven Library-Verzeichnisse aus lib_dir, lib_extra_dirs und shared_libdeps_dir"""
    print(f"\n📁 REKURSIVE LIBRARY-VERZEICHNIS-ERFASSUNG:")
    
    project_dir = env.get("PROJECT_DIR")
    all_lib_dirs = []
    header_directories = []
    
    # 1. lib_dir erfassen
    try:
        lib_dir = env.GetProjectOption('lib_dir', '')
        if lib_dir:
            print(f"   📋 lib_dir: {lib_dir}")
            
            # lib_dir kann mehrere Pfade enthalten (durch ; oder , getrennt)
            if isinstance(lib_dir, str):
                lib_dirs = [d.strip() for d in lib_dir.replace(';', ',').split(',') if d.strip()]
            else:
                lib_dirs = [lib_dir]
            
            for lib_directory in lib_dirs:
                # Relativer zu absolutem Pfad
                if not os.path.isabs(lib_directory):
                    abs_lib_dir = os.path.join(project_dir, lib_directory)
                else:
                    abs_lib_dir = lib_directory
                
                if os.path.exists(abs_lib_dir):
                    print(f"   📂 Durchsuche lib_dir rekursiv: {abs_lib_dir}")
                    
                    # VOLLSTÄNDIGE REKURSIVE DURCHSUCHUNG
                    for root, dirs, files in os.walk(abs_lib_dir):
                        # Prüfe ob Verzeichnis Header-Dateien enthält
                        header_files = [f for f in files if f.endswith(('.h', '.hpp', '.hxx', '.inc'))]
                        
                        if header_files:
                            header_directories.append(root)
                            rel_path = os.path.relpath(root, project_dir)
                            print(f"      ✓ lib_dir Header-Dir: {rel_path} ({len(header_files)} Headers)")
                            
                            # Spezielle Prüfung für kritische Header
                            for header in header_files:
                                if header in ['esp-knx-ip.h', 'Arduino.h', 'WiFi.h']:
                                    print(f"         🎯 {header} GEFUNDEN!")
                        
                        # Prüfe auf Library-Manifeste
                        if any(manifest in files for manifest in ['library.json', 'library.properties', 'module.json']):
                            if root not in all_lib_dirs:
                                all_lib_dirs.append(root)
                                print(f"      📚 lib_dir Library-Root: {os.path.relpath(root, project_dir)}")
                else:
                    print(f"   ❌ lib_dir nicht gefunden: {lib_directory}")
    
    except Exception as e:
        print(f"   ⚠ Fehler beim Erfassen von lib_dir: {e}")
    
    # 2. lib_extra_dirs erfassen
    try:
        lib_extra_dirs = env.GetProjectOption('lib_extra_dirs', [])
        if isinstance(lib_extra_dirs, str):
            lib_extra_dirs = [lib_extra_dirs]
        
        print(f"   📋 lib_extra_dirs: {lib_extra_dirs}")
        
        for extra_dir in lib_extra_dirs:
            # Relativer zu absolutem Pfad
            if not os.path.isabs(extra_dir):
                abs_extra_dir = os.path.join(project_dir, extra_dir)
            else:
                abs_extra_dir = extra_dir
            
            if os.path.exists(abs_extra_dir):
                print(f"   📂 Durchsuche lib_extra_dirs rekursiv: {abs_extra_dir}")
                
                # VOLLSTÄNDIGE REKURSIVE DURCHSUCHUNG
                for root, dirs, files in os.walk(abs_extra_dir):
                    # Prüfe ob Verzeichnis Header-Dateien enthält
                    header_files = [f for f in files if f.endswith(('.h', '.hpp', '.hxx', '.inc'))]
                    
                    if header_files:
                        if root not in header_directories:  # Duplikate vermeiden
                            header_directories.append(root)
                            rel_path = os.path.relpath(root, project_dir)
                            print(f"      ✓ lib_extra_dirs Header-Dir: {rel_path} ({len(header_files)} Headers)")
                            
                            # Spezielle Prüfung für kritische Header
                            for header in header_files:
                                if header in ['esp-knx-ip.h', 'Arduino.h', 'WiFi.h']:
                                    print(f"         🎯 {header} GEFUNDEN!")
                    
                    # Prüfe auf Library-Manifeste
                    if any(manifest in files for manifest in ['library.json', 'library.properties', 'module.json']):
                        if root not in all_lib_dirs:
                            all_lib_dirs.append(root)
                            print(f"      📚 lib_extra_dirs Library-Root: {os.path.relpath(root, project_dir)}")
                    
                    # Prüfe auf src/include Verzeichnisse
                    for subdir in dirs:
                        if subdir in ['src', 'include', 'includes']:
                            subdir_path = os.path.join(root, subdir)
                            if subdir_path not in header_directories:
                                # Prüfe ob das Unterverzeichnis Header enthält
                                try:
                                    subdir_files = os.listdir(subdir_path)
                                    subdir_headers = [f for f in subdir_files if f.endswith(('.h', '.hpp', '.hxx', '.inc'))]
                                    if subdir_headers:
                                        header_directories.append(subdir_path)
                                        print(f"      ✓ Subdir-Headers: {os.path.relpath(subdir_path, project_dir)} ({len(subdir_headers)} Headers)")
                                except:
                                    pass
            else:
                print(f"   ❌ lib_extra_dir nicht gefunden: {extra_dir}")
    
    except Exception as e:
        print(f"   ⚠ Fehler beim Erfassen von lib_extra_dirs: {e}")
    
    # 3. shared_libdeps_dir erfassen
    try:
        shared_libdeps_dir = env.GetProjectOption('shared_libdeps_dir', '')
        if shared_libdeps_dir:
            print(f"   📋 shared_libdeps_dir: {shared_libdeps_dir}")
            
            if not os.path.isabs(shared_libdeps_dir):
                abs_shared_dir = os.path.join(project_dir, shared_libdeps_dir)
            else:
                abs_shared_dir = shared_libdeps_dir
            
            if os.path.exists(abs_shared_dir):
                print(f"   📂 Durchsuche shared_libdeps rekursiv: {abs_shared_dir}")
                
                for root, dirs, files in os.walk(abs_shared_dir):
                    header_files = [f for f in files if f.endswith(('.h', '.hpp', '.hxx', '.inc'))]
                    
                    if header_files:
                        if root not in header_directories:
                            header_directories.append(root)
                            print(f"      ✓ Shared-Header-Dir: {os.path.relpath(root, project_dir)} ({len(header_files)} Headers)")
            else:
                print(f"   ❌ shared_libdeps_dir nicht gefunden: {shared_libdeps_dir}")
    
    except Exception as e:
        print(f"   ⚠ Fehler beim Erfassen von shared_libdeps_dir: {e}")
    
    # 4. Standard PlatformIO libdeps erfassen
    try:
        project_libdeps_dir = env.get('PROJECT_LIBDEPS_DIR', '')
        if project_libdeps_dir and os.path.exists(project_libdeps_dir):
            print(f"   📂 Durchsuche PROJECT_LIBDEPS_DIR: {project_libdeps_dir}")
            
            for root, dirs, files in os.walk(project_libdeps_dir):
                header_files = [f for f in files if f.endswith(('.h', '.hpp', '.hxx', '.inc'))]
                
                if header_files:
                    if root not in header_directories:
                        header_directories.append(root)
                        print(f"      ✓ Libdeps-Header-Dir: {os.path.relpath(root, project_dir)} ({len(header_files)} Headers)")
    
    except Exception as e:
        print(f"   ⚠ Fehler beim Erfassen von PROJECT_LIBDEPS_DIR: {e}")
    
    print(f"   📊 Rekursive Erfassung abgeschlossen:")
    print(f"      Library-Roots: {len(all_lib_dirs)}")
    print(f"      Header-Verzeichnisse: {len(header_directories)}")
    
    return all_lib_dirs, header_directories

def capture_ldf_cpppath():
    """Erfasst CPPPATH-Einträge nach LDF-Verarbeitung mit SICHERER SCons-Objekt-Konvertierung"""
    print(f"\n📁 VOLLSTÄNDIGE CPPPATH-ERFASSUNG MIT SICHERER SCons-KONVERTIERUNG:")
    
    # SICHERE String-Konvertierung für ALLE Quellen
    cpppath_sources = {
        'original_env': [safe_convert_to_string(p, "original_env") for p in env.get('CPPPATH', [])],
        'project_include_dirs': [],
        'lib_include_dirs': [],
        'dependency_include_dirs': [],
        'framework_include_dirs': [],
        'recursive_lib_dirs': [],
        'recursive_header_dirs': [],
    }
    
    # NEUE: Rekursive Library-Verzeichnis-Erfassung (bereits Strings)
    lib_roots, header_dirs = capture_recursive_lib_directories()
    cpppath_sources['recursive_lib_dirs'] = lib_roots
    cpppath_sources['recursive_header_dirs'] = header_dirs
    
    # Project Include Directories mit SICHERER Konvertierung
    try:
        project_builder = None
        lib_builders = env.GetLibBuilders()
        for lb in lib_builders:
            if hasattr(lb, '__class__') and 'ProjectAsLibBuilder' in lb.__class__.__name__:
                project_builder = lb
                break
        
        if project_builder:
            project_includes = project_builder.get_include_dirs()
            # SICHERE Konvertierung zu Strings
            cpppath_sources['project_include_dirs'] = [
                safe_convert_to_string(p, "project_include_dirs") for p in project_includes
            ]
    except:
        pass
    
    # Library Include Directories mit SICHERER Konvertierung
    try:
        lib_builders = env.GetLibBuilders()
        print(f"   📚 Aktive Library Builders: {len(lib_builders)}")
        
        for lb in lib_builders:
            try:
                # Erzwinge LDF-Verarbeitung falls noch nicht geschehen
                if not getattr(lb, '_deps_are_processed', False):
                    lb.search_deps_recursive()
                
                # SICHERE Konvertierung der Include-Verzeichnisse
                include_dirs = lb.get_include_dirs()
                for inc_dir in include_dirs:
                    inc_path = safe_convert_to_string(inc_dir, f"lib_include_dirs[{getattr(lb, 'name', 'Unknown')}]")
                    if inc_path not in cpppath_sources['lib_include_dirs']:
                        cpppath_sources['lib_include_dirs'].append(inc_path)
                
                # SICHERE Konvertierung der Library Environment CPPPATH
                lib_cpppath = lb.env.get('CPPPATH', [])
                for lib_path in lib_cpppath:
                    lib_path_str = safe_convert_to_string(lib_path, f"dependency_include_dirs[{getattr(lb, 'name', 'Unknown')}]")
                    if lib_path_str not in cpppath_sources['dependency_include_dirs']:
                        cpppath_sources['dependency_include_dirs'].append(lib_path_str)
                
                # Debug-Info für KNX-Libraries
                lib_name = getattr(lb, 'name', 'Unknown')
                lib_path = getattr(lb, 'path', '')
                if 'knx' in lib_name.lower() or 'knx' in lib_path.lower():
                    print(f"      🎯 KNX-Library: {lib_name}")
                    print(f"         Pfad: {lib_path}")
                    print(f"         Include-Dirs: {len(include_dirs)}")
                    for inc_dir in include_dirs:
                        inc_path = safe_convert_to_string(inc_dir, "knx_debug")
                        knx_header = os.path.join(inc_path, 'esp-knx-ip.h')
                        if os.path.exists(knx_header):
                            print(f"         ✅ esp-knx-ip.h: {knx_header}")
                
            except Exception as e:
                print(f"      ⚠ Warnung: Konnte Include-Dirs für {getattr(lb, 'name', 'Unknown')} nicht erfassen: {e}")
    except:
        pass
    
    # Framework Include Directories (bereits Strings)
    framework_paths = []
    for key in ['CPPPATH', 'CCFLAGS', 'CXXFLAGS']:
        values = env.get(key, [])
        if isinstance(values, str):
            values = [values]
        for value in values:
            value_str = safe_convert_to_string(value, f"framework_{key}")
            if isinstance(value_str, str) and ('-I' in value_str or 'include' in value_str.lower()):
                framework_paths.append(value_str)
    cpppath_sources['framework_include_dirs'] = framework_paths
    
    # Sammle alle eindeutigen CPPPATH-Einträge (alle bereits Strings)
    all_cpppath = set()
    for source, paths in cpppath_sources.items():
        if isinstance(paths, (list, tuple)):
            for path in paths:
                if isinstance(path, str) and path.strip():
                    expanded_path = env.subst(path)
                    all_cpppath.add(expanded_path)
                else:
                    print(f"⚠ Nicht-String-Pfad in {source}: {type(path)} = {path}")
    
    print(f"   📊 CPPPATH-Quellen-Statistik:")
    print(f"      Original env CPPPATH: {len(cpppath_sources['original_env'])} Einträge")
    print(f"      Project Include-Dirs: {len(cpppath_sources['project_include_dirs'])} Einträge")
    print(f"      Library Include-Dirs: {len(cpppath_sources['lib_include_dirs'])} Einträge")
    print(f"      Dependency CPPPATH: {len(cpppath_sources['dependency_include_dirs'])} Einträge")
    print(f"      Framework-Pfade: {len(cpppath_sources['framework_include_dirs'])} Einträge")
    print(f"      Rekursive Lib-Roots: {len(cpppath_sources['recursive_lib_dirs'])} Einträge")
    print(f"      Rekursive Header-Dirs: {len(cpppath_sources['recursive_header_dirs'])} Einträge")
    print(f"   ✅ Gesamt eindeutige CPPPATH: {len(all_cpppath)} Einträge")
    
    return cpppath_sources, sorted(list(all_cpppath))

def export_ldf_variables_extended():
    """Erweiterte Exportfunktion mit SICHERER SCons-Objekt-Konvertierung"""
    print(f"\n🎯 ERWEITERTE LDF-VARIABLE-ERFASSUNG MIT SICHERER SCons-KONVERTIERUNG:")
    
    # Erzwinge LDF-Verarbeitung für alle Libraries
    try:
        lib_builders = env.GetLibBuilders()
        print(f"   📚 Verarbeite {len(lib_builders)} Library Builders...")
        
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
    
    # Erfasse CPPPATH nach LDF-Verarbeitung mit sicherer SCons-Konvertierung
    cpppath_sources, complete_cpppath = capture_ldf_cpppath()
    
    # Aktualisierte LDF-Variablen
    ldf_variables = {}
    
    # Build-Environment Variablen (mit sicherer Konvertierung)
    ldf_variables['BUILD_VARS'] = {
        'BUILD_DIR': safe_convert_to_string(env.get('BUILD_DIR', ''), 'BUILD_DIR'),
        'PROJECT_DIR': safe_convert_to_string(env.get('PROJECT_DIR', ''), 'PROJECT_DIR'),
        'PROJECT_SRC_DIR': safe_convert_to_string(env.get('PROJECT_SRC_DIR', ''), 'PROJECT_SRC_DIR'),
        'PROJECT_INCLUDE_DIR': safe_convert_to_string(env.get('PROJECT_INCLUDE_DIR', ''), 'PROJECT_INCLUDE_DIR'),
        'PROJECT_LIBDEPS_DIR': safe_convert_to_string(env.get('PROJECT_LIBDEPS_DIR', ''), 'PROJECT_LIBDEPS_DIR'),
        'PIOENV': safe_convert_to_string(env.get('PIOENV', ''), 'PIOENV'),
        'PIOPLATFORM': safe_convert_to_string(env.get('PIOPLATFORM', ''), 'PIOPLATFORM'),
        'PIOFRAMEWORK': [safe_convert_to_string(f, 'PIOFRAMEWORK') for f in env.get('PIOFRAMEWORK', [])],
        'BUILD_TYPE': safe_convert_to_string(env.get('BUILD_TYPE', ''), 'BUILD_TYPE'),
    }
    
    # Erweiterte Library-Variablen mit sicherer SCons-Konvertierung
    ldf_variables['LIB_VARS'] = {
        'LIBSOURCE_DIRS': [safe_convert_to_string(d, 'LIBSOURCE_DIRS') for d in env.get('LIBSOURCE_DIRS', [])],
        'CPPPATH_ORIGINAL': [safe_convert_to_string(p, 'CPPPATH_ORIGINAL') for p in env.get('CPPPATH', [])],
        'CPPPATH_COMPLETE': complete_cpppath,
        'CPPPATH_SOURCES': cpppath_sources,  # Bereits alle Strings
        'LIBPATH': [safe_convert_to_string(p, 'LIBPATH') for p in env.get('LIBPATH', [])],
        'LIBS': [safe_convert_to_string(l, 'LIBS') for l in env.get('LIBS', [])],
        'LINKFLAGS': [safe_convert_to_string(f, 'LINKFLAGS') for f in env.get('LINKFLAGS', [])],
        'CPPDEFINES': [safe_convert_to_string(d, 'CPPDEFINES') for d in env.get('CPPDEFINES', [])],
        'SRC_FILTER': safe_convert_to_string(env.get('SRC_FILTER', ''), 'SRC_FILTER'),
        'SRC_BUILD_FLAGS': safe_convert_to_string(env.get('SRC_BUILD_FLAGS', ''), 'SRC_BUILD_FLAGS'),
    }
    
    # Project Options mit vollständiger lib-Konfiguration
    project_options = {}
    try:
        project_options = {
            'lib_deps': env.GetProjectOption('lib_deps', []),
            'lib_ignore': env.GetProjectOption('lib_ignore', []),
            'lib_dir': env.GetProjectOption('lib_dir', ''),
            'lib_extra_dirs': env.GetProjectOption('lib_extra_dirs', []),
            'shared_libdeps_dir': env.GetProjectOption('shared_libdeps_dir', ''),
            'lib_ldf_mode': env.GetProjectOption('lib_ldf_mode', 'chain'),
            'lib_compat_mode': env.GetProjectOption('lib_compat_mode', 'soft'),
            'lib_archive': env.GetProjectOption('lib_archive', True),
            'test_build_src': env.GetProjectOption('test_build_src', False),
        }
    except:
        pass
    
    ldf_variables['PROJECT_OPTIONS'] = project_options
    
    # Detaillierte Library Builders Information mit sicherer Konvertierung
    lib_builders_info = []
    try:
        lib_builders = env.GetLibBuilders()
        for lb in lib_builders:
            # Erfasse Environment-Zustand nach LDF-Verarbeitung mit sicherer Konvertierung
            lib_env_cpppath = lb.env.get('CPPPATH', []) if hasattr(lb, 'env') else []
            
            builder_info = {
                'name': safe_convert_to_string(getattr(lb, 'name', 'Unknown'), 'lib_name'),
                'path': safe_convert_to_string(getattr(lb, 'path', ''), 'lib_path'),
                'version': safe_convert_to_string(getattr(lb, 'version', None), 'lib_version'),
                'is_dependent': getattr(lb, 'is_dependent', False),
                'is_built': getattr(lb, 'is_built', False),
                'deps_processed': getattr(lb, '_deps_are_processed', False),
                'lib_ldf_mode': safe_convert_to_string(getattr(lb, 'lib_ldf_mode', 'chain'), 'lib_ldf_mode'),
                'lib_compat_mode': safe_convert_to_string(getattr(lb, 'lib_compat_mode', 'soft'), 'lib_compat_mode'),
                'lib_archive': getattr(lb, 'lib_archive', True),
                'include_dirs': [safe_convert_to_string(p, 'include_dirs') for p in getattr(lb, 'get_include_dirs', lambda: [])()],
                'src_dir': safe_convert_to_string(getattr(lb, 'src_dir', ''), 'src_dir'),
                'build_dir': safe_convert_to_string(getattr(lb, 'build_dir', ''), 'build_dir'),
                'dependencies': safe_convert_to_string(getattr(lb, 'dependencies', None), 'dependencies'),
                'depbuilders_count': len(getattr(lb, 'depbuilders', [])),
                'circular_deps_count': len(getattr(lb, '_circular_deps', [])),
                'env_cpppath': [safe_convert_to_string(p, 'env_cpppath') for p in lib_env_cpppath],
                'class_name': lb.__class__.__name__,
            }
            lib_builders_info.append(builder_info)
    except Exception as e:
        print(f"   ⚠ Fehler beim Erfassen der Library Builders: {e}")
    
    ldf_variables['LIB_BUILDERS'] = lib_builders_info
    
    # Erweiterte Metadaten
    ldf_variables['METADATA'] = {
        'export_timestamp': datetime.now().isoformat(),
        'platformio_version': safe_convert_to_string(env.get('PLATFORMIO_VERSION', 'Unknown'), 'platformio_version'),
        'python_version': safe_convert_to_string(env.get('PYTHONVERSION', 'Unknown'), 'python_version'),
        'total_lib_builders': len(lib_builders_info),
        'total_cpppath_entries': len(complete_cpppath),
        'recursive_lib_capture': True,
        'safe_scons_conversion': True,
        'ldf_processing_triggered': True,
    }
    
    print(f"   ✅ LDF-Variablen erfasst: {len(ldf_variables)} Kategorien")
    print(f"   📁 Vollständige CPPPATH: {len(complete_cpppath)} Einträge")
    print(f"   📚 Library Builders: {len(lib_builders_info)} erfasst")
    print(f"   🔄 Rekursive lib-Erfassung: Aktiviert")
    print(f"   🛡️ Sichere SCons-Konvertierung: Aktiviert")
    
    return ldf_variables

def convert_scons_objects_selective(value, key="", depth=0):
    """Konvertiert ALLE SCons-Objekte inklusive CLVar zu serialisierbaren Daten"""
    
    # Schutz vor zu tiefer Rekursion
    if depth > 10:
        return str(value)
    
    # 1. VOLLSTÄNDIGE CLVar-Behandlung (ALLE Varianten)
    if hasattr(value, '__class__'):
        class_name = str(value.__class__)
        # Alle bekannten CLVar-Varianten
        if any(clvar_type in class_name for clvar_type in ['CLVar', 'CommandLineVar', 'clvar']):
            try:
                # Methode 1: Direkte Konvertierung zu Liste
                if hasattr(value, '__iter__') and not isinstance(value, str):
                    return list(value)
                # Methode 2: String-Split
                elif hasattr(value, 'split'):
                    return str(value).split()
                # Methode 3: String-Konvertierung und Parse
                else:
                    str_val = str(value)
                    # Entferne CLVar(...) wrapper
                    if 'CLVar(' in str_val:
                        import re
                        match = re.search(r'CLVar\(\[(.*?)\]\)', str_val)
                        if match:
                            content = match.group(1)
                            # Parse die Liste
                            items = []
                            for item in content.split(','):
                                item = item.strip().strip("'\"")
                                if item:
                                    items.append(item)
                            return items
                    return [str_val] if str_val else []
            except Exception as e:
                print(f"   ⚠ CLVar-Konvertierung fehlgeschlagen für {key}: {e}")
                return str(value)
    
    # 2. String-Repräsentation von CLVar-Objekten
    if isinstance(value, str) and 'CLVar(' in value:
        try:
            import re
            match = re.search(r'CLVar\(\[(.*?)\]\)', value)
            if match:
                content = match.group(1)
                items = []
                for item in content.split(','):
                    item = item.strip().strip("'\"")
                    if item:
                        items.append(item)
                return items
        except:
            pass
    
    # 3. VOLLSTÄNDIGE SCons-Objekt-Behandlung
    if hasattr(value, '__class__') and 'SCons' in str(value.__class__):
        return safe_convert_to_string(value, key)
    
    # 4. Funktionen und Callables
    elif callable(value):
        if hasattr(value, '__name__'):
            return f"<Function:{value.__name__}>"
        else:
            return f"<Callable:{value.__class__.__name__}>"
    
    # 5. Listen rekursiv verarbeiten
    elif isinstance(value, list):
        converted_list = []
        for item in value:
            converted_item = convert_scons_objects_selective(item, key, depth + 1)
            converted_list.append(converted_item)
        return converted_list
    
    # 6. Tupel rekursiv verarbeiten
    elif isinstance(value, tuple):
        converted_items = []
        for item in value:
            converted_item = convert_scons_objects_selective(item, key, depth + 1)
            converted_items.append(converted_item)
        return tuple(converted_items)
    
    # 7. Dictionaries rekursiv verarbeiten
    elif isinstance(value, dict):
        converted_dict = {}
        for dict_key, dict_value in value.items():
            converted_key = convert_scons_objects_selective(dict_key, key, depth + 1)
            converted_value = convert_scons_objects_selective(dict_value, key, depth + 1)
            converted_dict[converted_key] = converted_value
        return converted_dict
    
    # 8. deque und andere Collections
    elif hasattr(value, '__class__') and value.__class__.__name__ in ['deque', 'UserList']:
        return list(value)
    
    # 9. os.environ und ähnliche Mapping-Objekte
    elif hasattr(value, '__class__') and 'environ' in str(value.__class__).lower():
        return dict(value)
    
    # 10. Primitive Typen UNVERÄNDERT lassen
    elif isinstance(value, (str, int, float, bool, type(None))):
        return value
    
    # 11. Alles andere als String (mit SCons-Prüfung)
    else:
        str_repr = str(value)
        if 'SCons' in str_repr or 'CLVar' in str_repr:
            print(f"   🚨 UNBEHANDELTE SCons/CLVar gefunden in {key}: {str_repr}")
        return str_repr

def capture_complete_scons_environment():
    """Erfasst vollständige SCons-Environment mit sicherer SCons-Objekt-Konvertierung"""
    
    print(f"\n🎯 VOLLSTÄNDIGE SCons-Environment-Erfassung mit sicherer SCons-Konvertierung:")
    
    # 1. Erweiterte LDF-Variablen erfassen (mit sicherer SCons-Konvertierung)
    ldf_variables = export_ldf_variables_extended()
    
    # 2. Kritische SCons-Variablen direkt erfassen mit sicherer Konvertierung
    critical_vars = [
        'CPPPATH', 'CPPDEFINES', 'LIBS', 'LIBPATH', 
        'BUILD_FLAGS', 'CCFLAGS', 'CXXFLAGS', 'LINKFLAGS',
        'PIOBUILDFILES', 'LIB_DEPS', 'LIB_EXTRA_DIRS',
        'FRAMEWORK_DIR', 'PLATFORM_PACKAGES_DIR',
        'LIBSOURCE_DIRS', 'PROJECT_LIBDEPS_DIR',
        'BOARD', 'PLATFORM', 'PIOENV', 'PIOFRAMEWORK'
    ]
    
    scons_data = {}
    conversion_stats = {"file_paths": 0, "builders": 0, "functions": 0, "clvar_converted": 0, "scons_converted": 0, "other": 0}
    
    for var in critical_vars:
        raw_value = env.get(var, [])
        
        if var == 'CPPPATH':
            # Verwende die vollständige CPPPATH aus LDF-Variablen (bereits sichere Strings)
            complete_cpppath = ldf_variables.get('LIB_VARS', {}).get('CPPPATH_COMPLETE', [])
            scons_data[var] = complete_cpppath
            
            print(f"   📁 CPPPATH: {len(complete_cpppath)} Einträge (sichere String-Konvertierung)")
            
            # Zeige erste 5 zur Verifikation
            for i, path in enumerate(complete_cpppath[:5]):
                exists = os.path.exists(path)
                print(f"      {i:2d}: {'✓' if exists else '✗'} {path}")
            
            if len(complete_cpppath) > 5:
                print(f"      ... und {len(complete_cpppath) - 5} weitere")
        
        elif isinstance(raw_value, list):
            print(f"   📊 {var}: {len(raw_value)} Einträge")
            # Sichere Konvertierung aller SCons-Objekte
            converted_value = convert_scons_objects_selective(raw_value, var)
            scons_data[var] = converted_value
        else:
            print(f"   📊 {var}: {type(raw_value).__name__}")
            # Sichere Konvertierung einzelner Werte
            converted_value = convert_scons_objects_selective(raw_value, var)
            scons_data[var] = converted_value
        
        # Zähle Konvertierungen
        if isinstance(raw_value, list):
            for item in raw_value:
                if hasattr(item, 'abspath'):
                    conversion_stats["file_paths"] += 1
                elif 'CLVar' in str(type(item)):
                    conversion_stats["clvar_converted"] += 1
                elif hasattr(item, '__class__') and 'SCons' in str(item.__class__):
                    conversion_stats["scons_converted"] += 1
    
    # 3. Kombiniere SCons-Daten mit LDF-Variablen
    complete_data = {
        'SCONS_VARS': scons_data,
        'LDF_VARS': ldf_variables,
        'CONVERSION_STATS': conversion_stats
    }
    
    print(f"   🔄 {conversion_stats['file_paths']} SCons-Pfad-Objekte konvertiert")
    print(f"   🔄 {conversion_stats['clvar_converted']} CLVar-Objekte konvertiert")
    print(f"   🔄 {conversion_stats['scons_converted']} SCons-Objekte konvertiert")
    print(f"   ✅ Alle Objekte zu Strings konvertiert")
    print(f"   📊 LDF-Variablen: {len(ldf_variables)} Kategorien")
    print(f"   🛡️ Sichere SCons-Konvertierung: Aktiviert")
    
    return complete_data

def freeze_complete_scons_configuration(complete_data):
    """Speichert vollständige SCons-Environment mit robuster CPPPATH-Wiederherstellung"""
    cache_file = get_cache_file_path()
    temp_file = cache_file + ".tmp"
    
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write("#!/usr/bin/env python3\n")
            f.write("# -*- coding: utf-8 -*-\n")
            f.write('"""\n')
            f.write('PlatformIO LDF SCons Variables Export - Robuste CPPPATH-Wiederherstellung\n')
            f.write(f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'Environment: {env.get("PIOENV")}\n')
            f.write('"""\n\n')
            
            # SCons-Daten
            f.write('# SCons Environment Variables (alle SCons-Objekte zu Strings konvertiert)\n')
            f.write('SCONS_VARS = ')
            f.write(repr(complete_data['SCONS_VARS']))
            f.write('\n\n')
            
            # LDF-Daten
            f.write('# LDF Variables (sichere SCons-Konvertierung)\n')
            f.write('LDF_VARS = ')
            f.write(repr(complete_data['LDF_VARS']))
            f.write('\n\n')
            
            # ROBUSTE CPPPATH-Wiederherstellung
            f.write('def restore_environment(target_env):\n')
            f.write('    """ROBUSTE CPPPATH-Wiederherstellung mit ALLEN erfassten Pfaden"""\n')
            f.write('    import os\n')
            f.write('    restored_count = 0\n')
            f.write('    critical_restored = 0\n')
            f.write('    \n')
            f.write('    print("🔄 Starte ROBUSTE CPPPATH-Wiederherstellung...")\n')
            f.write('    \n')
            f.write('    # 1. Sammle ALLE CPPPATH-Einträge aus ALLEN Quellen (ROBUST)\n')
            f.write('    all_cpppath = []\n')
            f.write('    \n')
            f.write('    # 2. Basis-CPPPATH aus LDF_VARS (ERSTE PRIORITÄT)\n')
            f.write('    complete_cpppath = LDF_VARS.get("LIB_VARS", {}).get("CPPPATH_COMPLETE", [])\n')
            f.write('    print(f"   📁 Basis CPPPATH_COMPLETE: {len(complete_cpppath)} Einträge")\n')
            f.write('    for path in complete_cpppath:\n')
            f.write('        if isinstance(path, str) and path.strip() and path not in all_cpppath:\n')
            f.write('            all_cpppath.append(path.strip())\n')
            f.write('    \n')
            f.write('    # 3. ALLE CPPPATH-Quellen einzeln verarbeiten (ZWEITE PRIORITÄT)\n')
            f.write('    cpppath_sources = LDF_VARS.get("LIB_VARS", {}).get("CPPPATH_SOURCES", {})\n')
            f.write('    print(f"   📊 CPPPATH-Quellen verfügbar: {list(cpppath_sources.keys())}")\n')
            f.write('    \n')
            f.write('    # Verarbeite jede Quelle einzeln\n')
            f.write('    for source_name, source_paths in cpppath_sources.items():\n')
            f.write('        added_from_source = 0\n')
            f.write('        \n')
            f.write('        if isinstance(source_paths, list) and len(source_paths) > 0:\n')
            f.write('            print(f"      🔄 Verarbeite {source_name}: {len(source_paths)} Pfade")\n')
            f.write('            for path in source_paths:\n')
            f.write('                if isinstance(path, str) and path.strip():\n')
            f.write('                    normalized_path = os.path.normpath(path.strip())\n')
            f.write('                    if normalized_path not in all_cpppath:\n')
            f.write('                        all_cpppath.append(normalized_path)\n')
            f.write('                        added_from_source += 1\n')
            f.write('                        # Debug für KNX-Pfade\n')
            f.write('                        if "knx" in normalized_path.lower() or "esp-knx" in normalized_path.lower():\n')
            f.write('                            print(f"         🎯 KNX-Pfad hinzugefügt: {normalized_path}")\n')
            f.write('        elif isinstance(source_paths, str) and source_paths.strip():\n')
            f.write('            normalized_path = os.path.normpath(source_paths.strip())\n')
            f.write('            if normalized_path not in all_cpppath:\n')
            f.write('                all_cpppath.append(normalized_path)\n')
            f.write('                added_from_source += 1\n')
            f.write('        \n')
            f.write('        if added_from_source > 0:\n')
            f.write('            print(f"         ➕ {added_from_source} neue Pfade von {source_name}")\n')
            f.write('    \n')
            f.write('    # 4. Zusätzliche Include-Pfade aus SCONS_VARS (DRITTE PRIORITÄT)\n')
            f.write('    include_vars = ["CPPPATH", "FRAMEWORK_DIR", "PLATFORM_PACKAGES_DIR"]\n')
            f.write('    for var in include_vars:\n')
            f.write('        if var in SCONS_VARS:\n')
            f.write('            scons_paths = SCONS_VARS[var]\n')
            f.write('            if isinstance(scons_paths, list):\n')
            f.write('                for path in scons_paths:\n')
            f.write('                    if isinstance(path, str) and path.strip() and path not in all_cpppath:\n')
            f.write('                        all_cpppath.append(os.path.normpath(path.strip()))\n')
            f.write('            elif isinstance(scons_paths, str) and scons_paths.strip() and scons_paths not in all_cpppath:\n')
            f.write('                all_cpppath.append(os.path.normpath(scons_paths.strip()))\n')
            f.write('    \n')
            f.write('    # 5. Include-Pfade aus Build-Flags extrahieren\n')
            f.write('    build_flags = SCONS_VARS.get("BUILD_FLAGS", [])\n')
            f.write('    if isinstance(build_flags, list):\n')
            f.write('        for flag in build_flags:\n')
            f.write('            if isinstance(flag, str) and flag.startswith("-I"):\n')
            f.write('                include_path = flag[2:].strip()\n')
            f.write('                if include_path and include_path not in all_cpppath:\n')
            f.write('                    all_cpppath.append(os.path.normpath(include_path))\n')
            f.write('    \n')
            f.write('    # 6. VALIDIERUNG: Prüfe ob kritische Dateien gefunden werden\n')
            f.write('    critical_files_found = {}\n')
            f.write('    critical_files = ["esp-knx-ip.h", "Arduino.h", "WiFi.h"]\n')
            f.write('    \n')
            f.write('    print(f"   🔍 Validiere {len(all_cpppath)} CPPPATH-Einträge für kritische Dateien...")\n')
            f.write('    for critical_file in critical_files:\n')
            f.write('        for cpppath in all_cpppath:\n')
            f.write('            if os.path.exists(cpppath):\n')
            f.write('                header_path = os.path.join(cpppath, critical_file)\n')
            f.write('                if os.path.exists(header_path):\n')
            f.write('                    critical_files_found[critical_file] = cpppath\n')
            f.write('                    print(f"         ✅ {critical_file} gefunden in {cpppath}")\n')
            f.write('                    break\n')
            f.write('        if critical_file not in critical_files_found:\n')
            f.write('            print(f"         ❌ {critical_file} NICHT gefunden!")\n')
            f.write('    \n')
            f.write('    # 7. SPEZIELLE KNX-VALIDIERUNG\n')
            f.write('    knx_paths_in_cpppath = []\n')
            f.write('    for path in all_cpppath:\n')
            f.write('        if "knx" in path.lower() or "esp-knx" in path.lower():\n')
            f.write('            knx_paths_in_cpppath.append(path)\n')
            f.write('    \n')
            f.write('    print(f"   🎯 KNX-relevante Pfade in CPPPATH: {len(knx_paths_in_cpppath)}")\n')
            f.write('    for knx_path in knx_paths_in_cpppath:\n')
            f.write('        exists = os.path.exists(knx_path)\n')
            f.write('        esp_knx_header = os.path.join(knx_path, "esp-knx-ip.h")\n')
            f.write('        has_header = os.path.exists(esp_knx_header)\n')
            f.write('        print(f"      {'✓' if exists else '✗'} {knx_path} (Header: {'✓' if has_header else '✗'})")\n')
            f.write('    \n')
            f.write('    # 8. CPPPATH ERWEITERN (NICHT ÜBERSCHREIBEN!)\n')
            f.write('    if all_cpppath:\n')
            f.write('        # Hole existierende CPPPATH\n')
            f.write('        existing_cpppath = target_env.get("CPPPATH", [])\n')
            f.write('        existing_paths = [str(p) for p in existing_cpppath]\n')
            f.write('        \n')
            f.write('        # Entferne nur echte Duplikate, behalte Reihenfolge\n')
            f.write('        final_cpppath = list(existing_paths)  # Beginne mit existierenden Pfaden\n')
            f.write('        seen_paths = set(os.path.normpath(p) for p in existing_paths)\n')
            f.write('        \n')
            f.write('        added_new = 0\n')
            f.write('        for path in all_cpppath:\n')
            f.write('            normalized = os.path.normpath(path)\n')
            f.write('            if normalized not in seen_paths:\n')
            f.write('                final_cpppath.append(path)  # Originalpfad hinzufügen\n')
            f.write('                seen_paths.add(normalized)\n')
            f.write('                added_new += 1\n')
            f.write('        \n')
            f.write('        # ERWEITERE CPPPATH (überschreibe nicht!)\n')
            f.write('        target_env["CPPPATH"] = final_cpppath\n')
            f.write('        print(f"      ✅ CPPPATH erweitert: {len(existing_paths)} + {added_new} = {len(final_cpppath)} Pfade")\n')
            f.write('        \n')
            f.write('        # SOFORTIGE VALIDIERUNG\n')
            f.write('        validation_cpppath = target_env.get("CPPPATH", [])\n')
            f.write('        print(f"      🔍 Validierung: target_env CPPPATH hat {len(validation_cpppath)} Einträge")\n')
            f.write('        \n')
            f.write('        # Prüfe ob esp-knx-ip.h jetzt gefunden wird\n')
            f.write('        knx_found_after_set = False\n')
            f.write('        for path in validation_cpppath:\n')
            f.write('            path_str = str(path)\n')
            f.write('            knx_header = os.path.join(path_str, "esp-knx-ip.h")\n')
            f.write('            if os.path.exists(knx_header):\n')
            f.write('                print(f"         ✅ esp-knx-ip.h VALIDIERT: {knx_header}")\n')
            f.write('                knx_found_after_set = True\n')
            f.write('                break\n')
            f.write('        \n')
            f.write('        if not knx_found_after_set:\n')
            f.write('            print(f"         🚨 FEHLER: esp-knx-ip.h immer noch nicht gefunden nach CPPPATH-Erweiterung!")\n')
            f.write('            print(f"         🔍 Debug: Erste 10 CPPPATH-Einträge:")\n')
            f.write('            for i, path in enumerate(validation_cpppath[:10]):\n')
            f.write('                print(f"            {i}: {path}")\n')
            f.write('        \n')
            f.write('        critical_restored += 1\n')
            f.write('    else:\n')
            f.write('        print(f"      ❌ FEHLER: Keine CPPPATH-Einträge zum Hinzufügen!")\n')
            f.write('    \n')
            f.write('    # 9. Andere kritische Variablen\n')
            f.write('    critical_vars = [\n')
            f.write('        "CPPDEFINES", "LIBS", "LIBPATH",\n')
            f.write('        "BUILD_FLAGS", "CCFLAGS", "CXXFLAGS", "LINKFLAGS",\n')
            f.write('        "FRAMEWORK_DIR", "PLATFORM_PACKAGES_DIR",\n')
            f.write('        "BOARD", "PLATFORM", "PIOENV", "PIOFRAMEWORK"\n')
            f.write('    ]\n')
            f.write('    \n')
            f.write('    for var in critical_vars:\n')
            f.write('        if var in SCONS_VARS:\n')
            f.write('            try:\n')
            f.write('                target_env[var] = SCONS_VARS[var]\n')
            f.write('                critical_restored += 1\n')
            f.write('            except Exception as e:\n')
            f.write('                print(f"      ⚠ Fehler bei {var}: {e}")\n')
            f.write('    \n')
            f.write('    print(f"✓ {critical_restored} kritische SCons-Variablen wiederhergestellt")\n')
            f.write('    print(f"✓ CPPPATH-Validierung: {len(critical_files_found)} von {len(critical_files)} kritischen Dateien gefunden")\n')
            f.write('    print(f"✓ KNX-Pfade in CPPPATH: {len(knx_paths_in_cpppath)}")\n')
            f.write('    \n')
            f.write('    # Erfolg nur wenn esp-knx-ip.h gefunden wird\n')
            f.write('    success = len(all_cpppath) > 5 and critical_restored >= 5 and "esp-knx-ip.h" in critical_files_found\n')
            f.write('    print(f"✓ Robuste Wiederherstellung erfolgreich: {success}")\n')
            f.write('    return success\n')
            f.write('\n')
            
            # Convenience-Funktionen
            f.write('def get_complete_cpppath():\n')
            f.write('    """Gibt vollständige CPPPATH-Einträge zurück"""\n')
            f.write('    return LDF_VARS.get("LIB_VARS", {}).get("CPPPATH_COMPLETE", [])\n\n')
            
            f.write('def get_cpppath_sources():\n')
            f.write('    """Gibt CPPPATH-Einträge nach Quelle gruppiert zurück"""\n')
            f.write('    return LDF_VARS.get("LIB_VARS", {}).get("CPPPATH_SOURCES", {})\n\n')
            
            f.write('def get_recursive_lib_info():\n')
            f.write('    """Gibt rekursive Library-Information zurück"""\n')
            f.write('    sources = get_cpppath_sources()\n')
            f.write('    return {\n')
            f.write('        "recursive_lib_dirs": sources.get("recursive_lib_dirs", []),\n')
            f.write('        "recursive_header_dirs": sources.get("recursive_header_dirs", [])\n')
            f.write('    }\n\n')
            
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
            f.write(f'COMPLETE_CPPPATH_FROM_ALL_SOURCES = True\n')
            f.write(f'RECURSIVE_LIB_CAPTURE = True\n')
            f.write(f'SAFE_SCONS_CONVERSION = True\n')
            f.write(f'ROBUST_CPPPATH_RESTORE = True\n')
            f.write(f'ALL_INCLUDES_TO_CPPPATH = True\n')
            f.write(f'CONVERTED_FILE_PATHS = {complete_data["CONVERSION_STATS"]["file_paths"]}\n')
            f.write(f'CONVERTED_CLVAR_OBJECTS = {complete_data["CONVERSION_STATS"]["clvar_converted"]}\n')
            f.write(f'CONVERTED_SCONS_OBJECTS = {complete_data["CONVERSION_STATS"]["scons_converted"]}\n')
            
            # Main-Block
            f.write('\nif __name__ == "__main__":\n')
            f.write('    import os\n')
            f.write('    print("PlatformIO LDF SCons Variables Export (Robuste CPPPATH-Wiederherstellung)")\n')
            f.write('    diff = analyze_cpppath_diff()\n')
            f.write('    print(f"Original CPPPATH: {diff[\\"original_count\\"]} Einträge")\n')
            f.write('    print(f"Vollständige CPPPATH: {diff[\\"complete_count\\"]} Einträge")\n')
            f.write('    print(f"Vom LDF hinzugefügt: {diff[\\"ldf_added_count\\"]} Einträge")\n')
            f.write('    lib_builders = get_lib_builders_info()\n')
            f.write('    print(f"Library Builders: {len(lib_builders)}")\n')
            f.write('    recursive_info = get_recursive_lib_info()\n')
            f.write('    print(f"Rekursive Lib-Roots: {len(recursive_info[\\"recursive_lib_dirs\\"])}")\n')
            f.write('    print(f"Rekursive Header-Dirs: {len(recursive_info[\\"recursive_header_dirs\\"])}")\n')
            f.write('    sources = get_cpppath_sources()\n')
            f.write('    print("CPPPATH-Quellen:")\n')
            f.write('    for source_name, source_paths in sources.items():\n')
            f.write('        if isinstance(source_paths, list):\n')
            f.write('            print(f"  {source_name}: {len(source_paths)} Pfade")\n')
        
        # Atomarer Move
        shutil.move(temp_file, cache_file)
        
        # JSON-Export zusätzlich
        json_file = cache_file.replace('.py', '.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(complete_data, f, indent=2, ensure_ascii=False, default=str)
        
        file_size = os.path.getsize(cache_file)
        cpppath_count = len(complete_data['LDF_VARS'].get('LIB_VARS', {}).get('CPPPATH_COMPLETE', []))
        
        print(f"✓ Vollständige SCons-Environment mit robuster CPPPATH-Wiederherstellung gespeichert:")
        print(f"   📁 {os.path.basename(cache_file)} ({file_size} Bytes)")
        print(f"   📊 {len(complete_data['SCONS_VARS'])} SCons-Variablen")
        print(f"   📄 {cpppath_count} CPPPATH-Einträge (sichere SCons-Konvertierung)")
        print(f"   🔄 {complete_data['CONVERSION_STATS']['file_paths']} SCons-Pfad-Objekte konvertiert")
        print(f"   🔄 {complete_data['CONVERSION_STATS']['clvar_converted']} CLVar-Objekte konvertiert")
        print(f"   🔄 {complete_data['CONVERSION_STATS']['scons_converted']} SCons-Objekte konvertiert")
        print(f"   📋 JSON-Export: {os.path.basename(json_file)}")
        print(f"   🛡️ Sichere SCons-Konvertierung: Aktiviert")
        print(f"   🔄 Rekursive lib-Sicherung: Aktiviert")
        print(f"   💪 Robuste CPPPATH-Wiederherstellung: Aktiviert")
        
        return True
        
    except Exception as e:
        print(f"❌ Vollständige Environment-Erfassung mit robuster CPPPATH-Wiederherstellung fehlgeschlagen: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def trigger_complete_environment_capture():
    """Triggert vollständige Environment-Erfassung mit sicherer SCons-Konvertierung"""
    global _backup_created
    
    if _backup_created:
        return
    
    try:
        print(f"🎯 Triggere vollständige Environment-Erfassung mit sicherer SCons-Konvertierung...")
        
        # Vollständige Environment-Erfassung mit sicherer SCons-Konvertierung
        complete_data = capture_complete_scons_environment()
        
        cpppath_count = len(complete_data['LDF_VARS'].get('LIB_VARS', {}).get('CPPPATH_COMPLETE', []))
        
        if cpppath_count > 5:
            if freeze_complete_scons_configuration(complete_data):
                env_name = env.get("PIOENV")
                if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                    print(f"🚀 Vollständige Environment mit robuster CPPPATH-Wiederherstellung erfolgreich erfasst!")
                    _backup_created = True
                else:
                    print(f"⚠ lib_ldf_mode konnte nicht gesetzt werden")
            else:
                print(f"❌ Environment-Speicherung fehlgeschlagen")
        else:
            print(f"⚠ Zu wenige CPPPATH-Einträge ({cpppath_count}) - LDF möglicherweise unvollständig")
    
    except Exception as e:
        print(f"❌ Vollständige Environment-Erfassung mit sicherer SCons-Konvertierung Fehler: {e}")

def restore_complete_scons_configuration():
    """Lädt vollständige Environment mit robuster CPPPATH-Wiederherstellung aus Python-Datei"""
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
        
        # Prüfe ob vollständige CPPPATH mit robuster Wiederherstellung
        complete_cpppath_all_sources = getattr(env_module, 'COMPLETE_CPPPATH_FROM_ALL_SOURCES', False)
        complete_capture = getattr(env_module, 'COMPLETE_CAPTURE', False)
        recursive_lib_capture = getattr(env_module, 'RECURSIVE_LIB_CAPTURE', False)
        safe_scons_conversion = getattr(env_module, 'SAFE_SCONS_CONVERSION', False)
        robust_cpppath_restore = getattr(env_module, 'ROBUST_CPPPATH_RESTORE', False)
        all_includes_to_cpppath = getattr(env_module, 'ALL_INCLUDES_TO_CPPPATH', False)
        
        if all([complete_cpppath_all_sources, complete_capture, recursive_lib_capture, 
                safe_scons_conversion, robust_cpppath_restore, all_includes_to_cpppath]):
            print("✅ Cache stammt von vollständiger robuster CPPPATH-Erfassung")
        else:
            print("⚠️ Cache stammt von älterer Version")
        
        # Environment wiederherstellen
        success = env_module.restore_environment(env)
        
        if success:
            scons_var_count = getattr(env_module, 'SCONS_VAR_COUNT', 0)
            ldf_categories = getattr(env_module, 'LDF_CATEGORIES', 0)
            converted_file_paths = getattr(env_module, 'CONVERTED_FILE_PATHS', 0)
            converted_clvar = getattr(env_module, 'CONVERTED_CLVAR_OBJECTS', 0)
            converted_scons = getattr(env_module, 'CONVERTED_SCONS_OBJECTS', 0)
            
            print(f"✓ Vollständige Environment mit robuster CPPPATH-Wiederherstellung:")
            print(f"   📊 {scons_var_count} SCons-Variablen")
            print(f"   📋 {ldf_categories} LDF-Kategorien")
            print(f"   📄 {converted_file_paths} SCons-Pfad-Objekte konvertiert")
            print(f"   🔄 {converted_clvar} CLVar-Objekte konvertiert")
            print(f"   🔄 {converted_scons} SCons-Objekte konvertiert")
            print(f"   ✅ Robuste CPPPATH-Wiederherstellung erfolgreich")
        
        return success
        
    except Exception as e:
        print(f"❌ Vollständige Cache-Wiederherstellung mit robuster CPPPATH fehlgeschlagen: {e}")
        return False

def enhanced_cache_validation():
    """Erweiterte Cache-Gültigkeitsprüfung mit robuster CPPPATH-Wiederherstellung"""
    print(f"🔍 Erweiterte Cache-Validierung mit robuster CPPPATH-Wiederherstellung...")
    
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        print(f"📝 Kein Cache vorhanden")
        return False
    
    try:
        # Lade Cache-Modul
        spec = importlib.util.spec_from_file_location("scons_env_cache", cache_file)
        env_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(env_module)
        
        # Prüfe alle erforderlichen Features
        required_features = {
            'COMPLETE_CPPPATH_FROM_ALL_SOURCES': getattr(env_module, 'COMPLETE_CPPPATH_FROM_ALL_SOURCES', False),
            'RECURSIVE_LIB_CAPTURE': getattr(env_module, 'RECURSIVE_LIB_CAPTURE', False),
            'SAFE_SCONS_CONVERSION': getattr(env_module, 'SAFE_SCONS_CONVERSION', False),
            'ROBUST_CPPPATH_RESTORE': getattr(env_module, 'ROBUST_CPPPATH_RESTORE', False),
            'ALL_INCLUDES_TO_CPPPATH': getattr(env_module, 'ALL_INCLUDES_TO_CPPPATH', False),
        }
        
        missing_features = [name for name, present in required_features.items() if not present]
        
        if missing_features:
            print(f"⚠️ Cache fehlen Features: {', '.join(missing_features)}")
            return False
        
        # Prüfe CPPPATH-Vollständigkeit
        try:
            complete_cpppath = env_module.get_complete_cpppath()
            if len(complete_cpppath) < 5:
                print("⚠️ Cache enthält zu wenige CPPPATH-Einträge")
                return False
        except:
            print("⚠️ Cache-CPPPATH nicht zugänglich")
            return False
        
        # Prüfe kritische Variablen
        scons_vars = getattr(env_module, 'SCONS_VARS', {})
        critical_vars_present = all([
            var in scons_vars for var in [
                'CPPPATH', 'LIBS', 'LIBPATH', 'BOARD'
            ]
        ])
        
        if not critical_vars_present:
            print("⚠️ Cache fehlen kritische Variablen")
            return False
        
        print(f"✅ Erweiterte Cache-Validierung mit robuster CPPPATH-Wiederherstellung erfolgreich:")
        print(f"   📊 {len(scons_vars)} SCons-Variablen")
        print(f"   📁 {len(complete_cpppath)} CPPPATH-Einträge")
        print(f"   ✨ Alle erforderlichen Features vorhanden")
        
        return True
        
    except Exception as e:
        print(f"❌ Erweiterte Cache-Validierung mit robuster CPPPATH fehlgeschlagen: {e}")
        return False

def debug_cache_restore():
    """Debuggt die tatsächliche Cache-Wiederherstellung mit robuster CPPPATH"""
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        print("❌ Cache-Datei existiert nicht")
        return
    
    try:
        spec = importlib.util.spec_from_file_location("cache", cache_file)
        cache_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cache_module)
        
        print(f"\n🔍 CACHE-WIEDERHERSTELLUNG DEBUG (robuste CPPPATH):")
        
        # Zeige was im Cache steht
        if hasattr(cache_module, 'get_complete_cpppath'):
            cached_paths = cache_module.get_complete_cpppath()
            print(f"   📁 Cache enthält: {len(cached_paths)} CPPPATH-Einträge")
            
            # Suche nach KNX-relevanten Pfaden
            knx_paths = [p for p in cached_paths if 'knx' in p.lower() or 'esp-knx' in p.lower()]
            print(f"   🔍 KNX-relevante Pfade im Cache: {len(knx_paths)}")
            for knx_path in knx_paths:
                exists = os.path.exists(knx_path)
                print(f"      {'✓' if exists else '✗'} {knx_path}")
        
        # Zeige CPPPATH-Quellen
        if hasattr(cache_module, 'get_cpppath_sources'):
            sources = cache_module.get_cpppath_sources()
            print(f"   📊 CPPPATH-Quellen im Cache:")
            for source_name, source_paths in sources.items():
                if isinstance(source_paths, list):
                    print(f"      {source_name}: {len(source_paths)} Pfade")
        
        # Zeige aktuellen CPPPATH vor Wiederherstellung
        current_cpppath = env.get('CPPPATH', [])
        print(f"   📋 Aktueller CPPPATH vor Restore: {len(current_cpppath)} Einträge")
        
        # Führe Wiederherstellung durch
        success = cache_module.restore_environment(env)
        print(f"   🔄 Robuste Restore-Funktion Erfolg: {success}")
        
        # Zeige CPPPATH nach Wiederherstellung
        restored_cpppath = env.get('CPPPATH', [])
        print(f"   📋 CPPPATH nach robuster Restore: {len(restored_cpppath)} Einträge")
        
        # Suche nach KNX-Pfaden im wiederhergestellten CPPPATH
        knx_in_restored = []
        for path in restored_cpppath:
            path_str = str(path.abspath) if hasattr(path, 'abspath') else str(path)
            if 'knx' in path_str.lower() or 'esp-knx' in path_str.lower():
                knx_in_restored.append(path_str)
        
        print(f"   🔍 KNX-Pfade im wiederhergestellten CPPPATH: {len(knx_in_restored)}")
        for knx_path in knx_in_restored:
            exists = os.path.exists(knx_path)
            print(f"      {'✓' if exists else '✗'} {knx_path}")
        
        # Suche nach esp-knx-ip.h
        print(f"   🔍 Suche nach esp-knx-ip.h:")
        found_files = []
        for path in restored_cpppath:
            path_str = str(path.abspath) if hasattr(path, 'abspath') else str(path)
            header_file = os.path.join(path_str, 'esp-knx-ip.h')
            if os.path.exists(header_file):
                found_files.append(header_file)
                print(f"      ✅ GEFUNDEN: {header_file}")
        
        if not found_files:
            print(f"      ❌ esp-knx-ip.h NICHT gefunden!")
            
    except Exception as e:
        print(f"❌ Cache-Debug fehlgeschlagen: {e}")

def early_cache_check_and_restore():
    """Prüft Cache und stellt vollständige SCons-Environment mit robuster CPPPATH wieder her"""
    print(f"🔍 Cache-Prüfung (robuste CPPPATH-Wiederherstellung)...")
    
    # Erweiterte Cache-Validierung mit robuster CPPPATH
    if not enhanced_cache_validation():
        return False
    
    current_ldf_mode = get_current_ldf_mode(env.get("PIOENV"))
    
    if current_ldf_mode != 'off':
        print(f"🔄 LDF noch aktiv - robuster CPPPATH-Cache wird nach Build erstellt")
        return False
    
    print(f"⚡ Robuster CPPPATH-Cache verfügbar - stelle Environment wieder her")
    
    # DEBUG: Zeige detaillierte Wiederherstellung
    debug_cache_restore()
    
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
    """Post-Build Hook: Vollständige SCons-Environment-Erfassung mit robuster CPPPATH"""
    global _backup_created
    
    if _backup_created:
        print("✓ Vollständige Environment bereits erfasst - überspringe Post-Build Action")
        return None
    
    try:
        print(f"\n🎯 POST-BUILD: Vollständige SCons-Environment-Erfassung mit robuster CPPPATH")
        print(f"   Target: {[str(t) for t in target]}")
        print(f"   Source: {len(source)} Dateien")
        print(f"   🕐 Timing: NACH vollständigem Build - alle LDF-Daten verfügbar")
        
        # Vollständige Environment-Erfassung mit robuster CPPPATH
        trigger_complete_environment_capture()
        
    except Exception as e:
        print(f"❌ Post-Build vollständige Erfassung Fehler: {e}")
    
    return None

# =============================================================================
# HAUPTLOGIK - ROBUSTE CPPPATH-WIEDERHERSTELLUNG
# =============================================================================

print(f"\n🎯 Vollständige CPPPATH-Erfassung mit robuster Wiederherstellung für: {env.get('PIOENV')}")

# NEUES DEBUG-LOGGING - IMMER AUSFÜHREN
print(f"\n🔍 DEBUG: Aktueller Environment-Zustand:")
current_cpppath = env.get('CPPPATH', [])
print(f"   📋 Aktueller CPPPATH: {len(current_cpppath)} Einträge")

# Suche nach KNX-Pfaden BEVOR Cache-Prüfung
knx_paths_before = []
for path in current_cpppath:
    path_str = safe_convert_to_string(path, "debug_before")
    if 'knx' in path_str.lower() or 'esp-knx' in path_str.lower():
        knx_paths_before.append(path_str)

print(f"   🔍 KNX-Pfade VOR Cache-Prüfung: {len(knx_paths_before)}")
for knx_path in knx_paths_before:
    exists = os.path.exists(knx_path)
    print(f"      {'✓' if exists else '✗'} {knx_path}")

# Suche nach esp-knx-ip.h in aktuellen Pfaden
print(f"   🔍 Suche nach esp-knx-ip.h VOR Cache-Prüfung:")
found_knx_header = False
for path in current_cpppath:
    path_str = safe_convert_to_string(path, "debug_header_search")
    header_file = os.path.join(path_str, 'esp-knx-ip.h')
    if os.path.exists(header_file):
        print(f"      ✅ GEFUNDEN: {header_file}")
        found_knx_header = True

if not found_knx_header:
    print(f"      ❌ esp-knx-ip.h NICHT in aktuellen CPPPATH gefunden!")

# Cache-Prüfung und vollständige SCons-Environment-Wiederherstellung
cache_restored = early_cache_check_and_restore()

if cache_restored:
    print(f"🚀 Build mit robuster CPPPATH-Environment-Cache - LDF übersprungen!")
    
    # ZUSÄTZLICHES DEBUG NACH Cache-Wiederherstellung
    print(f"\n🔍 DEBUG: Environment-Zustand NACH robuster Cache-Wiederherstellung:")
    restored_cpppath = env.get('CPPPATH', [])
    print(f"   📋 Wiederhergestellter CPPPATH: {len(restored_cpppath)} Einträge")
    
    # Suche nach KNX-Pfaden NACH Wiederherstellung
    knx_paths_after = []
    for path in restored_cpppath:
        path_str = safe_convert_to_string(path, "debug_after")
        if 'knx' in path_str.lower() or 'esp-knx' in path_str.lower():
            knx_paths_after.append(path_str)
    
    print(f"   🔍 KNX-Pfade NACH robuster Cache-Wiederherstellung: {len(knx_paths_after)}")
    for knx_path in knx_paths_after:
        exists = os.path.exists(knx_path)
        print(f"      {'✓' if exists else '✗'} {knx_path}")
    
    # Suche nach esp-knx-ip.h NACH Wiederherstellung
    print(f"   🔍 Suche nach esp-knx-ip.h NACH robuster Cache-Wiederherstellung:")
    found_knx_header_after = False
    for path in restored_cpppath:
        path_str = safe_convert_to_string(path, "debug_header_after")
        header_file = os.path.join(path_str, 'esp-knx-ip.h')
        if os.path.exists(header_file):
            print(f"      ✅ GEFUNDEN: {header_file}")
            found_knx_header_after = True
    
    if not found_knx_header_after:
        print(f"      ❌ esp-knx-ip.h NICHT in wiederhergestellten CPPPATH gefunden!")
        print(f"      🚨 PROBLEM: Include-Pfad für KNX fehlt nach robuster Cache-Wiederherstellung!")
    
    # Vergleiche CPPPATH vor und nach Wiederherstellung
    print(f"\n📊 CPPPATH-Vergleich:")
    print(f"   Vor Cache: {len(knx_paths_before)} KNX-Pfade")
    print(f"   Nach Cache: {len(knx_paths_after)} KNX-Pfade")
    
    if len(knx_paths_before) != len(knx_paths_after):
        print(f"   🚨 UNTERSCHIED: KNX-Pfade haben sich geändert!")
        missing_paths = set(knx_paths_before) - set(knx_paths_after)
        if missing_paths:
            print(f"   ❌ Fehlende KNX-Pfade:")
            for missing in missing_paths:
                print(f"      - {missing}")

else:
    print(f"📝 Normaler LDF-Durchlauf - robuste CPPPATH-Erfassung nach Build...")
    
    # Post-Build Hook für vollständige Environment-Erfassung mit robuster CPPPATH
    env.AddPostAction("$BUILD_DIR/${PROGNAME}.elf", post_build_complete_capture)
    print(f"✅ Post-Build Hook für robuste CPPPATH-Erfassung registriert")
    print(f"🔍 Erfasst ALLE CPPPATH-Einträge durch vollständige LDF-Verarbeitung")

print(f"🏁 Robuste CPPPATH-SCons-Environment-Erfassung initialisiert")
print(f"💡 Reset: rm -rf .pio/ldf_cache/")
print(f"💡 Nach erfolgreichem Build: lib_ldf_mode = off für nachfolgende Builds")
print(f"🎯 Garantiert: Sichere SCons-Konvertierung und robuste CPPPATH-Wiederherstellung")
print(f"🛡️ Features: Rekursive lib-Erfassung, sichere SCons-Konvertierung, robuste Wiederherstellung\n")
