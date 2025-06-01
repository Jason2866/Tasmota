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

def debug_all_scons_variables():
    """Zeigt ALLE SCons-Variablen für LDF-Analyse"""
    print(f"\n🔍 VOLLSTÄNDIGE SCons-Environment-Analyse:")
    
    env_dict = env.Dictionary()
    
    # Gruppiere Variablen nach Typ
    path_vars = {}
    lib_vars = {}
    build_vars = {}
    other_vars = {}
    
    for key, value in env_dict.items():
        if 'PATH' in key.upper() or 'DIR' in key.upper():
            path_vars[key] = value
        elif 'LIB' in key.upper():
            lib_vars[key] = value  
        elif any(x in key.upper() for x in ['BUILD', 'FLAG', 'CC', 'CXX', 'LINK']):
            build_vars[key] = value
        else:
            other_vars[key] = value
    
    print(f"📁 Pfad-Variablen ({len(path_vars)}):")
    for key, value in sorted(path_vars.items()):
        if isinstance(value, list):
            print(f"   {key}: {len(value)} Einträge")
            if key == 'CPPPATH' and len(value) <= 20:  # Zeige CPPPATH Details
                for i, path in enumerate(value):
                    source = determine_path_source(path)
                    exists = os.path.exists(str(path))
                    print(f"      {i:2d}: {source:12s} {'✓' if exists else '✗'} {path}")
        else:
            print(f"   {key}: {value}")
    
    print(f"📚 Bibliotheks-Variablen ({len(lib_vars)}):")
    for key, value in sorted(lib_vars.items()):
        if isinstance(value, list):
            print(f"   {key}: {len(value)} Einträge")
            if len(value) <= 10:  # Zeige Details für kleine Listen
                for item in value:
                    print(f"      - {item}")
        else:
            print(f"   {key}: {value}")
    
    print(f"🔨 Build-Variablen ({len(build_vars)}):")
    for key, value in sorted(build_vars.items()):
        if isinstance(value, list):
            print(f"   {key}: {len(value)} Einträge")
            # Zeige Include-Flags in Build-Variablen
            include_flags = [f for f in value if str(f).startswith('-I')]
            if include_flags:
                print(f"      Include-Flags: {len(include_flags)}")
                for flag in include_flags[:5]:  # Nur erste 5 zeigen
                    print(f"         {flag}")
        else:
            print(f"   {key}: {str(value)[:100]}{'...' if len(str(value)) > 100 else ''}")
    
    print(f"📦 Andere Variablen ({len(other_vars)}):")
    interesting_vars = ['PIOENV', 'BOARD', 'PLATFORM', 'PIOFRAMEWORK']
    for key in interesting_vars:
        if key in other_vars:
            print(f"   {key}: {other_vars[key]}")

def debug_ldf_resolution():
    """Macht LDF-Entscheidungen transparent"""
    
    print("\n🔍 LDF-Pfad-Resolution-Analyse:")
    
    # Zeige alle Include-Pfade mit Quelle
    cpppath = env.get('CPPPATH', [])
    print(f"📁 CPPPATH ({len(cpppath)} Pfade):")
    
    source_stats = {}
    for i, path in enumerate(cpppath):
        source = determine_path_source(path)
        exists = os.path.exists(str(path))
        
        # Statistiken sammeln
        if source not in source_stats:
            source_stats[source] = {'count': 0, 'missing': 0}
        source_stats[source]['count'] += 1
        if not exists:
            source_stats[source]['missing'] += 1
        
        print(f"  {i:2d}: {source:12s} {'✓' if exists else '✗'} {path}")
    
    print(f"\n📊 Pfad-Quellen-Statistik:")
    for source, stats in sorted(source_stats.items()):
        missing_info = f" ({stats['missing']} fehlen)" if stats['missing'] > 0 else ""
        print(f"   {source:12s}: {stats['count']} Pfade{missing_info}")
    
    # Zeige Bibliotheks-Informationen
    libs = env.get('LIBS', [])
    if libs:
        print(f"\n📚 Verlinkte Bibliotheken ({len(libs)}):")
        for lib in libs:
            print(f"   - {lib}")
    
    # Zeige PIOBUILDFILES
    piobuildfiles = env.get('PIOBUILDFILES', [])
    if piobuildfiles:
        print(f"\n🔨 Build-Dateien ({len(piobuildfiles)} Listen):")
        total_files = 0
        for i, file_list in enumerate(piobuildfiles):
            if isinstance(file_list, list):
                total_files += len(file_list)
                print(f"   Liste {i}: {len(file_list)} Dateien")
        print(f"   Gesamt: {total_files} Dateien")

def capture_complete_ldf_results():
    """Erfasst ALLE LDF-Ergebnisse aus dem SCons Environment"""
    
    # 1. Include-Pfade
    cpppath = env.get('CPPPATH', [])
    
    # 2. Bibliotheks-Pfade und -Namen
    libpath = env.get('LIBPATH', [])
    libs = env.get('LIBS', [])
    
    # 3. Source-Dateien die gebaut werden müssen
    piobuildfiles = env.get('PIOBUILDFILES', [])
    
    # 4. Preprocessor-Defines
    cppdefines = env.get('CPPDEFINES', [])
    
    # 5. Build-Flags
    build_flags = env.get('BUILD_FLAGS', [])
    ccflags = env.get('CCFLAGS', [])
    cxxflags = env.get('CXXFLAGS', [])
    linkflags = env.get('LINKFLAGS', [])
    
    # 6. LDF-spezifische Variablen (WICHTIG!)
    lib_deps = env.get('LIB_DEPS', [])
    lib_extra_dirs = env.get('LIB_EXTRA_DIRS', [])
    lib_builtin = env.get('LIB_BUILTIN', [])
    
    # 7. Framework-spezifische Variablen
    framework_dir = env.get('FRAMEWORK_DIR', '')
    platform_packages = env.get('PLATFORM_PACKAGES_DIR', '')
    
    print(f"\n📊 Vollständige LDF-Erfassung:")
    print(f"  CPPPATH: {len(cpppath)} Pfade")
    print(f"  LIBPATH: {len(libpath)} Bibliotheks-Pfade")
    print(f"  LIBS: {len(libs)} Bibliotheken")
    print(f"  PIOBUILDFILES: {len(piobuildfiles)} Source-Listen")
    print(f"  CPPDEFINES: {len(cppdefines)} Defines")
    print(f"  LIB_DEPS: {len(lib_deps)} Dependencies")
    print(f"  LIB_EXTRA_DIRS: {len(lib_extra_dirs)} Extra-Verzeichnisse")
    
    return {
        'cpppath': cpppath,
        'libpath': libpath, 
        'libs': libs,
        'piobuildfiles': piobuildfiles,
        'cppdefines': cppdefines,
        'lib_deps': lib_deps,
        'lib_extra_dirs': lib_extra_dirs,
        'framework_dir': framework_dir,
        'platform_packages': platform_packages
    }

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

def count_conversions(value, stats, depth=0):
    """Zählt verschiedene Arten von SCons-Objekt-Konvertierungen"""
    
    if depth > 5:  # Schutz vor zu tiefer Rekursion
        return
    
    if hasattr(value, 'abspath') or hasattr(value, 'path'):
        stats["file_paths"] += 1
    elif hasattr(value, '__class__') and 'SCons.Builder' in str(value.__class__):
        stats["builders"] += 1
    elif callable(value):
        stats["functions"] += 1
    elif hasattr(value, '__class__') and 'SCons' in str(value.__class__):
        stats["other"] += 1
    elif isinstance(value, (list, tuple)):
        for item in value:
            count_conversions(item, stats, depth + 1)
    elif isinstance(value, dict):
        for dict_value in value.values():
            count_conversions(dict_value, stats, depth + 1)

def freeze_exact_scons_configuration_local(local_dict):
    """Speichert lokales Environment mit selektiver SCons-Objekt-Pfad-Konvertierung"""
    cache_file = get_cache_file_path()
    temp_file = cache_file + ".tmp"
    
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write("# SCons Environment Snapshot - POST-COMPILE ACTION\n")
            f.write("# SCons objects → paths, String paths unchanged\n")
            f.write("# Auto-generated - do not edit manually\n")
            f.write(f"# Generated: {time.ctime()}\n")
            f.write(f"# Environment: {env.get('PIOENV')}\n")
            f.write(f"# Captured after compile, before linking\n\n")
            
            f.write("def restore_environment(target_env):\n")
            f.write('    """Stellt das post-compile erfasste SCons-Environment wieder her"""\n')
            f.write('    restored_count = 0\n')
            f.write('    conversion_stats = {"file_paths": 0, "builders": 0, "functions": 0, "other": 0}\n')
            f.write('    \n')
            
            var_count = 0
            conversion_stats = {"file_paths": 0, "builders": 0, "functions": 0, "other": 0}
            
            for key, value in sorted(local_dict.items()):
                try:
                    # Selektive Konvertierung: Nur SCons-Objekte, String-Pfade bleiben unverändert
                    converted_value = convert_scons_objects_selective(value, key)
                    
                    # Statistiken sammeln
                    count_conversions(value, conversion_stats)
                    
                    f.write(f'    # {key} (Original: {type(value).__name__})\n')
                    f.write(f'    try:\n')
                    f.write(f'        target_env[{repr(key)}] = {repr(converted_value)}\n')
                    f.write(f'        restored_count += 1\n')
                    f.write(f'    except Exception as e:\n')
                    f.write(f'        print(f"⚠ Fehler bei {key}: {{e}}")\n')
                    f.write(f'        pass\n')
                    f.write(f'    \n')
                    var_count += 1
                    
                except Exception as e:
                    f.write(f'    # {key}: KONVERTIERUNGSFEHLER - {e}\n')
                    f.write(f'    conversion_stats["other"] += 1\n')
                    continue
            
            # Konvertierungs-Statistiken
            f.write('    # === KONVERTIERUNGS-STATISTIKEN ===\n')
            f.write(f'    conversion_stats["file_paths"] = {conversion_stats["file_paths"]}\n')
            f.write(f'    conversion_stats["builders"] = {conversion_stats["builders"]}\n')
            f.write(f'    conversion_stats["functions"] = {conversion_stats["functions"]}\n')
            f.write(f'    conversion_stats["other"] = {conversion_stats["other"]}\n')
            f.write('    \n')
            
            f.write('    print(f"✓ {{restored_count}} SCons-Variablen wiederhergestellt (Post-Compile)")\n')
            f.write('    print(f"✓ {{conversion_stats[\'file_paths\']}} SCons-Objekt-Pfade konvertiert")\n')
            f.write('    print(f"✓ {{conversion_stats[\'builders\']}} Builder-Objekte konvertiert")\n')
            f.write('    print(f"✓ {{conversion_stats[\'functions\']}} Funktionen konvertiert")\n')
            f.write('    print(f"✓ {{conversion_stats[\'other\']}} andere Objekte konvertiert")\n')
            f.write('    print("✓ String-Pfade blieben unverändert")\n')
            f.write('    return restored_count > 50\n')
            f.write('\n')
            f.write('# Metadata\n')
            f.write(f'CONFIG_HASH = {repr(calculate_config_hash())}\n')
            f.write(f'ENV_NAME = {repr(env.get("PIOENV"))}\n')
            f.write(f'VARIABLE_COUNT = {var_count}\n')
            f.write(f'CONVERTED_FILE_PATHS = {conversion_stats["file_paths"]}\n')
            f.write(f'CONVERTED_BUILDERS = {conversion_stats["builders"]}\n')
            f.write(f'CONVERTED_FUNCTIONS = {conversion_stats["functions"]}\n')
            f.write(f'CONVERTED_OTHER = {conversion_stats["other"]}\n')
        
        # Atomarer Move
        shutil.move(temp_file, cache_file)
        
        file_size = os.path.getsize(cache_file)
        total_conversions = sum(conversion_stats.values())
        
        print(f"✓ Post-Compile Environment gespeichert:")
        print(f"   📁 {os.path.basename(cache_file)} ({file_size} Bytes)")
        print(f"   📊 {var_count} SCons-Variablen")
        print(f"   🔄 {total_conversions} SCons-Objekte konvertiert:")
        print(f"      📄 {conversion_stats['file_paths']} SCons-Objekt-Pfade")
        print(f"      🔨 {conversion_stats['builders']} Builder-Objekte")
        print(f"      ⚙️  {conversion_stats['functions']} Funktionen")
        print(f"      📦 {conversion_stats['other']} andere Objekte")
        print(f"   ✅ String-Pfade blieben unverändert")
        
        return True
        
    except Exception as e:
        print(f"❌ Post-Compile Environment-Konvertierung fehlgeschlagen: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def post_compile_action(target, source, env):
    """SCons Action: Erfasst Environment nach Compile, vor Linking"""
    global _backup_created
    
    if _backup_created:
        print("✓ Environment bereits erfasst - überspringe Post-Compile Action")
        return None
    
    try:
        print(f"\n🎯 POST-COMPILE ACTION: Erfasse finales SCons-Environment")
        print(f"   Target: {[str(t) for t in target]}")
        print(f"   Source: {len(source)} Dateien")
        
        # Analysiere aktuellen Environment-Zustand
        cpppath = env.get('CPPPATH', [])
        libs = env.get('LIBS', [])
        piobuildfiles = env.get('PIOBUILDFILES', [])
        
        print(f"   📊 Environment-Status:")
        print(f"      CPPPATH: {len(cpppath)} Pfade")
        print(f"      LIBS: {len(libs)} Bibliotheken")
        print(f"      PIOBUILDFILES: {len(piobuildfiles)} Listen")
        
        # Prüfe ob realistische Werte vorhanden sind
        realistic_values = (
            len(cpppath) > 50 and  # Mindestens 50 Include-Pfade
            len(libs) > 5 and len(libs) < 50 and  # Realistische LIBS-Anzahl
            len(piobuildfiles) > 0  # Build-Dateien vorhanden
        )
        
        if realistic_values:
            print(f"✅ Realistische Environment-Werte - erfasse vollständiges Environment")
            
            # Vollständige Debug-Ausgabe
            debug_all_scons_variables()
            debug_ldf_resolution()
            capture_complete_ldf_results()
            
            # Environment erfassen
            complete_env = env.Clone()
            complete_dict = complete_env.Dictionary()
            
            print(f"📊 SCons Environment: {len(complete_dict)} Variablen erfasst")
            
            if freeze_exact_scons_configuration_local(complete_dict):
                env_name = env.get("PIOENV")
                if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                    print(f"✓ lib_ldf_mode = off für Lauf 2 gesetzt")
                    print(f"🚀 POST-COMPILE SCons-Environment erfasst!")
                    _backup_created = True
                else:
                    print(f"⚠ lib_ldf_mode konnte nicht gesetzt werden")
            else:
                print(f"❌ Environment-Backup fehlgeschlagen")
        else:
            print(f"⚠ Unrealistische Environment-Werte - überspringe Erfassung")
            print(f"   CPPPATH: {len(cpppath)} (erwartet >50)")
            print(f"   LIBS: {len(libs)} (erwartet 5-50)")
            print(f"   PIOBUILDFILES: {len(piobuildfiles)} (erwartet >0)")
    
    except Exception as e:
        print(f"❌ Post-Compile Action Fehler: {e}")
    
    return None

def restore_exact_scons_configuration():
    """Lädt Environment aus Python-Datei"""
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
            print("⚠ Konfiguration geändert - Python-Cache ungültig")
            return False
        
        # Environment wiederherstellen
        success = env_module.restore_environment(env)
        
        if success:
            var_count = getattr(env_module, 'VARIABLE_COUNT', 0)
            converted_file_paths = getattr(env_module, 'CONVERTED_FILE_PATHS', 0)
            converted_builders = getattr(env_module, 'CONVERTED_BUILDERS', 0)
            converted_functions = getattr(env_module, 'CONVERTED_FUNCTIONS', 0)
            converted_other = getattr(env_module, 'CONVERTED_OTHER', 0)
            
            print(f"✓ Post-Compile Environment wiederhergestellt:")
            print(f"   📊 {var_count} Variablen")
            print(f"   📄 {converted_file_paths} SCons-Objekt-Pfade")
            print(f"   🔨 {converted_builders} Builder-Objekte")
            print(f"   ⚙️  {converted_functions} Funktionen")
            print(f"   📦 {converted_other} andere Objekte")
            print(f"   ✅ String-Pfade unverändert")
            
            # Debug-Ausgabe nach Wiederherstellung
            print(f"\n🔍 Environment nach Post-Compile Cache-Wiederherstellung:")
            debug_ldf_resolution()
        
        return success
        
    except Exception as e:
        print(f"❌ Python-Datei-Wiederherstellung fehlgeschlagen: {e}")
        return False

def early_cache_check_and_restore():
    """Prüft Cache und stellt SCons-Environment wieder her"""
    print(f"🔍 Cache-Prüfung (Post-Compile Environment)...")
    
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        print(f"📝 Kein Post-Compile Cache - LDF wird normal ausgeführt")
        return False
    
    current_ldf_mode = get_current_ldf_mode(env.get("PIOENV"))
    
    if current_ldf_mode != 'off':
        print(f"🔄 LDF noch aktiv - Post-Compile Cache wird nach Build erstellt")
        return False
    
    print(f"⚡ Post-Compile Cache verfügbar - stelle Environment wieder her")
    
    success = restore_exact_scons_configuration()
    return success

def count_scons_objects_in_value(value, depth=0):
    """Zählt verbleibende SCons-Objekte in einem Wert"""
    
    if depth > 5:
        return 0
    
    count = 0
    
    if hasattr(value, '__class__') and 'SCons' in str(value.__class__):
        count += 1
    elif isinstance(value, (list, tuple)):
        for item in value:
            count += count_scons_objects_in_value(item, depth + 1)
    elif isinstance(value, dict):
        for dict_value in value.values():
            count += count_scons_objects_in_value(dict_value, depth + 1)
    
    return count

def verify_frozen_restoration():
    """Verifikation mit Fokus auf Post-Compile Environment"""
    print(f"\n🔍 SCons-Environment-Verifikation (Post-Compile)...")
    
    critical_scons_vars = [
        "CPPPATH", "CPPDEFINES", "BUILD_FLAGS", "LIBS", 
        "CCFLAGS", "CXXFLAGS", "LINKFLAGS", "PIOBUILDFILES"
    ]
    
    all_ok = True
    scons_objects_found = 0
    string_paths_preserved = 0
    converted_paths = 0
    
    for var in critical_scons_vars:
        if var in env and env[var]:
            value = env[var]
            
            # Prüfe ob noch SCons-Objekte vorhanden sind
            scons_obj_count = count_scons_objects_in_value(value)
            scons_objects_found += scons_obj_count
            
            if var == "CPPPATH":
                paths = value
                print(f"   ✅ {var}: {len(paths)} Include-Pfade")
                
                # Prüfe lib/default/headers
                project_dir = env.get("PROJECT_DIR")
                lib_default = os.path.join(project_dir, "lib", "default", "headers")
                found = any(lib_default in str(path) for path in paths)
                
                if found:
                    print(f"      ✅ lib/default/headers: VERFÜGBAR")
                else:
                    print(f"      ❌ lib/default/headers: FEHLT")
                    all_ok = False
                
                # Zähle String-Pfade vs. konvertierte Pfade
                for path in paths:
                    if isinstance(path, str):
                        if path.startswith('/') or path.startswith('./'):
                            string_paths_preserved += 1
                        else:
                            converted_paths += 1
                
                print(f"      ✅ String-Pfade erhalten: {string_paths_preserved}")
                print(f"      🔄 Konvertierte Pfade: {converted_paths}")
                
            elif var == "PIOBUILDFILES":
                # Prüfe ob SCons-File-Objekte zu Pfaden konvertiert wurden
                if isinstance(value, list):
                    valid_paths = 0
                    for item_list in value:
                        if isinstance(item_list, list):
                            for item in item_list:
                                if isinstance(item, str) and (item.startswith('/') or os.path.exists(item)):
                                    valid_paths += 1
                    print(f"   ✅ {var}: {valid_paths} gültige Dateipfade")
                else:
                    print(f"   ✅ {var}: Vorhanden")
                    
            elif hasattr(value, '__len__') and not isinstance(value, str):
                print(f"   ✅ {var}: {len(value)} Einträge")
                if scons_obj_count > 0:
                    print(f"      ⚠️  {scons_obj_count} SCons-Objekte noch vorhanden")
            else:
                print(f"   ✅ {var}: Vorhanden")
        else:
            print(f"   ❌ {var}: Fehlt")
            all_ok = False
    
    scons_dict_size = len(env.Dictionary())
    print(f"   📊 SCons Dictionary: {scons_dict_size} Variablen")
    print(f"   🔄 Verbleibende SCons-Objekte: {scons_objects_found}")
    print(f"   ✅ String-Pfade erhalten: {string_paths_preserved}")
    print(f"   🔄 SCons-Objekte zu Pfaden: {converted_paths}")
    
    if all_ok and scons_objects_found == 0:
        print(f"✅ Post-Compile SCons-Environment vollständig wiederhergestellt")
    elif all_ok:
        print(f"⚠️  Post-Compile SCons-Environment wiederhergestellt, aber {scons_objects_found} Objekte nicht konvertiert")
    else:
        print(f"❌ Post-Compile SCons-Environment UNVOLLSTÄNDIG")
    
    return all_ok

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
# HAUPTLOGIK - POST-COMPILE SCONS-ENVIRONMENT
# =============================================================================

print(f"\n🎯 Post-Compile SCons-Environment-Backup für: {env.get('PIOENV')}")

# Cache-Prüfung und SCons-Environment-Wiederherstellung
cache_restored = early_cache_check_and_restore()

if cache_restored:
    print(f"🚀 Build mit Post-Compile Environment-Cache - LDF übersprungen!")
    
    if not verify_frozen_restoration():
        print(f"❌ KRITISCHER FEHLER: Post-Compile SCons-Environment unvollständig!")
        print(f"💡 Löschen Sie '.pio/ldf_cache/' und starten Sie neu")

else:
    print(f"📝 Normaler LDF-Durchlauf - erfasse Environment nach Compile-Phase...")
    
    # SCons Action: Erfasse Environment nach Compile, vor Linking
    # Füge Action zu allen Object-Files hinzu (nach Compile, vor Linking)
    env.AddPostAction("$BUILD_DIR/${PROGNAME}.elf", post_compile_action)
    
    # Alternative: Action für Object-Files
    # env.AddPostAction("*.o", post_compile_action)
    
    print(f"✅ Post-Compile Action registriert für: $BUILD_DIR/${{PROGNAME}}.elf")

print(f"🏁 Post-Compile SCons-Environment-Backup initialisiert")
print(f"💡 Reset: rm -rf .pio/ldf_cache/\n")
