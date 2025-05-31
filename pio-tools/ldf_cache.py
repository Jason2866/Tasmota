Import("env")
import os
import json
import hashlib
import glob
import configparser

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
    ini_files = glob.glob(os.path.join(project_dir, 'platformio*.ini'))
    
    # Sortiere um Priorität zu gewährleisten (override sollte zuletzt kommen)
    ini_files.sort(key=lambda x: ('override' in os.path.basename(x), x))
    
    print(f"📁 Gefundene PlatformIO Konfigurationsdateien:")
    for ini_file in ini_files:
        print(f"   - {os.path.basename(ini_file)}")
    
    return ini_files

def find_env_definition_file(env_name):
    """Findet die Datei, die das spezifische Environment definiert"""
    project_dir = env.get("PROJECT_DIR")
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
            print(f"⚠ Fehler beim Lesen von {ini_file}: {e}")
            continue
    
    print(f"⚠ Environment [env:{env_name}] nicht in PlatformIO-Dateien gefunden")
    return None

def get_current_ldf_mode(env_name):
    """Ermittelt den aktuellen LDF-Modus für das Environment"""
    ini_files = find_all_platformio_files()
    
    # Lade alle Konfigurationen in der richtigen Reihenfolge
    combined_config = configparser.ConfigParser(allow_no_value=True)
    
    for ini_file in ini_files:
        try:
            temp_config = configparser.ConfigParser(allow_no_value=True)
            temp_config.read(ini_file, encoding='utf-8')
            
            # Merge Konfigurationen
            for section in temp_config.sections():
                if not combined_config.has_section(section):
                    combined_config.add_section(section)
                for key, value in temp_config.items(section):
                    combined_config.set(section, key, value)
                    
        except Exception as e:
            print(f"⚠ Fehler beim Lesen von {ini_file}: {e}")
            continue
    
    # Prüfe LDF-Modus
    section_name = f"env:{env_name}"
    if combined_config.has_section(section_name):
        if combined_config.has_option(section_name, 'lib_ldf_mode'):
            return combined_config.get(section_name, 'lib_ldf_mode')
    
    # Fallback: Prüfe [env] Sektion
    if combined_config.has_section('env'):
        if combined_config.has_option('env', 'lib_ldf_mode'):
            return combined_config.get('env', 'lib_ldf_mode')
    
    return 'chain'  # PlatformIO Standard

def modify_ldf_mode_in_override(env_name, set_ldf_off=True):
    """Modifiziert LDF-Modus in platformio_override.ini"""
    project_dir = env.get("PROJECT_DIR")
    override_file = os.path.join(project_dir, "platformio_override.ini")
    
    # Erstelle platformio_override.ini falls nicht vorhanden
    if not os.path.exists(override_file):
        print(f"📝 Erstelle {override_file}")
        with open(override_file, 'w') as f:
            f.write("; PlatformIO Override Configuration\n")
            f.write("; This file is used to override settings from other platformio*.ini files\n\n")
    
    try:
        config = configparser.ConfigParser(allow_no_value=True)
        config.read(override_file, encoding='utf-8')
        
        section_name = f"env:{env_name}"
        
        # Erstelle Sektion falls nicht vorhanden
        if not config.has_section(section_name):
            config.add_section(section_name)
            print(f"📝 Sektion [{section_name}] zu {os.path.basename(override_file)} hinzugefügt")
        
        if set_ldf_off:
            config.set(section_name, "lib_ldf_mode", "off")
            print(f"✓ lib_ldf_mode = off gesetzt in {os.path.basename(override_file)}")
        else:
            # Entferne lib_ldf_mode Override (zurück zum Standard)
            if config.has_option(section_name, "lib_ldf_mode"):
                config.remove_option(section_name, "lib_ldf_mode")
                print(f"✓ lib_ldf_mode Override entfernt aus {os.path.basename(override_file)}")
        
        # Schreibe Konfiguration zurück
        with open(override_file, 'w') as f:
            config.write(f, space_around_delimiters=True)
        
        return True
        
    except Exception as e:
        print(f"⚠ Fehler beim Modifizieren von {override_file}: {e}")
        return False

def get_config_hash():
    """Erstellt Hash aller relevanten Konfigurationsdateien"""
    project_dir = env.get("PROJECT_DIR")
    ini_files = find_all_platformio_files()
    
    config_content = []
    
    for ini_file in ini_files:
        try:
            with open(ini_file, 'r', encoding='utf-8') as f:
                content = f.read()
                config_content.append(f"{os.path.basename(ini_file)}:{content}")
        except Exception:
            continue
    
    # Zusätzliche Environment-spezifische Werte
    config_content.extend([
        str(env.get("BUILD_FLAGS", [])),
        env.get("BOARD", ""),
        env.get("PLATFORM", "")
    ])
    
    config_string = "|".join(config_content)
    return hashlib.md5(config_string.encode()).hexdigest()

def scan_available_libraries():
    """Scannt alle verfügbaren Libraries im lib/ Ordner"""
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

# =============================================================================
# HAUPTLOGIK
# =============================================================================

print(f"\n🔍 Tasmota LDF Cache für Environment: {env.get('PIOENV')}")

env_name = env.get("PIOENV")

# Zeige aktuelle Konfiguration
current_ldf_mode = get_current_ldf_mode(env_name)
print(f"📊 Aktueller LDF-Modus: {current_ldf_mode}")

cached_ldf = load_ldf_cache()

if cached_ldf is not None:
    # Cache vorhanden - setze LDF auf off in override
    print(f"⚡ LDF Cache gefunden - setze lib_ldf_mode = off in platformio_override.ini")
    
    if modify_ldf_mode_in_override(env_name, set_ldf_off=True):
        unused_libs = cached_ldf.get("unused", [])
        if unused_libs:
            current_ignore = env.get("LIB_IGNORE", [])
            if isinstance(current_ignore, str):
                current_ignore = [current_ignore]
            elif current_ignore is None:
                current_ignore = []
            
            all_ignore = list(set(current_ignore + unused_libs))
            env.Replace(LIB_IGNORE=all_ignore)
        
        used_count = len(cached_ldf.get("used", []))
        unused_count = len(cached_ldf.get("unused", []))
        print(f"✅ Override gesetzt: {used_count} verwendet, {unused_count} ignoriert")
        print(f"⚠ HINWEIS: Starten Sie den Build erneut, um die LDF-Optimierung zu nutzen")

else:
    # Kein Cache - stelle sicher, dass LDF aktiviert ist
    print(f"📝 Erster Build - stelle sicher dass LDF aktiviert ist")
    modify_ldf_mode_in_override(env_name, set_ldf_off=False)
    
    def post_build_cache_ldf(source, target, env):
        """Erfasst LDF-Ergebnisse nach erfolgreichem Build"""
        print(f"\n🔄 Erfasse LDF-Ergebnisse für zukünftige Builds...")
        
        ldf_results = capture_ldf_results()
        save_ldf_cache(ldf_results)
        
        used_count = len(ldf_results["used"])
        unused_count = len(ldf_results["unused"])
        
        print(f"📊 LDF-Analyse abgeschlossen:")
        print(f"   Verfügbare Libraries: {len(ldf_results['available'])}")
        print(f"   Verwendete Libraries: {used_count}")
        print(f"   Ignorierte Libraries: {unused_count}")
        
        if unused_count > 0:
            print(f"\n💡 Führen Sie den Build erneut aus, um {unused_count} Libraries zu überspringen")
    
    env.AddPostAction("buildprog", post_build_cache_ldf)

print(f"🏁 LDF Cache Setup abgeschlossen für {env_name}\n")

