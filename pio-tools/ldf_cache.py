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
        print(f"[OK] Backup erstellt: {os.path.basename(backup_file)}")
    
    try:
        config = configparser.ConfigParser(allow_no_value=True)
        config.read(env_file, encoding='utf-8')
        
        section_name = f"env:{env_name}"
        
        if not config.has_section(section_name):
            return False
        
        if set_ldf_off:
            config.set(section_name, "lib_ldf_mode", "off")
            print(f"[OK] lib_ldf_mode = off gesetzt in {os.path.basename(env_file)}")
        else:
            if config.has_option(section_name, "lib_ldf_mode"):
                config.remove_option(section_name, "lib_ldf_mode")
                print(f"[OK] lib_ldf_mode entfernt aus {os.path.basename(env_file)}")
        
        with open(env_file, 'w', encoding='utf-8') as f:
            config.write(f, space_around_delimiters=True)
        
        return True
        
    except Exception as e:
        print(f"[WARNUNG] Fehler beim Modifizieren von {os.path.basename(env_file)}: {e}")
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

def should_create_ldf_cache():
    """Prüft ob ein LDF-Cache erstellt werden sollte"""
    cache_file = get_cache_file_path()
    env_name = env.get("PIOENV")
    
    # 1. Kein Cache vorhanden
    if not os.path.exists(cache_file):
        print(f"[INFO] Kein Cache gefunden - Cache wird erstellt")
        return True
    
    # 2. Cache ist zu alt (älter als 1 Tag)
    try:
        cache_age = time.time() - os.path.getmtime(cache_file)
        if cache_age > 24 * 3600:  # 24 Stunden
            print(f"[INFO] Cache ist zu alt ({cache_age/3600:.1f}h) - Cache wird erneuert")
            return True
    except:
        pass
    
    # 3. LDF-Modus hat sich geändert
    current_ldf_mode = get_current_ldf_mode(env_name)
    try:
        # Lade gespeicherten LDF-Modus aus Cache
        cache_globals = {}
        with open(cache_file, 'r', encoding='utf-8') as f:
            exec(f.read(), cache_globals)
        
        cached_ldf_mode = cache_globals.get('LDF_VARS', {}).get('PROJECT_OPTIONS', {}).get('lib_ldf_mode', 'chain')
        
        if current_ldf_mode != cached_ldf_mode:
            print(f"[INFO] LDF-Modus geändert ({cached_ldf_mode} -> {current_ldf_mode}) - Cache wird erneuert")
            return True
    except:
        print(f"[INFO] Cache nicht lesbar - Cache wird erneuert")
        return True
    
    # 4. platformio.ini wurde geändert (neuer als Cache)
    try:
        ini_files = find_all_platformio_files()
        for ini_file in ini_files:
            if os.path.exists(ini_file):
                ini_mtime = os.path.getmtime(ini_file)
                cache_mtime = os.path.getmtime(cache_file)
                if ini_mtime > cache_mtime:
                    print(f"[INFO] {os.path.basename(ini_file)} wurde geändert - Cache wird erneuert")
                    return True
    except:
        pass
    
    print(f"[INFO] Cache ist aktuell - keine Erneuerung nötig")
    return False

def should_trigger_ldf_processing():
    """Prüft ob LDF-Verarbeitung getriggert werden sollte"""
    env_name = env.get("PIOENV")
    current_ldf_mode = get_current_ldf_mode(env_name)
    
    # LDF-Verarbeitung nur wenn LDF aktiv ist
    if current_ldf_mode == "off":
        print(f"[INFO] LDF ist deaktiviert - keine LDF-Verarbeitung")
        return False
    
    # Prüfe ob Libraries vorhanden sind, die LDF benötigen
    try:
        lib_deps = env.GetProjectOption('lib_deps', [])
        if lib_deps:
            print(f"[INFO] {len(lib_deps)} Library-Dependencies gefunden - LDF-Verarbeitung wird getriggert")
            return True
    except:
        pass
    
    # Prüfe lib_extra_dirs
    try:
        lib_extra_dirs = env.GetProjectOption('lib_extra_dirs', [])
        if lib_extra_dirs:
            print(f"[INFO] lib_extra_dirs konfiguriert - LDF-Verarbeitung wird getriggert")
            return True
    except:
        pass
    
    print(f"[INFO] Keine LDF-Verarbeitung nötig")
    return False

def should_disable_ldf():
    """Prüft ob LDF deaktiviert werden sollte"""
    env_name = env.get("PIOENV")
    if not env_name:
        return False
    
    current_mode = get_current_ldf_mode(env_name)
    print(f"[INFO] Aktueller LDF-Modus: {current_mode}")
    
    # Deaktiviere LDF wenn nicht bereits "off"
    return current_mode != "off"

def manage_ldf_mode():
    """Verwaltet LDF-Modus für Cache-Erstellung"""
    env_name = env.get("PIOENV")
    if not env_name:
        return False
    
    print(f"\n[LDF] LDF-MODUS-VERWALTUNG:")
    
    # Prüfe aktuellen LDF-Modus
    if should_disable_ldf():
        print(f"[INFO] Deaktiviere LDF für vollständige Library-Erfassung...")
        
        # Erstelle Backup und setze LDF auf "off"
        if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
            print(f"[OK] LDF-Modus auf 'off' gesetzt")
            return True
        else:
            print(f"[WARNUNG] Konnte LDF-Modus nicht ändern")
            return False
    else:
        print(f"[INFO] LDF bereits deaktiviert")
        return True

def restore_ldf_mode():
    """Stellt ursprünglichen LDF-Modus wieder her"""
    env_name = env.get("PIOENV")
    if not env_name:
        return
    
    print(f"\n[LDF] LDF-MODUS-WIEDERHERSTELLUNG:")
    
    try:
        # Finde Backup-Datei
        env_file = find_env_definition_file(env_name)
        if not env_file:
            project_dir = env.get("PROJECT_DIR")
            env_file = os.path.join(project_dir, "platformio.ini")
        
        backup_file = f"{env_file}.ldf_backup"
        
        if os.path.exists(backup_file):
            # Stelle Original wieder her
            shutil.copy2(backup_file, env_file)
            print(f"[OK] Ursprünglicher LDF-Modus wiederhergestellt")
            
            # Entferne Backup
            os.remove(backup_file)
            print(f"[OK] Backup-Datei entfernt")
        else:
            print(f"[INFO] Kein LDF-Backup gefunden")
            
    except Exception as e:
        print(f"[WARNUNG] Fehler bei LDF-Wiederherstellung: {e}")

def capture_recursive_lib_directories():
    """Erfasst ALLE rekursiven Library-Verzeichnisse aus lib_dir, lib_extra_dirs und shared_libdeps_dir"""
    print(f"\n[ORDNER] REKURSIVE LIBRARY-VERZEICHNIS-ERFASSUNG:")
    
    project_dir = env.get("PROJECT_DIR")
    all_lib_dirs = []
    header_directories = []
    
    # 1. lib_dir erfassen
    try:
        lib_dir = env.GetProjectOption('lib_dir', '')
        if lib_dir:
            print(f"   [INFO] lib_dir: {lib_dir}")
            
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
                    print(f"   [ORDNER] Durchsuche lib_dir rekursiv: {abs_lib_dir}")
                    
                    # VOLLSTÄNDIGE REKURSIVE DURCHSUCHUNG
                    for root, dirs, files in os.walk(abs_lib_dir):
                        # Prüfe ob Verzeichnis Header-Dateien enthält
                        header_files = [f for f in files if f.endswith(('.h', '.hpp', '.hxx', '.inc'))]
                        
                        if header_files:
                            header_directories.append(root)
                            rel_path = os.path.relpath(root, project_dir)
                            print(f"      [OK] lib_dir Header-Dir: {rel_path} ({len(header_files)} Headers)")
                            
                            # Spezielle Prüfung für kritische Header
                            for header in header_files:
                                if header in ['esp-knx-ip.h', 'Arduino.h', 'WiFi.h']:
                                    print(f"         [TARGET] {header} GEFUNDEN!")
                        
                        # Prüfe auf Library-Manifeste
                        if any(manifest in files for manifest in ['library.json', 'library.properties', 'module.json']):
                            if root not in all_lib_dirs:
                                all_lib_dirs.append(root)
                                print(f"      [LIB] lib_dir Library-Root: {os.path.relpath(root, project_dir)}")
                else:
                    print(f"   [FEHLER] lib_dir nicht gefunden: {lib_directory}")
    
    except Exception as e:
        print(f"   [WARNUNG] Fehler beim Erfassen von lib_dir: {e}")
    
    # 2. lib_extra_dirs erfassen
    try:
        lib_extra_dirs = env.GetProjectOption('lib_extra_dirs', [])
        if isinstance(lib_extra_dirs, str):
            lib_extra_dirs = [lib_extra_dirs]
        
        print(f"   [INFO] lib_extra_dirs: {lib_extra_dirs}")
        
        for extra_dir in lib_extra_dirs:
            # Relativer zu absolutem Pfad
            if not os.path.isabs(extra_dir):
                abs_extra_dir = os.path.join(project_dir, extra_dir)
            else:
                abs_extra_dir = extra_dir
            
            if os.path.exists(abs_extra_dir):
                print(f"   [ORDNER] Durchsuche lib_extra_dirs rekursiv: {abs_extra_dir}")
                
                # VOLLSTÄNDIGE REKURSIVE DURCHSUCHUNG
                for root, dirs, files in os.walk(abs_extra_dir):
                    # Prüfe ob Verzeichnis Header-Dateien enthält
                    header_files = [f for f in files if f.endswith(('.h', '.hpp', '.hxx', '.inc'))]
                    
                    if header_files:
                        if root not in header_directories:  # Duplikate vermeiden
                            header_directories.append(root)
                            rel_path = os.path.relpath(root, project_dir)
                            print(f"      [OK] lib_extra_dirs Header-Dir: {rel_path} ({len(header_files)} Headers)")
                            
                            # Spezielle Prüfung für kritische Header
                            for header in header_files:
                                if header in ['esp-knx-ip.h', 'Arduino.h', 'WiFi.h']:
                                    print(f"         [TARGET] {header} GEFUNDEN!")
                    
                    # Prüfe auf Library-Manifeste
                    if any(manifest in files for manifest in ['library.json', 'library.properties', 'module.json']):
                        if root not in all_lib_dirs:
                            all_lib_dirs.append(root)
                            print(f"      [LIB] lib_extra_dirs Library-Root: {os.path.relpath(root, project_dir)}")
                    
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
                                        print(f"      [OK] Subdir-Headers: {os.path.relpath(subdir_path, project_dir)} ({len(subdir_headers)} Headers)")
                                except:
                                    pass
            else:
                print(f"   [FEHLER] lib_extra_dir nicht gefunden: {extra_dir}")
    
    except Exception as e:
        print(f"   [WARNUNG] Fehler beim Erfassen von lib_extra_dirs: {e}")
    
    # 3. shared_libdeps_dir erfassen
    try:
        shared_libdeps_dir = env.GetProjectOption('shared_libdeps_dir', '')
        if shared_libdeps_dir:
            print(f"   [INFO] shared_libdeps_dir: {shared_libdeps_dir}")
            
            if not os.path.isabs(shared_libdeps_dir):
                abs_shared_dir = os.path.join(project_dir, shared_libdeps_dir)
            else:
                abs_shared_dir = shared_libdeps_dir
            
            if os.path.exists(abs_shared_dir):
                print(f"   [ORDNER] Durchsuche shared_libdeps rekursiv: {abs_shared_dir}")
                
                for root, dirs, files in os.walk(abs_shared_dir):
                    header_files = [f for f in files if f.endswith(('.h', '.hpp', '.hxx', '.inc'))]
                    
                    if header_files:
                        if root not in header_directories:
                            header_directories.append(root)
                            print(f"      [OK] Shared-Header-Dir: {os.path.relpath(root, project_dir)} ({len(header_files)} Headers)")
            else:
                print(f"   [FEHLER] shared_libdeps_dir nicht gefunden: {shared_libdeps_dir}")
    
    except Exception as e:
        print(f"   [WARNUNG] Fehler beim Erfassen von shared_libdeps_dir: {e}")
    
    # 4. Standard PlatformIO libdeps erfassen
    try:
        project_libdeps_dir = env.get('PROJECT_LIBDEPS_DIR', '')
        if project_libdeps_dir and os.path.exists(project_libdeps_dir):
            print(f"   [ORDNER] Durchsuche PROJECT_LIBDEPS_DIR: {project_libdeps_dir}")
            
            for root, dirs, files in os.walk(project_libdeps_dir):
                header_files = [f for f in files if f.endswith(('.h', '.hpp', '.hxx', '.inc'))]
                
                if header_files:
                    if root not in header_directories:
                        header_directories.append(root)
                        print(f"      [OK] Libdeps-Header-Dir: {os.path.relpath(root, project_dir)} ({len(header_files)} Headers)")
    
    except Exception as e:
        print(f"   [WARNUNG] Fehler beim Erfassen von PROJECT_LIBDEPS_DIR: {e}")
    
    print(f"   [STATS] Rekursive Erfassung abgeschlossen:")
    print(f"      Library-Roots: {len(all_lib_dirs)}")
    print(f"      Header-Verzeichnisse: {len(header_directories)}")
    
    return all_lib_dirs, header_directories

def capture_ldf_cpppath():
    """Erfasst CPPPATH-Einträge nach LDF-Verarbeitung mit rekursiver lib-Erfassung"""
    print(f"\n[ORDNER] VOLLSTÄNDIGE CPPPATH-ERFASSUNG MIT REKURSIVER LIB-SICHERUNG:")
    
    # Sammle CPPPATH aus verschiedenen Quellen
    cpppath_sources = {
        'original_env': [str(p.abspath) if hasattr(p, 'abspath') else str(p) for p in env.get('CPPPATH', [])],
        'project_include_dirs': [],
        'lib_include_dirs': [],
        'dependency_include_dirs': [],
        'framework_include_dirs': [],
        'recursive_lib_dirs': [],
        'recursive_header_dirs': [],
    }
    
    # Rekursive Library-Verzeichnis-Erfassung
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
        print(f"   [LIB] Aktive Library Builders: {len(lib_builders)}")
        
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
                    print(f"      [TARGET] KNX-Library: {lib_name}")
                    print(f"         Pfad: {lib_path}")
                    print(f"         Include-Dirs: {len(include_dirs)}")
                    for inc_dir in include_dirs:
                        inc_path = str(inc_dir.abspath) if hasattr(inc_dir, 'abspath') else str(inc_dir)
                        knx_header = os.path.join(inc_path, 'esp-knx-ip.h')
                        if os.path.exists(knx_header):
                            print(f"         [OK] esp-knx-ip.h: {knx_header}")
                
            except Exception as e:
                print(f"      [WARNUNG] Konnte Include-Dirs für {getattr(lb, 'name', 'Unknown')} nicht erfassen: {e}")
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
    
    print(f"   [STATS] CPPPATH-Quellen-Statistik:")
    print(f"      Original env CPPPATH: {len(cpppath_sources['original_env'])} Einträge")
    print(f"      Project Include-Dirs: {len(cpppath_sources['project_include_dirs'])} Einträge")
    print(f"      Library Include-Dirs: {len(cpppath_sources['lib_include_dirs'])} Einträge")
    print(f"      Dependency CPPPATH: {len(cpppath_sources['dependency_include_dirs'])} Einträge")
    print(f"      Framework-Pfade: {len(cpppath_sources['framework_include_dirs'])} Einträge")
    print(f"      Rekursive Lib-Roots: {len(cpppath_sources['recursive_lib_dirs'])} Einträge")
    print(f"      Rekursive Header-Dirs: {len(cpppath_sources['recursive_header_dirs'])} Einträge")
    print(f"   [OK] Gesamt eindeutige CPPPATH: {len(all_cpppath)} Einträge")
    
    return cpppath_sources, sorted(list(all_cpppath))

def export_ldf_variables_extended():
    """Erweiterte Exportfunktion mit vollständiger CPPPATH-Erfassung und rekursiver lib-Sicherung"""
    print(f"\n[TARGET] ERWEITERTE LDF-VARIABLE-ERFASSUNG MIT REKURSIVER LIB-SICHERUNG:")
    
    # Erzwinge LDF-Verarbeitung für alle Libraries
    try:
        lib_builders = env.GetLibBuilders()
        print(f"   [LIB] Verarbeite {len(lib_builders)} Library Builders...")
        
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
        print(f"   [WARNUNG] Fehler beim Erfassen der Library Builders: {e}")
    
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
    
    print(f"   [OK] LDF-Variablen erfasst: {len(ldf_variables)} Kategorien")
    print(f"   [ORDNER] Vollständige CPPPATH: {len(complete_cpppath)} Einträge")
    print(f"   [LIB] Library Builders: {len(lib_builders_info)} erfasst")
    print(f"   [SYNC] Rekursive lib-Erfassung: Aktiviert")
    
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
                print(f"   [WARNUNG] CLVar-Konvertierung fehlgeschlagen für {key}: {e}")
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
            print(f"   [WARNUNG] UNBEHANDELTE CLVar gefunden in {key}: {str_repr}")
        return str_repr

def capture_complete_scons_environment():
    """Erfasst vollständige SCons-Environment mit funktionierender CPPPATH-Erfassung und rekursiver lib-Sicherung"""
    
    print(f"\n[TARGET] VOLLSTÄNDIGE SCons-Environment-Erfassung mit rekursiver lib-Sicherung:")
    
    # 1. Erweiterte LDF-Variablen erfassen (mit rekursiver lib-Sicherung)
    ldf_variables = export_ldf_variables_extended()
    
    # 2. Kritische SCons-Variablen direkt erfassen - ERWEITERT UM ALLE COMPILE-RELEVANTEN
    critical_vars = [
        'CPPPATH', 'CPPDEFINES', 'LIBS', 'LIBPATH', 
        'ASFLAGS', 'ASPPFLAGS', 'CFLAGS', 'CXXFLAGS', 'CCFLAGS', 'LINKFLAGS',
        'BUILD_FLAGS', 'PIOBUILDFILES', 'LIB_DEPS', 'LIB_EXTRA_DIRS',
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
            
            print(f"   [ORDNER] CPPPATH: {len(complete_cpppath)} Einträge (vollständig mit rekursiver lib-Erfassung)")
            
            # Zeige erste 5 zur Verifikation
            for i, path in enumerate(complete_cpppath[:5]):
                exists = os.path.exists(path)
                status = "[OK]" if exists else "[FEHLER]"
                print(f"      {i:2d}: {status} {path}")
            
            if len(complete_cpppath) > 5:
                print(f"      ... und {len(complete_cpppath) - 5} weitere")
        
        elif isinstance(raw_value, list):
            print(f"   [STATS] {var}: {len(raw_value)} Einträge")
            # Konvertiere SCons-Objekte zu wiederverwendbaren Daten
            converted_value = convert_scons_objects_selective(raw_value, var)
            scons_data[var] = converted_value
        else:
            print(f"   [STATS] {var}: {type(raw_value).__name__}")
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
    
    print(f"   [SYNC] {conversion_stats['file_paths']} SCons-Pfad-Objekte konvertiert")
    print(f"   [SYNC] {conversion_stats['clvar_converted']} CLVar-Objekte konvertiert")
    print(f"   [OK] String-Pfade blieben unverändert")
    print(f"   [STATS] LDF-Variablen: {len(ldf_variables)} Kategorien")
    print(f"   [SYNC] Rekursive lib-Sicherung: Aktiviert")
    
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
            f.write('PlatformIO LDF SCons Variables Export - Vollständige Compile-Variablen-Wiederherstellung\n')
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
            
            # Cache-Pfad-Funktion
            f.write('def get_cache_file_path():\n')
            f.write('    """Generiert Pfad zur LDF-Cache-Datei für das aktuelle Environment"""\n')
            f.write(f'    return "{cache_file}"\n\n')
            
            # VOLLSTÄNDIGE COMPILE-VAR-WIEDERHERSTELLUNG
            f.write('def restore_environment(target_env):\n')
            f.write('    """Vollständige Wiederherstellung aller compile-relevanten SCons-Variablen"""\n')
            f.write('    import os\n')
            f.write('    \n')
            f.write('    # ALLE compile-relevanten Variablen\n')
            f.write('    COMPILE_VARS = [\n')
            f.write('        "CPPPATH",      # Include-Pfade (KRITISCH)\n')
            f.write('        "CPPDEFINES",   # Präprozessor-Defines\n')
            f.write('        "LIBS",         # Libraries\n')
            f.write('        "LIBPATH",      # Library-Pfade\n')
            f.write('        "ASFLAGS",      # Assembler Flags\n')
            f.write('        "ASPPFLAGS",    # Assembler Präprozessor Flags\n')
            f.write('        "CFLAGS",       # C Compiler Flags\n')
            f.write('        "CXXFLAGS",     # C++ Compiler Flags\n')
            f.write('        "CCFLAGS",      # C/C++ Common Compiler Flags\n')
            f.write('        "LINKFLAGS"     # Linker Flags\n')
            f.write('    ]\n')
            f.write('    \n')
            f.write('    print("[TARGET] VOLLSTÄNDIGE COMPILE-VAR-WIEDERHERSTELLUNG:")\n')
            f.write('    restored_vars = 0\n')
            f.write('    failed_vars = 0\n')
            f.write('    skipped_vars = 0\n')
            f.write('    \n')
            f.write('    # Wiederherstellung aller compile-relevanten Variablen\n')
            f.write('    for var_name in COMPILE_VARS:\n')
            f.write('        if var_name in SCONS_VARS:\n')
            f.write('            try:\n')
            f.write('                cached_value = SCONS_VARS[var_name]\n')
            f.write('                current_value = target_env.get(var_name, [])\n')
            f.write('                \n')
            f.write('                # Spezielle Behandlung für CPPPATH\n')
            f.write('                if var_name == "CPPPATH":\n')
            f.write('                    # Verwende vollständige CPPPATH aus LDF-Analyse\n')
            f.write('                    complete_cpppath = LDF_VARS.get("LIB_VARS", {}).get("CPPPATH_COMPLETE", [])\n')
            f.write('                    if complete_cpppath:\n')
            f.write('                        # Filtere nur existierende Pfade\n')
            f.write('                        valid_paths = [p for p in complete_cpppath if isinstance(p, str) and os.path.exists(p)]\n')
            f.write('                        target_env.Replace(CPPPATH=valid_paths)\n')
            f.write('                        \n')
            f.write('                        # Debug für KNX\n')
            f.write('                        knx_paths = [p for p in valid_paths if "knx" in p.lower()]\n')
            f.write('                        print(f"   [OK] CPPPATH: {len(valid_paths)} Pfade, {len(knx_paths)} KNX-Pfade")\n')
            f.write('                        restored_vars += 1\n')
            f.write('                    else:\n')
            f.write('                        # Fallback auf gecachte CPPPATH\n')
            f.write('                        if isinstance(cached_value, list) and cached_value:\n')
            f.write('                            valid_cached = [p for p in cached_value if isinstance(p, str) and os.path.exists(p)]\n')
            f.write('                            target_env.Replace(CPPPATH=valid_cached)\n')
            f.write('                            print(f"   [OK] CPPPATH (Fallback): {len(valid_cached)} Pfade")\n')
            f.write('                            restored_vars += 1\n')
            f.write('                        else:\n')
            f.write('                            print(f"   [FEHLER] CPPPATH: Keine gültigen Pfade verfügbar")\n')
            f.write('                            failed_vars += 1\n')
            f.write('                \n')
            f.write('                # Spezielle Behandlung für LIBPATH (Pfad-Validierung)\n')
            f.write('                elif var_name == "LIBPATH":\n')
            f.write('                    if isinstance(cached_value, list):\n')
            f.write('                        valid_libpaths = [p for p in cached_value if isinstance(p, str) and os.path.exists(p)]\n')
            f.write('                        target_env.Replace(LIBPATH=valid_libpaths)\n')
            f.write('                        print(f"   [OK] LIBPATH: {len(valid_libpaths)} gültige Pfade")\n')
            f.write('                        restored_vars += 1\n')
            f.write('                    else:\n')
            f.write('                        target_env.Replace(LIBPATH=cached_value)\n')
            f.write('                        print(f"   [OK] LIBPATH: {type(cached_value).__name__}")\n')
            f.write('                        restored_vars += 1\n')
            f.write('                \n')
            f.write('                # Alle anderen Variablen direkt setzen\n')
            f.write('                else:\n')
            f.write('                    target_env.Replace(**{var_name: cached_value})\n')
            f.write('                    \n')
            f.write('                    if isinstance(cached_value, list):\n')
            f.write('                        print(f"   [OK] {var_name}: {len(cached_value)} Einträge")\n')
            f.write('                    elif isinstance(cached_value, str):\n')
            f.write('                        print(f"   [OK] {var_name}: {len(cached_value)} Zeichen")\n')
            f.write('                    else:\n')
            f.write('                        print(f"   [OK] {var_name}: {type(cached_value).__name__}")\n')
            f.write('                    restored_vars += 1\n')
            f.write('                \n')
            f.write('            except Exception as e:\n')
            f.write('                print(f"   [FEHLER] {var_name}: Fehler - {e}")\n')
            f.write('                failed_vars += 1\n')
            f.write('        else:\n')
            f.write('            print(f"   [WARNUNG] {var_name}: Nicht im Cache")\n')
            f.write('            skipped_vars += 1\n')
            f.write('    \n')
            f.write('    # Erweiterte Validierung\n')
            f.write('    print("\\n[INFO] VALIDIERUNG:")\n')
            f.write('    \n')
            f.write('    # 1. CPPPATH-Validierung\n')
            f.write('    final_cpppath = target_env.get("CPPPATH", [])\n')
            f.write('    knx_header_found = False\n')
            f.write('    knx_paths_count = 0\n')
            f.write('    \n')
            f.write('    for cpppath in final_cpppath:\n')
            f.write('        if isinstance(cpppath, str):\n')
            f.write('            if "knx" in cpppath.lower():\n')
            f.write('                knx_paths_count += 1\n')
            f.write('            \n')
            f.write('            knx_header = os.path.join(cpppath, "esp-knx-ip.h")\n')
            f.write('            if os.path.exists(knx_header):\n')
            f.write('                print(f"   [TARGET] esp-knx-ip.h: {knx_header}")\n')
            f.write('                knx_header_found = True\n')
            f.write('    \n')
            f.write('    print(f"   CPPPATH: {len(final_cpppath)} Pfade, {knx_paths_count} KNX-Pfade")\n')
            f.write('    \n')
            f.write('    # 2. LIBS-Validierung\n')
            f.write('    final_libs = target_env.get("LIBS", [])\n')
            f.write('    if isinstance(final_libs, list):\n')
            f.write('        print(f"   LIBS: {len(final_libs)} Libraries")\n')
            f.write('    else:\n')
            f.write('        print(f"   LIBS: {type(final_libs).__name__}")\n')
            f.write('    \n')
            f.write('    # Erfolgs-Bewertung\n')
            f.write('    min_required_vars = 7  # Mindestens 7 der 10 Variablen sollten wiederhergestellt werden\n')
            f.write('    success = (restored_vars >= min_required_vars and failed_vars <= 2)\n')
            f.write('    \n')
            f.write('    print(f"\\n[STATS] ZUSAMMENFASSUNG:")\n')
            f.write('    print(f"   Wiederhergestellt: {restored_vars}/{len(COMPILE_VARS)} Variablen")\n')
            f.write('    print(f"   Fehlgeschlagen: {failed_vars}")\n')
            f.write('    print(f"   Übersprungen: {skipped_vars}")\n')
            f.write('    ok_text = "[OK]" if knx_header_found else "[FEHLER]"\n')
            f.write('    print(f"   KNX-Header gefunden: {ok_text}")\n')
            f.write('    status_text = "[OK] Erfolgreich" if success else "[FEHLER] Fehlgeschlagen"\n')
            f.write('    print(f"   Status: {status_text}")\n')
            f.write('    \n')
            f.write('    return success\n')
            f.write('\n')
            
            # Convenience-Funktionen
            f.write('def get_complete_cpppath():\n')
            f.write('    """Gibt vollständige CPPPATH-Einträge zurück"""\n')
            f.write('    return LDF_VARS.get("LIB_VARS", {}).get("CPPPATH_COMPLETE", [])\n\n')
        
        # Atomarer Austausch
        if os.path.exists(cache_file):
            backup_file = cache_file + ".backup"
            shutil.move(cache_file, backup_file)
        
        shutil.move(temp_file, cache_file)
        print(f"[OK] Vollständige SCons-Konfiguration gespeichert: {os.path.basename(cache_file)}")
        
        return True
        
    except Exception as e:
        print(f"[FEHLER] Fehler beim Speichern der SCons-Konfiguration: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def show_cache_statistics(complete_data):
    """Zeigt Cache-Statistiken an"""
    scons_vars = complete_data.get('SCONS_VARS', {})
    ldf_vars = complete_data.get('LDF_VARS', {})
    
    print(f"\n[STATS] CACHE-STATISTIKEN:")
    print(f"   SCons-Variablen: {len(scons_vars)}")
    print(f"   LDF-Kategorien: {len(ldf_vars)}")
    
    # CPPPATH-Statistik
    complete_cpppath = ldf_vars.get('LIB_VARS', {}).get('CPPPATH_COMPLETE', [])
    knx_paths = [p for p in complete_cpppath if 'knx' in p.lower()]
    print(f"   CPPPATH-Einträge: {len(complete_cpppath)}")
    print(f"   KNX-Pfade: {len(knx_paths)}")
    
    if knx_paths:
        print(f"   [TARGET] KNX-Pfade gefunden:")
        for knx_path in knx_paths[:3]:  # Zeige erste 3
            print(f"      {knx_path}")
        if len(knx_paths) > 3:
            print(f"      ... und {len(knx_paths) - 3} weitere")
    
    # Compile-Variablen-Statistik
    compile_vars = ['CPPPATH', 'CPPDEFINES', 'LIBS', 'LIBPATH', 'ASFLAGS', 'ASPPFLAGS', 'CFLAGS', 'CXXFLAGS', 'CCFLAGS', 'LINKFLAGS']
    cached_compile_vars = sum(1 for var in compile_vars if var in scons_vars)
    print(f"   Compile-Variablen gecacht: {cached_compile_vars}/{len(compile_vars)}")

def load_and_restore_cache():
    """Lädt und wendet den LDF-Cache an"""
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        print(f"[WARNUNG] Kein LDF-Cache gefunden: {os.path.basename(cache_file)}")
        return False
    
    try:
        print(f"\n[SYNC] LADE LDF-CACHE:")
        print(f"   Cache-Datei: {os.path.basename(cache_file)}")
        
        # Lade Cache-Daten
        cache_globals = {}
        with open(cache_file, 'r', encoding='utf-8') as f:
            exec(f.read(), cache_globals)
        
        # Prüfe ob restore_environment verfügbar ist
        if 'restore_environment' not in cache_globals:
            print(f"[FEHLER] restore_environment Funktion nicht gefunden")
            return False
        
        # Führe Wiederherstellung aus
        restore_func = cache_globals['restore_environment']
        success = restore_func(env)
        
        if success:
            print(f"[OK] LDF-Cache erfolgreich angewendet")
        else:
            print(f"[FEHLER] LDF-Cache-Anwendung fehlgeschlagen")
        
        return success
        
    except Exception as e:
        print(f"[FEHLER] Fehler beim Laden des LDF-Cache: {e}")
        return False

def cleanup_old_backups():
    """Bereinigt alte Backup-Dateien"""
    try:
        project_dir = env.get("PROJECT_DIR")
        if not project_dir:
            return
        
        # Suche nach .ldf_backup Dateien
        backup_files = glob.glob(os.path.join(project_dir, "*.ldf_backup"))
        
        if backup_files:
            print(f"\n[CLEAN] BACKUP-BEREINIGUNG:")
            for backup_file in backup_files:
                try:
                    # Prüfe Alter der Backup-Datei
                    backup_age = time.time() - os.path.getmtime(backup_file)
                    if backup_age > 7 * 24 * 3600:  # Älter als 7 Tage
                        os.remove(backup_file)
                        print(f"   [OK] Altes Backup entfernt: {os.path.basename(backup_file)}")
                except:
                    pass
    except:
        pass

def main():
    """Hauptfunktion des LDF-Cache-Systems mit automatischer Trigger-Logik"""
    print(f"\n[START] TASMOTA LDF CACHE SYSTEM - AUTOMATISCHE LDF-VERARBEITUNG")
    print(f"Environment: {env.get('PIOENV')}")
    print(f"Projekt: {env.get('PROJECT_DIR')}")
    
    env_name = env.get("PIOENV")
    if not env_name:
        print("[FEHLER] Kein PIOENV gefunden")
        return
    
    # 1. Prüfe ob Cache erstellt werden sollte
    if should_create_ldf_cache():
        print(f"\n[LDF] STARTE LDF-CACHE-ERSTELLUNG:")
        
        # 2. Prüfe ob LDF-Verarbeitung nötig ist
        if should_trigger_ldf_processing():
            # LDF-Management für vollständige Erfassung
            ldf_managed = manage_ldf_mode()
            
            try:
                # Cache mit LDF-Verarbeitung erstellen
                complete_data = capture_complete_scons_environment()
                cache_created = freeze_complete_scons_configuration(complete_data)
                
                if cache_created:
                    print(f"[OK] LDF-Cache erfolgreich erstellt")
                    
                    # Zeige Statistiken
                    show_cache_statistics(complete_data)
                else:
                    print(f"[FEHLER] Cache-Erstellung fehlgeschlagen")
                    
            finally:
                # LDF-Modus immer wiederherstellen
                if ldf_managed:
                    restore_ldf_mode()
        else:
            # Einfacher Cache ohne LDF-Verarbeitung
            print(f"[INFO] Erstelle einfachen Cache ohne LDF-Verarbeitung")
            complete_data = capture_complete_scons_environment()
            freeze_complete_scons_configuration(complete_data)
    else:
        print(f"[INFO] Cache-Erstellung übersprungen")

# Hauptausführung
if __name__ == "__main__":
    try:
        # Bereinige alte Backups
        cleanup_old_backups()
        
        # Prüfe ob Cache bereits existiert
        cache_file = get_cache_file_path()
        cache_exists = os.path.exists(cache_file)
        
        if cache_exists:
            print(f"[INFO] Existierender Cache gefunden: {os.path.basename(cache_file)}")
            
            # Versuche Cache-Wiederherstellung
            if load_and_restore_cache():
                print(f"[TARGET] Cache-Wiederherstellung erfolgreich - Build kann fortgesetzt werden")
            else:
                print(f"[WARNUNG] Cache-Wiederherstellung fehlgeschlagen - Erstelle neuen Cache")
                main()
        else:
            print(f"[INFO] Kein Cache gefunden - Erstelle neuen Cache")
            main()
            
    except KeyboardInterrupt:
        print(f"\n[WARNUNG] Abbruch durch Benutzer")
    except Exception as e:
        print(f"\n[FEHLER] Unerwarteter Fehler: {e}")
        import traceback
        traceback.print_exc()

# Script-Ende-Marker
print(f"\n[ENDE] LDF-Cache-Script beendet - Environment: {env.get('PIOENV')}")
