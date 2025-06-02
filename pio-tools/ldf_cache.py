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
    """Erfasst CPPPATH-Einträge nach LDF-Verarbeitung mit rekursiver lib-Erfassung"""
    print(f"\n📁 VOLLSTÄNDIGE CPPPATH-ERFASSUNG MIT REKURSIVER LIB-SICHERUNG:")
    
    # Sammle CPPPATH aus verschiedenen Quellen - ORIGINAL VERSION
    cpppath_sources = {
        'original_env': [str(p.abspath) if hasattr(p, 'abspath') else str(p) for p in env.get('CPPPATH', [])],
        'project_include_dirs': [],
        'lib_include_dirs': [],
        'dependency_include_dirs': [],
        'framework_include_dirs': [],
        'recursive_lib_dirs': [],
        'recursive_header_dirs': [],
    }
    
    # NEUE: Rekursive Library-Verzeichnis-Erfassung
    lib_roots, header_dirs = capture_recursive_lib_directories()
    cpppath_sources['recursive_lib_dirs'] = lib_roots
    cpppath_sources['recursive_header_dirs'] = header_dirs
    
    # Project Include Directories
    try:
        project_builder = None
        lib_builders = env.GetLibBuilders()
        for lb in lib_builders:
            if hasattr(lb, '__class__') and 'ProjectAsLibBuilder' in lb.__class__.__name__:
                project_builder = lb
                break
        
        if project_builder:
            project_includes = project_builder.get_include_dirs()
            cpppath_sources['project_include_dirs'] = [str(p.abspath) if hasattr(p, 'abspath') else str(p) for p in project_includes]
    except:
        pass
    
    # Library Include Directories (nach LDF-Verarbeitung)
    try:
        lib_builders = env.GetLibBuilders()
        print(f"   📚 Aktive Library Builders: {len(lib_builders)}")
        
        for lb in lib_builders:
            try:
                # Erzwinge LDF-Verarbeitung falls noch nicht geschehen
                if not getattr(lb, '_deps_are_processed', False):
                    lb.search_deps_recursive()
                
                # Sammle Include-Verzeichnisse
                include_dirs = lb.get_include_dirs()
                for inc_dir in include_dirs:
                    inc_path = str(inc_dir.abspath) if hasattr(inc_dir, 'abspath') else str(inc_dir)
                    if inc_path not in cpppath_sources['lib_include_dirs']:
                        cpppath_sources['lib_include_dirs'].append(inc_path)
                
                # Sammle auch CPPPATH aus dem Library Environment
                lib_cpppath = lb.env.get('CPPPATH', [])
                for lib_path in lib_cpppath:
                    lib_path_str = str(lib_path.abspath) if hasattr(lib_path, 'abspath') else str(lib_path)
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
                        inc_path = str(inc_dir.abspath) if hasattr(inc_dir, 'abspath') else str(inc_dir)
                        knx_header = os.path.join(inc_path, 'esp-knx-ip.h')
                        if os.path.exists(knx_header):
                            print(f"         ✅ esp-knx-ip.h: {knx_header}")
                
            except Exception as e:
                print(f"      ⚠ Warnung: Konnte Include-Dirs für {getattr(lb, 'name', 'Unknown')} nicht erfassen: {e}")
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
    
    # Sammle alle eindeutigen CPPPATH-Einträge
    all_cpppath = set()
    for source, paths in cpppath_sources.items():
        if isinstance(paths, (list, tuple)):
            for path in paths:
                if isinstance(path, str):
                    expanded_path = env.subst(path)
                    all_cpppath.add(expanded_path)
                elif hasattr(path, 'abspath'):
                    all_cpppath.add(str(path.abspath))
                else:
                    all_cpppath.add(str(path))
    
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
    """Erweiterte Exportfunktion mit vollständiger CPPPATH-Erfassung und rekursiver lib-Sicherung"""
    print(f"\n🎯 ERWEITERTE LDF-VARIABLE-ERFASSUNG MIT REKURSIVER LIB-SICHERUNG:")
    
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
    
    # Erfasse CPPPATH nach LDF-Verarbeitung mit rekursiver lib-Erfassung
    cpppath_sources, complete_cpppath = capture_ldf_cpppath()
    
    # Aktualisierte LDF-Variablen
    ldf_variables = {}
    
    # Build-Environment Variablen (mit vollständiger CPPPATH)
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
    
    # Erweiterte Library-Variablen mit vollständiger CPPPATH-Analyse und rekursiver lib-Sicherung
    ldf_variables['LIB_VARS'] = {
        'LIBSOURCE_DIRS': env.get('LIBSOURCE_DIRS', []),
        'CPPPATH_ORIGINAL': [str(p.abspath) if hasattr(p, 'abspath') else str(p) for p in env.get('CPPPATH', [])],
        'CPPPATH_COMPLETE': complete_cpppath,
        'CPPPATH_SOURCES': {k: [str(p.abspath) if hasattr(p, 'abspath') else str(p) for p in v] if isinstance(v, list) else v for k, v in cpppath_sources.items()},
        'LIBPATH': [str(p.abspath) if hasattr(p, 'abspath') else str(p) for p in env.get('LIBPATH', [])],
        'LIBS': env.get('LIBS', []),
        'LINKFLAGS': env.get('LINKFLAGS', []),
        'CPPDEFINES': list(env.get('CPPDEFINES', [])),
        'SRC_FILTER': env.get('SRC_FILTER', ''),
        'SRC_BUILD_FLAGS': env.get('SRC_BUILD_FLAGS', ''),
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
        print(f"   ⚠ Fehler beim Erfassen der Library Builders: {e}")
    
    ldf_variables['LIB_BUILDERS'] = lib_builders_info
    
    # Erweiterte Metadaten
    ldf_variables['METADATA'] = {
        'export_timestamp': datetime.now().isoformat(),
        'platformio_version': env.get('PLATFORMIO_VERSION', 'Unknown'),
        'python_version': env.get('PYTHONVERSION', 'Unknown'),
        'total_lib_builders': len(lib_builders_info),
        'total_cpppath_entries': len(complete_cpppath),
        'recursive_lib_capture': True,
        'ldf_processing_triggered': True,
    }
    
    print(f"   ✅ LDF-Variablen erfasst: {len(ldf_variables)} Kategorien")
    print(f"   📁 Vollständige CPPPATH: {len(complete_cpppath)} Einträge")
    print(f"   📚 Library Builders: {len(lib_builders_info)} erfasst")
    print(f"   🔄 Rekursive lib-Erfassung: Aktiviert")
    
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
    
    # 3. SCons.Node.FS.File und ähnliche Node-Objekte
    if hasattr(value, 'abspath'):
        return str(value.abspath)
    elif hasattr(value, 'path'):
        return str(value.path)
    elif hasattr(value, 'get_path'):
        try:
            return str(value.get_path())
        except:
            return str(value)
    
    # 4. Andere SCons-Objekte
    elif hasattr(value, '__class__') and 'SCons' in str(value.__class__):
        class_name = value.__class__.__name__
        if 'Builder' in class_name:
            return f"<Builder:{getattr(value, 'name', 'Unknown')}>"
        elif 'Scanner' in class_name:
            return f"<Scanner:{getattr(value, 'name', 'Unknown')}>"
        elif 'Environment' in class_name:
            return "<Environment>"
        else:
            return str(value)
    
    # 5. Funktionen und Callables
    elif callable(value):
        if hasattr(value, '__name__'):
            return f"<Function:{value.__name__}>"
        else:
            return f"<Callable:{value.__class__.__name__}>"
    
    # 6. Listen rekursiv verarbeiten
    elif isinstance(value, list):
        converted_list = []
        for item in value:
            converted_item = convert_scons_objects_selective(item, key, depth + 1)
            converted_list.append(converted_item)
        return converted_list
    
    # 7. Tupel rekursiv verarbeiten
    elif isinstance(value, tuple):
        converted_items = []
        for item in value:
            converted_item = convert_scons_objects_selective(item, key, depth + 1)
            converted_items.append(converted_item)
        return tuple(converted_items)
    
    # 8. Dictionaries rekursiv verarbeiten
    elif isinstance(value, dict):
        converted_dict = {}
        for dict_key, dict_value in value.items():
            converted_key = convert_scons_objects_selective(dict_key, key, depth + 1)
            converted_value = convert_scons_objects_selective(dict_value, key, depth + 1)
            converted_dict[converted_key] = converted_value
        return converted_dict
    
    # 9. deque und andere Collections
    elif hasattr(value, '__class__') and value.__class__.__name__ in ['deque', 'UserList']:
        return list(value)
    
    # 10. os.environ und ähnliche Mapping-Objekte
    elif hasattr(value, '__class__') and 'environ' in str(value.__class__).lower():
        return dict(value)
    
    # 11. Primitive Typen UNVERÄNDERT lassen
    elif isinstance(value, (str, int, float, bool, type(None))):
        return value
    
    # 12. Alles andere als String (mit CLVar-Prüfung)
    else:
        str_repr = str(value)
        if 'CLVar' in str_repr:
            print(f"   🚨 UNBEHANDELTE CLVar gefunden in {key}: {str_repr}")
        return str_repr

def capture_complete_scons_environment():
    """Erfasst vollständige SCons-Environment mit funktionierender CPPPATH-Erfassung und rekursiver lib-Sicherung"""
    
    print(f"\n🎯 VOLLSTÄNDIGE SCons-Environment-Erfassung mit rekursiver lib-Sicherung:")
    
    # 1. Erweiterte LDF-Variablen erfassen (mit rekursiver lib-Sicherung)
    ldf_variables = export_ldf_variables_extended()
    
    # 2. Kritische SCons-Variablen direkt erfassen
    critical_vars = [
        'CPPPATH', 'CPPDEFINES', 'LIBS', 'LIBPATH', 
        'BUILD_FLAGS', 'CCFLAGS', 'CXXFLAGS', 'LINKFLAGS',
        'PIOBUILDFILES', 'LIB_DEPS', 'LIB_EXTRA_DIRS',
        'FRAMEWORK_DIR', 'PLATFORM_PACKAGES_DIR',
        'LIBSOURCE_DIRS', 'PROJECT_LIBDEPS_DIR',
        'BOARD', 'PLATFORM', 'PIOENV', 'PIOFRAMEWORK'
    ]
    
    scons_data = {}
    conversion_stats = {"file_paths": 0, "builders": 0, "functions": 0, "clvar_converted": 0, "other": 0}
    
    for var in critical_vars:
        raw_value = env.get(var, [])
        
        if var == 'CPPPATH':
            # Verwende die vollständige CPPPATH aus LDF-Variablen (mit rekursiver lib-Erfassung)
            complete_cpppath = ldf_variables.get('LIB_VARS', {}).get('CPPPATH_COMPLETE', [])
            scons_data[var] = complete_cpppath
            
            print(f"   📁 CPPPATH: {len(complete_cpppath)} Einträge (vollständig mit rekursiver lib-Erfassung)")
            
            # Zeige erste 5 zur Verifikation
            for i, path in enumerate(complete_cpppath[:5]):
                exists = os.path.exists(path)
                print(f"      {i:2d}: {'✓' if exists else '✗'} {path}")
            
            if len(complete_cpppath) > 5:
                print(f"      ... und {len(complete_cpppath) - 5} weitere")
        
        elif isinstance(raw_value, list):
            print(f"   📊 {var}: {len(raw_value)} Einträge")
            # Konvertiere SCons-Objekte zu wiederverwendbaren Daten
            converted_value = convert_scons_objects_selective(raw_value, var)
            scons_data[var] = converted_value
        else:
            print(f"   📊 {var}: {type(raw_value).__name__}")
            # Konvertiere SCons-Objekte zu wiederverwendbaren Daten
            converted_value = convert_scons_objects_selective(raw_value, var)
            scons_data[var] = converted_value
        
        # Zähle Konvertierungen
        if isinstance(raw_value, list):
            for item in raw_value:
                if hasattr(item, 'abspath'):
                    conversion_stats["file_paths"] += 1
                elif 'CLVar' in str(type(item)):
                    conversion_stats["clvar_converted"] += 1
    
    # 3. Kombiniere SCons-Daten mit LDF-Variablen
    complete_data = {
        'SCONS_VARS': scons_data,
        'LDF_VARS': ldf_variables,
        'CONVERSION_STATS': conversion_stats
    }
    
    print(f"   🔄 {conversion_stats['file_paths']} SCons-Pfad-Objekte konvertiert")
    print(f"   🔄 {conversion_stats['clvar_converted']} CLVar-Objekte konvertiert")
    print(f"   ✅ String-Pfade blieben unverändert")
    print(f"   📊 LDF-Variablen: {len(ldf_variables)} Kategorien")
    print(f"   🔄 Rekursive lib-Sicherung: Aktiviert")
    
    return complete_data

def freeze_complete_scons_configuration(complete_data):
    """Speichert vollständige SCons-Environment mit verbesserter CPPPATH-Wiederherstellung"""
    cache_file = get_cache_file_path()
    temp_file = cache_file + ".tmp"
    
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write("#!/usr/bin/env python3\n")
            f.write("# -*- coding: utf-8 -*-\n")
            f.write('"""\n')
            f.write('PlatformIO LDF SCons Variables Export - Verbesserte CPPPATH-Wiederherstellung\n')
            f.write(f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'Environment: {env.get("PIOENV")}\n')
            f.write('"""\n\n')
            
            # SCons-Daten
            f.write('# SCons Environment Variables\n')
            f.write('SCONS_VARS = ')
            f.write(repr(complete_data['SCONS_VARS']))
            f.write('\n\n')
            
            # LDF-Daten
            f.write('# LDF Variables (vollständig mit CPPPATH und rekursiver lib-Sicherung)\n')
            f.write('LDF_VARS = ')
            f.write(repr(complete_data['LDF_VARS']))
            f.write('\n\n')
            
            # VERBESSERTE CPPPATH-Wiederherstellung - ERWEITERT STATT ÜBERSCHREIBT
            f.write('def restore_environment(target_env):\n')
            f.write('    """VERBESSERTE CPPPATH-Wiederherstellung - erweitert existierende Pfade"""\n')
            f.write('    import os\n')
            f.write('    restored_count = 0\n')
            f.write('    critical_restored = 0\n')
            f.write('    \n')
            f.write('    print("Starte verbesserte CPPPATH-Wiederherstellung...")\n')
            f.write('    \n')
            f.write('    # Sammle ALLE CPPPATH aus allen Quellen\n')
            f.write('    all_new_paths = []\n')
            f.write('    \n')
            f.write('    # Basis-CPPPATH\n')
            f.write('    complete_cpppath = LDF_VARS.get("LIB_VARS", {}).get("CPPPATH_COMPLETE", [])\n')
            f.write('    all_new_paths.extend(complete_cpppath)\n')
            f.write('    print(f"   Basis CPPPATH_COMPLETE: {len(complete_cpppath)} Eintraege")\n')
            f.write('    \n')
            f.write('    # Alle CPPPATH-Quellen\n')
            f.write('    cpppath_sources = LDF_VARS.get("LIB_VARS", {}).get("CPPPATH_SOURCES", {})\n')
            f.write('    for source_name, source_paths in cpppath_sources.items():\n')
            f.write('        if isinstance(source_paths, list):\n')
            f.write('            all_new_paths.extend(source_paths)\n')
            f.write('            print(f"   {source_name}: {len(source_paths)} Pfade hinzugefuegt")\n')
            f.write('    \n')
            f.write('    # ERWEITERE existierende CPPPATH (ueberschreibe NICHT!)\n')
            f.write('    existing_cpppath = list(target_env.get("CPPPATH", []))\n')
            f.write('    existing_strings = [str(p) for p in existing_cpppath]\n')
            f.write('    print(f"   Existierende CPPPATH: {len(existing_strings)} Eintraege")\n')
            f.write('    \n')
            f.write('    added_count = 0\n')
            f.write('    knx_paths_added = 0\n')
            f.write('    for new_path in all_new_paths:\n')
            f.write('        if isinstance(new_path, str) and new_path.strip() and new_path not in existing_strings:\n')
            f.write('            existing_cpppath.append(new_path)\n')
            f.write('            existing_strings.append(new_path)\n')
            f.write('            added_count += 1\n')
            f.write('            \n')
            f.write('            # Debug fuer KNX-Pfade\n')
            f.write('            if "knx" in new_path.lower() or "esp-knx" in new_path.lower():\n')
            f.write('                knx_paths_added += 1\n')
            f.write('                print(f"      KNX-Pfad hinzugefuegt: {new_path}")\n')
            f.write('    \n')
            f.write('    # SETZE erweiterte CPPPATH\n')
            f.write('    target_env["CPPPATH"] = existing_cpppath\n')
            f.write('    print(f"   CPPPATH erweitert: +{added_count} = {len(existing_cpppath)} total")\n')
            f.write('    print(f"   KNX-Pfade hinzugefuegt: {knx_paths_added}")\n')
            f.write('    critical_restored += 1\n')
            f.write('    \n')
            f.write('    # Validierung: Pruefe esp-knx-ip.h\n')
            f.write('    knx_header_found = False\n')
            f.write('    for cpppath in existing_cpppath:\n')
            f.write('        path_str = str(cpppath)\n')
            f.write('        knx_header = os.path.join(path_str, "esp-knx-ip.h")\n')
            f.write('        if os.path.exists(knx_header):\n')
            f.write('            print(f"   esp-knx-ip.h GEFUNDEN: {knx_header}")\n')
            f.write('            knx_header_found = True\n')
            f.write('            break\n')
            f.write('    \n')
            f.write('    if not knx_header_found:\n')
            f.write('        print("   WARNUNG: esp-knx-ip.h NICHT gefunden!")\n')
            f.write('    \n')
            f.write('    # Andere kritische Variablen\n')
            f.write('    critical_vars = ["CPPDEFINES", "LIBS", "LIBPATH", "BUILD_FLAGS", "CCFLAGS", "CXXFLAGS", "LINKFLAGS"]\n')
            f.write('    for var in critical_vars:\n')
            f.write('        if var in SCONS_VARS:\n')
            f.write('            try:\n')
            f.write('                target_env[var] = SCONS_VARS[var]\n')
            f.write('                critical_restored += 1\n')
            f.write('            except Exception as e:\n')
            f.write('                print(f"   Fehler bei {var}: {e}")\n')
            f.write('    \n')
            f.write('    print(f"Verbesserte Wiederherstellung abgeschlossen: {critical_restored} kritische Variablen")\n')
            f.write('    return critical_restored >= 2 and knx_header_found\n')
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
            f.write(f'IMPROVED_CPPPATH_RESTORE = True\n')
            f.write(f'ALL_INCLUDES_TO_CPPPATH = True\n')
            f.write(f'CONVERTED_FILE_PATHS = {complete_data["CONVERSION_STATS"]["file_paths"]}\n')
            f.write(f'CONVERTED_CLVAR_OBJECTS = {complete_data["CONVERSION_STATS"]["clvar_converted"]}\n')
            
            # Main-Block
            f.write('\nif __name__ == "__main__":\n')
            f.write('    import os\n')
            f.write('    print("PlatformIO LDF SCons Variables Export (Verbesserte CPPPATH-Wiederherstellung)")\n')
            f.write('    diff = analyze_cpppath_diff()\n')
            f.write('    print(f"Original CPPPATH: {diff[\\"original_count\\"]} Eintraege")\n')
            f.write('    print(f"Vollstaendige CPPPATH: {diff[\\"complete_count\\"]} Eintraege")\n')
            f.write('    print(f"Vom LDF hinzugefuegt: {diff[\\"ldf_added_count\\"]} Eintraege")\n')
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
        
        print(f"✓ Vollständige SCons-Environment mit verbesserter CPPPATH-Wiederherstellung gespeichert:")
        print(f"   📁 {os.path.basename(cache_file)} ({file_size} Bytes)")
        print(f"   📊 {len(complete_data['SCONS_VARS'])} SCons-Variablen")
        print(f"   📄 {cpppath_count} CPPPATH-Einträge (vollständige Erfassung)")
        print(f"   🔄 {complete_data['CONVERSION_STATS']['file_paths']} SCons-Objekte konvertiert")
        print(f"   🔄 {complete_data['CONVERSION_STATS']['clvar_converted']} CLVar-Objekte konvertiert")
        print(f"   📋 JSON-Export: {os.path.basename(json_file)}")
        print(f"   🔄 Rekursive lib-Sicherung: Aktiviert")
        print(f"   ✅ Verbesserte CPPPATH-Wiederherstellung: Aktiviert")
        
        return True
        
    except Exception as e:
        print(f"❌ Vollständige Environment-Erfassung mit verbesserter CPPPATH fehlgeschlagen: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def trigger_complete_environment_capture():
    """Triggert vollständige Environment-Erfassung mit CPPPATH aus allen Quellen und rekursiver lib-Sicherung"""
    global _backup_created
    
    if _backup_created:
        return
    
    try:
        print(f"🎯 Triggere vollständige Environment-Erfassung mit verbesserter CPPPATH...")
        
        # Vollständige Environment-Erfassung mit rekursiver lib-Sicherung
        complete_data = capture_complete_scons_environment()
        
        cpppath_count = len(complete_data['LDF_VARS'].get('LIB_VARS', {}).get('CPPPATH_COMPLETE', []))
        
        if cpppath_count > 5:
            if freeze_complete_scons_configuration(complete_data):
                env_name = env.get("PIOENV")
                if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                    print(f"🚀 Vollständige Environment mit verbesserter CPPPATH erfolgreich erfasst!")
                    _backup_created = True
                else:
                    print(f"⚠ lib_ldf_mode konnte nicht gesetzt werden")
            else:
                print(f"❌ Environment-Speicherung fehlgeschlagen")
        else:
            print(f"⚠ Zu wenige CPPPATH-Einträge ({cpppath_count}) - LDF möglicherweise unvollständig")
    
    except Exception as e:
        print(f"❌ Vollständige Environment-Erfassung mit verbesserter CPPPATH Fehler: {e}")

def restore_complete_scons_configuration():
    """Lädt vollständige Environment mit verbesserter CPPPATH-Wiederherstellung aus Python-Datei"""
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
        
        # Prüfe ob verbesserte CPPPATH-Wiederherstellung
        complete_cpppath_all_sources = getattr(env_module, 'COMPLETE_CPPPATH_FROM_ALL_SOURCES', False)
        complete_capture = getattr(env_module, 'COMPLETE_CAPTURE', False)
        recursive_lib_capture = getattr(env_module, 'RECURSIVE_LIB_CAPTURE', False)
        improved_cpppath_restore = getattr(env_module, 'IMPROVED_CPPPATH_RESTORE', False)
        all_includes_to_cpppath = getattr(env_module, 'ALL_INCLUDES_TO_CPPPATH', False)
        
        if all([complete_cpppath_all_sources, complete_capture, recursive_lib_capture, 
                improved_cpppath_restore, all_includes_to_cpppath]):
            print("✅ Cache stammt von verbesserter CPPPATH-Wiederherstellung")
        else:
            print("⚠️ Cache stammt von älterer Version")
        
        # Environment wiederherstellen
        success = env_module.restore_environment(env)
        
        if success:
            scons_var_count = getattr(env_module, 'SCONS_VAR_COUNT', 0)
            ldf_categories = getattr(env_module, 'LDF_CATEGORIES', 0)
            converted_file_paths = getattr(env_module, 'CONVERTED_FILE_PATHS', 0)
            converted_clvar = getattr(env_module, 'CONVERTED_CLVAR_OBJECTS', 0)
            
            print(f"✓ Vollständige Environment mit verbesserter CPPPATH wiederhergestellt:")
            print(f"   📊 {scons_var_count} SCons-Variablen")
            print(f"   📋 {ldf_categories} LDF-Kategorien")
            print(f"   📄 {converted_file_paths} SCons-Pfad-Objekte konvertiert")
            print(f"   🔄 {converted_clvar} CLVar-Objekte konvertiert")
            print(f"   ✅ Verbesserte CPPPATH-Wiederherstellung erfolgreich")
        
        return success
        
    except Exception as e:
        print(f"❌ Vollständige Cache-Wiederherstellung mit verbesserter CPPPATH fehlgeschlagen: {e}")
        return False



