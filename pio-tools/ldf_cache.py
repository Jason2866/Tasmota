Import("env")
import os
import json
import hashlib

def get_cache_file_path():
    """Generiert Pfad zur LDF-Cache-Datei für das aktuelle Environment"""
    env_name = env.get("PIOENV")
    project_dir = env.get("PROJECT_DIR")
    cache_dir = os.path.join(project_dir, ".pio", "ldf_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{env_name}_ldf_cache.json")

def get_config_hash():
    """Erstellt Hash der relevanten Konfiguration für Cache-Invalidierung"""
    config_items = [
        str(env.get("BUILD_FLAGS", [])),
        str(env.get("LIB_DEPS", [])),
        env.get("BOARD", ""),
        env.get("PLATFORM", ""),
        str(env.get("LIB_IGNORE", []))
    ]
    config_string = "|".join(config_items)
    return hashlib.md5(config_string.encode()).hexdigest()

def scan_available_libraries():
    """Scannt alle verfügbaren Libraries im lib/ Ordner"""
    project_dir = env.get("PROJECT_DIR")
    lib_dir = os.path.join(project_dir, "lib")
    
    available_libs = []
    if os.path.exists(lib_dir):
        for root, dirs, files in os.walk(lib_dir):
            # Prüfe ob es ein Library-Verzeichnis ist
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
    # Alle verfügbaren Libraries
    available_libs = scan_available_libraries()
    
    # Aktuell ignorierte Libraries (diese sind ungenutzt)
    current_ignore = env.get("LIB_IGNORE", [])
    if isinstance(current_ignore, str):
        current_ignore = [current_ignore]
    elif current_ignore is None:
        current_ignore = []
    
    # Verwendete Libraries = Verfügbare - Ignorierte
    ignored_libs = set(current_ignore)
    used_libs = [lib for lib in available_libs if lib not in ignored_libs]
    
    # Zusätzlich: Externe lib_deps
    external_deps = env.get("LIB_DEPS", [])
    if external_deps:
        for dep in external_deps:
            if isinstance(dep, str) and not dep.startswith("${"):
                # Extrahiere Library-Namen aus externen Dependencies
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
        
        # Prüfe Cache-Gültigkeit
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

def apply_cached_ldf(ldf_results):
    """Wendet gecachte LDF-Ergebnisse an"""
    # 1. LDF deaktivieren
    env.Replace(LIB_LDF_MODE="off")
    
    # 2. Externe Dependencies setzen
    external_deps = ldf_results.get("external_deps", [])
    if external_deps:
        current_deps = env.get("LIB_DEPS", [])
        if isinstance(current_deps, str):
            current_deps = [current_deps]
        elif current_deps is None:
            current_deps = []
        
        # Kombiniere bestehende und gecachte externe Dependencies
        all_deps = list(set(current_deps + external_deps))
        env.Replace(LIB_DEPS=all_deps)
    
    # 3. lib_ignore setzen
    unused_libs = ldf_results.get("unused", [])
    if unused_libs:
        current_ignore = env.get("LIB_IGNORE", [])
        if isinstance(current_ignore, str):
            current_ignore = [current_ignore]
        elif current_ignore is None:
            current_ignore = []
        
        # Kombiniere bestehende und gecachte ignores
        all_ignore = list(set(current_ignore + unused_libs))
        env.Replace(LIB_IGNORE=all_ignore)
    
    print(f"⚡ LDF übersprungen - Build beschleunigt")
    return True

# =============================================================================
# HAUPTLOGIK
# =============================================================================

print(f"\n🔍 Tasmota LDF Cache für Environment: {env.get('PIOENV')}")

# Versuche LDF-Cache zu laden
cached_ldf = load_ldf_cache()

if cached_ldf is not None:
    # Cache vorhanden - LDF überspringen
    if apply_cached_ldf(cached_ldf):
        used_count = len(cached_ldf.get("used", []))
        unused_count = len(cached_ldf.get("unused", []))
        print(f"✅ Cache angewendet: {used_count} Libraries verwendet, {unused_count} ignoriert")
    else:
        print(f"⚠ Fehler beim Anwenden des Caches")

else:
    # Kein Cache - LDF normal laufen lassen und Ergebnisse erfassen
    print(f"📝 Erster Build - LDF wird ausgeführt und Ergebnisse gecacht")
    
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
            print(f"\n💡 Beim nächsten Build werden {unused_count} Libraries übersprungen")
            print(f"   Erwartete Zeitersparnis: Deutlich schnellerer LDF-Scan")
    
    # Registriere Post-Build Action
    env.AddPostAction("buildprog", post_build_cache_ldf)

print(f"🏁 LDF Cache Setup abgeschlossen für {env.get('PIOENV')}\n")

