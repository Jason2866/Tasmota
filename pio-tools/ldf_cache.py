Import("env")
import os
import json
import hashlib
import configparser
import shutil
import glob

def get_cache_file_path():
    """Generiert Pfad zur LDF-Cache-Datei für das aktuelle Environment"""
    env_name = env.get("PIOENV")
    project_dir = env.get("PROJECT_DIR")
    cache_dir = os.path.join(project_dir, ".pio", "ldf_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{env_name}_ldf_cache.json")

def find_all_platformio_files():
    """Findet alle platformio*.ini Dateien im Projekt"""
    project_dir = env.get("PROJECT_DIR")
    
    # Suche nach allen platformio*.ini Dateien
    ini_patterns = [
        'platformio.ini',
        'platformio_*.ini'
    ]
    
    ini_files = []
    for pattern in ini_patterns:
        found_files = glob.glob(os.path.join(project_dir, pattern))
        ini_files.extend(found_files)
    
    # Entferne Duplikate und sortiere
    ini_files = list(set(ini_files))
    
    # Sortiere nach Priorität: Basis-Dateien zuerst, Override zuletzt
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
    
    # Finde die Datei, die das Environment definiert
    env_file = find_env_definition_file(env_name)
    
    if not env_file:
        print(f"⚠ Environment {env_name} nicht gefunden - verwende platformio.ini")
        project_dir = env.get("PROJECT_DIR")
        env_file = os.path.join(project_dir, "platformio.ini")
    
    if not os.path.exists(env_file):
        print(f"⚠ Datei nicht gefunden: {env_file}")
        return False
    
    # Erstelle Backup
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
        
        # Schreibe zurück
        with open(env_file, 'w', encoding='utf-8') as f:
            config.write(f, space_around_delimiters=True)
        
        return True
        
    except Exception as e:
        print(f"⚠ Fehler beim Modifizieren von {os.path.basename(env_file)}: {e}")
        return False

def get_current_ldf_mode(env_name):
    """Ermittelt aktuellen LDF-Modus aus allen platformio*.ini Dateien"""
    ini_files = find_all_platformio_files()
    
    # Lade alle Konfigurationen in der richtigen Reihenfolge
    merged_config = configparser.ConfigParser(allow_no_value=True)
    
    for ini_file in ini_files:
        try:
            temp_config = configparser.ConfigParser(allow_no_value=True)
            temp_config.read(ini_file, encoding='utf-8')
            
            # Merge alle Sektionen (spätere Dateien überschreiben frühere)
            for section_name in temp_config.sections():
                if not merged_config.has_section(section_name):
                    merged_config.add_section(section_name)
                
                for option, value in temp_config.items(section_name):
                    merged_config.set(section_name, option, value)
                    
        except Exception as e:
            print(f"⚠ Fehler beim Lesen von {os.path.basename(ini_file)}: {e}")
            continue
    
    # Prüfe spezifisches Environment
    section_name = f"env:{env_name}"
    if merged_config.has_section(section_name):
        if merged_config.has_option(section_name, 'lib_ldf_mode'):
            mode = merged_config.get(section_name, 'lib_ldf_mode')
            return mode
    
    # Fallback: Prüfe [env] Basis-Sektion
    if merged_config.has_section('env'):
        if merged_config.has_option('env', 'lib_ldf_mode'):
            mode = merged_config.get('env', 'lib_ldf_mode')
            return mode
    
    return 'chain'  # PlatformIO Standard

def restore_platformio_ini():
    """Stellt alle ursprünglichen platformio*.ini Dateien wieder her"""
    project_dir = env.get("PROJECT_DIR")
    
    # Finde alle Backup-Dateien
    backup_files = glob.glob(os.path.join(project_dir, "platformio*.ini.ldf_backup"))
    
    restored_count = 0
    for backup_file in backup_files:
        original_file = backup_file.replace('.ldf_backup', '')
        if os.path.exists(backup_file):
            shutil.copy2(backup_file, original_file)
            print(f"✓ {os.path.basename(original_file)} wiederhergestellt")
            restored_count += 1
    
    if restored_count > 0:
        print(f"✓ {restored_count} Dateien wiederhergestellt")
        return True
    return False

def scan_available_libraries():
    """Scannt alle verfügbaren Libraries im lib/ Ordner rekursiv"""
    project_dir = env.get("PROJECT_DIR")
    lib_dir = os.path.join(project_dir, "lib")
    
    available_libs = []
    if os.path.exists(lib_dir):
        for root, dirs, files in os.walk(lib_dir):
            has_code = any(f.endswith(('.h', '.hpp', '.cpp', '.c', '.ino')) for f in files)
            has_config = any(f in files for f in ['library.json', 'library.properties'])
            
            if has_code or has_config:
                rel_path = os.path.relpath(root, lib_dir)
                if rel_path != '.':
                    lib_name = os.path.basename(root)
                    available_libs.append(lib_name)
    
    return sorted(list(set(available_libs)))

def capture_ldf_results():
    """Erfasst die LDF-Ergebnisse nach dem Build"""
    available_libs = scan_available_libraries()
    
    current_ignore = env.get("LIB_IGNORE", [])
    if isinstance(current_ignore, str):
        current_ignore = [current_ignore]
    elif current_ignore is None:
        current_ignore = []
    
    ignored_libs = set(current_ignore)
    used_libs = [lib for lib in available_libs if lib not in ignored_libs]
    
    # Externe Dependencies hinzufügen
    external_deps = env.get("LIB_DEPS", [])
    if external_deps:
        for dep in external_deps:
            if isinstance(dep, str) and not dep.startswith("${"):
                lib_name = dep.split('/')[-1].split('@')[0]
                if lib_name:
                    used_libs.append(lib_name)
    
    used_libs = sorted(list(set(used_libs)))
    unused_libs = sorted(list(ignored_libs))
    
    return {
        "available": available_libs,
        "used": used_libs,
        "unused": unused_libs,
        "external_deps": external_deps if external_deps else []
    }

def get_config_hash():
    """Erstellt Hash aller relevanten Konfigurationsdateien"""
    ini_files = find_all_platformio_files()
    
    config_content = []
    
    for ini_file in ini_files:
        if os.path.exists(ini_file):
            try:
                with open(ini_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    config_content.append(f"{os.path.basename(ini_file)}:{content}")
            except Exception:
                continue
    
    # Zusätzliche Environment-Werte
    config_content.extend([
        str(env.get("BUILD_FLAGS", [])),
        env.get("BOARD", ""),
        env.get("PLATFORM", ""),
        env.get("PIOENV", "")
    ])
    
    config_string = "|".join(config_content)
    return hashlib.md5(config_string.encode()).hexdigest()

def save_ldf_cache(ldf_results):
    """Speichert LDF-Ergebnisse im Cache"""
    cache_file = get_cache_file_path()
    cache_data = {
        "config_hash": get_config_hash(),
        "ldf_results": ldf_results,
        "env_name": env.get("PIOENV")
    }
    
    with open(cache_file, 'w') as f:
        json.dump(cache_data, f, indent=2)
    
    used_count = len(ldf_results["used"])
    unused_count = len(ldf_results["unused"])
    print(f"✓ LDF Cache gespeichert: {used_count} verwendet, {unused_count} ignoriert")

def load_ldf_cache():
    """Lädt LDF-Cache falls vorhanden und gültig"""
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        return None
    
    try:
        with open(cache_file, 'r') as f:
            cache_data = json.load(f)
        
        if cache_data.get("config_hash") == get_config_hash():
            ldf_results = cache_data.get("ldf_results")
            if ldf_results:
                used_count = len(ldf_results.get("used", []))
                unused_count = len(ldf_results.get("unused", []))
                print(f"✓ LDF Cache geladen: {used_count} verwendet, {unused_count} ignoriert")
                return ldf_results
        else:
            print(f"⚠ LDF Cache ungültig - Konfiguration geändert")
            
    except (json.JSONDecodeError, KeyError) as e:
        print(f"⚠ LDF Cache beschädigt: {e}")
    
    return None

def clear_ldf_cache():
    """Löscht den LDF Cache und stellt alle platformio*.ini wieder her"""
    cache_file = get_cache_file_path()
    if os.path.exists(cache_file):
        os.remove(cache_file)
        print(f"✓ LDF Cache gelöscht")
    
    restore_platformio_ini()

# =============================================================================
# HAUPTLOGIK - MIT MULTI-FILE SUPPORT
# =============================================================================

print(f"\n🔍 Tasmota LDF Cache für Environment: {env.get('PIOENV')}")

env_name = env.get("PIOENV")
current_ldf_mode = get_current_ldf_mode(env_name)
print(f"📊 Aktueller LDF-Modus: {current_ldf_mode}")

cached_ldf = load_ldf_cache()

# Prüfe ob Cache GÜLTIG und VOLLSTÄNDIG ist
cache_is_valid = (cached_ldf is not None and 
                  cached_ldf.get("used") is not None and 
                  len(cached_ldf.get("used", [])) > 0)

if cache_is_valid and current_ldf_mode == 'off':
    # Cache ist gültig UND LDF bereits deaktiviert - optimierter Build
    print(f"⚡ LDF bereits deaktiviert - Build läuft optimiert")
    
    unused_libs = cached_ldf.get("unused", [])
    if unused_libs:
        current_ignore = env.get("LIB_IGNORE", [])
        if isinstance(current_ignore, str):
            current_ignore = [current_ignore]
        elif current_ignore is None:
            current_ignore = []
        
        all_ignore = list(set(current_ignore + unused_libs))
        env.Replace(LIB_IGNORE=all_ignore)
        print(f"✅ {len(unused_libs)} Libraries ignoriert - Build beschleunigt")

elif cache_is_valid and current_ldf_mode != 'off':
    # Cache ist gültig aber LDF noch nicht deaktiviert
    print(f"⚡ Gültiger Cache gefunden - deaktiviere LDF für diesen Build")
    
    if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
        print(f"✅ lib_ldf_mode = off gesetzt")
        print(f"⚠ WICHTIG: Starten Sie den Build ERNEUT für optimierten Build")
        
        # Setze auch lib_ignore für den Fall dass der Build trotzdem läuft
        unused_libs = cached_ldf.get("unused", [])
        if unused_libs:
            current_ignore = env.get("LIB_IGNORE", [])
            if isinstance(current_ignore, str):
                current_ignore = [current_ignore]
            elif current_ignore is None:
                current_ignore = []
            
            all_ignore = list(set(current_ignore + unused_libs))
            env.Replace(LIB_IGNORE=all_ignore)

else:
    # Kein gültiger Cache - sammle Dependencies
    print(f"📝 Sammle Dependencies - LDF läuft normal")
    
    # Stelle sicher, dass LDF aktiviert ist
    if current_ldf_mode == 'off':
        backup_and_modify_correct_ini_file(env_name, set_ldf_off=False)
        print(f"✓ LDF reaktiviert für Dependency-Sammlung")
        print(f"⚠ Starten Sie den Build ERNEUT für LDF-Sammlung")
    
    def post_build_action(source, target, env):
        """Wird nach erfolgreichem Build ausgeführt - NUR für Cache-Erstellung"""
        print(f"\n🔄 Post-Build: Sammle LDF-Ergebnisse...")
        
        ldf_results = capture_ldf_results()
        
        if len(ldf_results["used"]) > 0:
            save_ldf_cache(ldf_results)
            
            used_count = len(ldf_results["used"])
            unused_count = len(ldf_results["unused"])
            
            print(f"📊 LDF-Analyse erfolgreich:")
            print(f"   Verfügbare Libraries: {len(ldf_results['available'])}")
            print(f"   Verwendete Libraries: {used_count}")
            print(f"   Ignorierte Libraries: {unused_count}")
            
            if unused_count > 0:
                print(f"\n🚫 Beispiele ignorierter Libraries:")
                for lib in sorted(ldf_results["unused"])[:5]:
                    print(f"   - {lib}")
                if len(ldf_results["unused"]) > 5:
                    print(f"   ... und {len(ldf_results['unused']) - 5} weitere")
            
            print(f"\n💡 Cache erstellt - führen Sie 'pio run' erneut aus")
            print(f"   Nächster Build wird {unused_count} Libraries überspringen")
            
        else:
            print(f"⚠ Keine verwendeten Libraries gefunden")
    
    env.AddPostAction("buildprog", post_build_action)

print(f"🏁 LDF Cache Setup abgeschlossen für {env_name}")
print(f"💡 Tipp: Löschen Sie '.pio/ldf_cache/' um den Cache zurückzusetzen\n")

