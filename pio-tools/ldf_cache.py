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
    return os.path.join(cache_dir, f"{env_name}_deps.json")

def get_config_hash():
    """Erstellt Hash der relevanten Konfiguration"""
    config_items = [
        str(env.get("BUILD_FLAGS", [])),
        str(env.get("LIB_DEPS", [])),
        env.get("BOARD", ""),
        env.get("PLATFORM", "")
    ]
    config_string = "|".join(config_items)
    return hashlib.md5(config_string.encode()).hexdigest()

def load_cached_deps():
    """Lädt gecachte Dependencies falls vorhanden und gültig"""
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        return None
    
    try:
        with open(cache_file, 'r') as f:
            cache_data = json.load(f)
        
        if cache_data.get("config_hash") == get_config_hash():
            analysis = cache_data.get("analysis", {})
            used_libs = analysis.get("used", [])
            if used_libs:
                print(f"✓ LDF Cache geladen für {env.get('PIOENV')}: {len(used_libs)} Dependencies")
                return used_libs
        else:
            print(f"⚠ Cache ungültig für {env.get('PIOENV')} - wird neu erstellt")
            
    except (json.JSONDecodeError, KeyError) as e:
        print(f"⚠ Cache beschädigt für {env.get('PIOENV')}: {e}")
    
    return None

def scan_local_libraries_recursive():
    """Scannt rekursiv alle Libraries im lib/ Ordner und Unterordnern"""
    project_dir = env.get("PROJECT_DIR")
    lib_dir = os.path.join(project_dir, "lib")
    
    available_libs = []
    if os.path.exists(lib_dir):
        for root, dirs, files in os.walk(lib_dir):
            has_library_config = any(f in files for f in ['library.json', 'library.properties'])
            has_headers = any(f.endswith(('.h', '.hpp')) for f in files)
            has_sources = any(f.endswith(('.cpp', '.c', '.ino')) for f in files)
            
            if has_library_config or has_headers or has_sources:
                rel_path = os.path.relpath(root, lib_dir)
                if rel_path != '.':
                    lib_name = os.path.basename(root)
                    available_libs.append(lib_name)
    
    return sorted(list(set(available_libs)))

def save_analysis_cache(analysis):
    """Speichert Library-Analyse im Cache"""
    cache_file = get_cache_file_path()
    cache_data = {
        "config_hash": get_config_hash(),
        "analysis": analysis,
        "env_name": env.get("PIOENV")
    }
    
    with open(cache_file, 'w') as f:
        json.dump(cache_data, f, indent=2)
    
    used_count = len(analysis["used"])
    unused_count = len(analysis["unused"])
    print(f"✓ Library-Analyse gespeichert: {used_count} verwendet, {unused_count} ungenutzt")

# HAUPTLOGIK - Sofortige Entscheidung beim Script-Load
print(f"🔍 Tasmota LDF Cache für Environment: {env.get('PIOENV')}")

# Versuche gecachte Dependencies zu laden
cached_deps = load_cached_deps()

if cached_deps is not None:
    # Cache vorhanden - LDF sofort deaktivieren
    print(f"⚡ LDF deaktiviert - verwende Cache mit {len(cached_deps)} Dependencies")
    env.Replace(LIB_LDF_MODE="off")
    
    # Setze explizite lib_deps basierend auf Cache
    current_lib_deps = env.get("LIB_DEPS", [])
    if isinstance(current_lib_deps, str):
        current_lib_deps = [current_lib_deps]
    elif current_lib_deps is None:
        current_lib_deps = []
    
    # Kombiniere aktuelle lib_deps mit gecachten
    all_deps = list(set(current_lib_deps + cached_deps))
    env.Replace(LIB_DEPS=all_deps)
    
    print(f"✅ Build-Optimierung aktiv - LDF übersprungen")
    
else:
    # Kein Cache - LDF normal laufen lassen
    print(f"📝 Kein gültiger Cache - LDF wird ausgeführt")
    
    def capture_ldf_results(source, target, env):
        """Erfasst LDF-Ergebnisse nach dem Build"""
        print(f"🔄 Sammle Library-Dependencies für zukünftige Builds...")
        
        # Sammle alle verfügbaren Libraries
        available_libs = scan_local_libraries_recursive()
        
        # Sammle verwendete Libraries aus verschiedenen Quellen
        used_libs = []
        
        # 1. Aus aktuellen LIB_DEPS
        lib_deps = env.get("LIB_DEPS", [])
        if lib_deps:
            for dep in lib_deps:
                if isinstance(dep, str):
                    lib_name = dep.split('/')[-1].split('@')[0]
                    used_libs.append(lib_name)
        
        # 2. Aus Build-Flags
        build_flags = env.get("BUILD_FLAGS", [])
        for flag in build_flags:
            if isinstance(flag, str) and flag.startswith("-I") and "/lib/" in flag:
                lib_path = flag.replace("-I", "").strip()
                lib_name = lib_path.split("/lib/")[-1].split("/")[0]
                if lib_name and lib_name in available_libs:
                    used_libs.append(lib_name)
        
        # Entferne Duplikate
        used_libs = sorted(list(set(used_libs)))
        unused_libs = sorted(list(set(available_libs) - set(used_libs)))
        
        analysis = {
            "available": available_libs,
            "used": used_libs,
            "unused": unused_libs
        }
        
        print(f"📊 Library-Analyse: {len(used_libs)} verwendet, {len(unused_libs)} ungenutzt")
        save_analysis_cache(analysis)
        print(f"💡 Nächster Build wird LDF überspringen und {len(used_libs)} Dependencies direkt verwenden")
    
    # Registriere Post-Build Action
    env.AddPostAction("buildprog", capture_ldf_results)

