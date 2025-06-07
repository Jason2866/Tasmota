# post_build_sources.py
Import("env", "projenv")

def capture_final_sources(source, target, env):
    """Erfasst die finale Source-Reihenfolge nach dem Build"""
    
    # Global Environment Sources
    global_sources = env.get("SOURCES", [])
    
    # Project Environment Sources (falls verfügbar)
    project_sources = projenv.get("SOURCES", []) if 'projenv' in globals() else []
    
    print("=== Finale Build-Reihenfolge ===")
    print(f"Global Sources: {len(global_sources)} Dateien")
    print(f"Project Sources: {len(project_sources)} Dateien")
    
    # Sources mit Index ausgeben
    all_sources = global_sources if global_sources else project_sources
    
    for i, src in enumerate(all_sources, 1):
        print(f"{i:3d}. {src}")
    
    # In Datei speichern
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    with open(f"final_sources_{timestamp}.txt", 'w') as f:
        f.write("=== PlatformIO Final Sources Order ===\n\n")
        for i, src in enumerate(all_sources, 1):
            f.write(f"{i:3d}. {str(src)}\n")
    
    return all_sources

# Nach dem Build ausführen
env.AddPostAction("buildprog", capture_final_sources)
