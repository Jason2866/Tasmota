# detailed_source_analysis.py
Import("env")

def analyze_sources_detailed(source, target, env):
    """Detaillierte Analyse der Source-Dateien"""
    
    sources = env.get("SOURCES", [])
    
    # Kategorisierung der Sources
    categories = {
        'framework': [],
        'libraries': [],
        'project': [],
        'external': [],
        'unknown': []
    }
    
    for src in sources:
        src_path = str(src)
        
        if 'framework-' in src_path or 'arduino' in src_path.lower():
            categories['framework'].append(src_path)
        elif '.pio/libdeps' in src_path:
            categories['libraries'].append(src_path)
        elif 'src/' in src_path:
            categories['project'].append(src_path)
        elif 'external' in src_path:
            categories['external'].append(src_path)
        else:
            categories['unknown'].append(src_path)
    
    # Detaillierten Report erstellen
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    with open(f"source_analysis_{timestamp}.txt", 'w', encoding='utf-8') as f:
        f.write("=== PlatformIO Source-Analyse ===\n\n")
        f.write(f"Gesamt: {len(sources)} Source-Dateien\n\n")
        
        for category, files in categories.items():
            if files:
                f.write(f"=== {category.upper()} ({len(files)} Dateien) ===\n")
                for i, file_path in enumerate(files, 1):
                    f.write(f"{i:3d}. {file_path}\n")
                f.write("\n")
    
    print(f"Source-Analyse gespeichert: source_analysis_{timestamp}.txt")
    
    # Zusammenfassung ausgeben
    print("=== Source-Kategorien ===")
    for category, files in categories.items():
        if files:
            print(f"{category:12s}: {len(files):3d} Dateien")

env.AddPostAction("buildprog", analyze_sources_detailed)
