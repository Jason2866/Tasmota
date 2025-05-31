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

def scan_local_libraries_recursive():
    """Scannt rekursiv alle Libraries im lib/ Ordner und Unterordnern"""
    project_dir = env.get("PROJECT_DIR")
    lib_dir = os.path.join(project_dir, "lib")
    
    available_libs = []
    if os.path.exists(lib_dir):
        for root, dirs, files in os.walk(lib_dir):
            # Prüfe ob es ein Library-Verzeichnis ist
            has_library_config = any(f in files for f in ['library.json', 'library.properties'])
            has_headers = any(f.endswith(('.h', '.hpp')) for f in files)
            has_sources = any(f.endswith(('.cpp', '.c', '.ino')) for f in files)
            
            if has_library_config or has_headers or has_sources:
                # Extrahiere Library-Namen relativ zum lib/ Ordner
                rel_path = os.path.relpath(root, lib_dir)
                if rel_path != '.':  # Nicht das lib/ Verzeichnis selbst
                    # Verwende nur den Ordnernamen, nicht den ganzen Pfad
                    lib_name = os.path.basename(root)
                    available_libs.append(lib_name)
    
    # Entferne Duplikate und sortiere
    available_libs = sorted(list(set(available_libs)))
    
    print(f"📚 Gefundene Libraries (rekursiv): {len(available_libs)}")
    for lib in available_libs:
        print(f"   - {lib}")
    
    return available_libs

def get_used_libraries_from_ldf():
    """Ermittelt tatsächlich verwendete Libraries über LDF-Ausgabe"""
    used_libs = []
    
    # Hole die vom LDF ermittelten Dependencies
    lib_deps = env.get("LIB_DEPS", [])
    if lib_deps:
        for dep in lib_deps:
            # Extrahiere Library-Namen (ohne Pfade oder Versionen)
            if isinstance(dep, str):
                lib_name = dep.split('/')[-1].split('@')[0]
                used_libs.append(lib_name)
    
    # Alternative: Scanne Build-Flags nach Library-Includes
    build_flags = env.get("BUILD_FLAGS", [])
    for flag in build_flags:
        if isinstance(flag, str) and flag.startswith("-I") and "lib/" in flag:
            lib_path = flag.replace("-I", "").strip()
            if "/lib/" in lib_path:
                lib_name = lib_path.split("/lib/")[-1].split("/")[0]
                if lib_name:
                    used_libs.append(lib_name)
    
    # Entferne Duplikate
    used_libs = list(set(used_libs))
    
    print(f"🔧 Verwendete Libraries: {len(used_libs)}")
    for lib in used_libs:
        print(f"   - {lib}")
    
    return used_libs

def analyze_tasmota_dependencies():
    """Analysiert Dependencies speziell für Tasmota mit statischen Libraries"""
    # 1. Alle verfügbaren Libraries (rekursiv)
    available_libs = scan_local_libraries_recursive()
    
    # 2. Vom LDF ermittelte verwendete Libraries
    used_libs = get_used_libraries_from_ldf()
    
    # 3. Ungenutzte Libraries ermitteln
    unused_libs = set(available_libs) - set(used_libs)
    
    print(f"\n📊 Tasmota Library-Analyse für {env.get('PIOENV')}:")
    print(f"   Verfügbare Libraries: {len(available_libs)}")
    print(f"   Verwendete Libraries: {len(used_libs)}")
    print(f"   Ungenutzte Libraries: {len(unused_libs)}")
    
    if unused_libs:
        print(f"\n🚫 Ungenutzte Libraries:")
        for lib in sorted(unused_libs):
            print(f"   - {lib}")
    
    return {
        "available": available_libs,
        "used": used_libs,
        "unused": list(unused_libs)
    }

def save_deps_cache(analysis_result):
    """Speichert Library-Analyse im Cache"""
    cache_file = get_cache_file_path()
    cache_data = {
        "config_hash": get_config_hash(),
        "analysis": analysis_result,
        "env_name": env.get("PIOENV"),
        "timestamp": env.get("UNIX_TIME", 0)
    }
    
    with open(cache_file, 'w') as f:
        json.dump(cache_data, f, indent=2)
    
    used_count = len(analysis_result["used"])
    unused_count = len(analysis_result["unused"])
    print(f"✓ Library-Analyse gespeichert: {used_count} verwendet, {unused_count} ungenutzt")

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

def load_cached_analysis():
    """Lädt gecachte Library-Analyse"""
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        print(f"ℹ Kein Cache gefunden für {env.get('PIOENV')}")
        return None
    
    try:
        with open(cache_file, 'r') as f:
            cache_data = json.load(f)
        
        if cache_data.get("config_hash") == get_config_hash():
            analysis = cache_data.get("analysis")
            if analysis:
                used_count = len(analysis.get("used", []))
                unused_count = len(analysis.get("unused", []))
                print(f"✓ Library-Analyse Cache geladen für {env.get('PIOENV')}: {used_count} verwendet, {unused_count} ungenutzt")
                return analysis
        else:
            print(f"⚠ Cache ungültig für {env.get('PIOENV')} - wird neu erstellt")
            
    except (json.JSONDecodeError, KeyError) as e:
        print(f"⚠ Cache beschädigt für {env.get('PIOENV')}: {e}")
    
    return None

def apply_lib_ignore():
    """Wendet lib_ignore für ungenutzte Libraries an"""
    analysis = load_cached_analysis()
    
    if analysis and analysis.get("unused"):
        unused_libs = analysis["unused"]
        
        # Hole aktuelle lib_ignore Liste
        current_ignore = env.get("LIB_IGNORE", [])
        if isinstance(current_ignore, str):
            current_ignore = [current_ignore]
        elif current_ignore is None:
            current_ignore = []
        
        # Füge ungenutzte Libraries hinzu (ohne Duplikate)
        all_ignore = list(set(current_ignore + unused_libs))
        env.Replace(LIB_IGNORE=all_ignore)
        
        print(f"⚡ lib_ignore angewendet: {len(unused_libs)} Libraries ignoriert")
        print(f"   Ignorierte Libraries: {sorted(unused_libs)}")
        return True
    
    return False

# Hauptlogik für Tasmota
print(f"\n🔍 Tasmota LDF Cache für Environment: {env.get('PIOENV')}")

cached_analysis = load_cached_analysis()

if cached_analysis is None:
    print(f"📝 Erste Library-Analyse wird durchgeführt...")
    
    def post_build_action(source, target, env):
        print(f"\n🔄 Führe Library-Analyse durch...")
        analysis = analyze_tasmota_dependencies()
        save_deps_cache(analysis)
        
        # Zeige Zusammenfassung
        if analysis["unused"]:
            print(f"\n💡 Tipp: {len(analysis['unused'])} ungenutzte Libraries gefunden.")
            print(f"   Beim nächsten Build werden diese automatisch ignoriert.")
    
    env.AddPostAction("buildprog", post_build_action)
else:
    # Wende lib_ignore an
    if apply_lib_ignore():
        print(f"✅ Build-Optimierung aktiv")
    else:
        print(f"ℹ Alle Libraries werden verwendet")

