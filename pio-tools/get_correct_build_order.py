import os
import json
from datetime import datetime

Import("env")

def get_correct_build_order():
    """Kombiniert compile_commands.json (Reihenfolge) mit Build-Artefakten (Pfade)"""
    
    # 1. Lade compile_commands.json für korrekte Reihenfolge
    if not os.path.exists("compile_commands.json"):
        print("FEHLER: compile_commands.json nicht gefunden")
        print("Führe erst aus: python -m platformio run -t compiledb")
        return None
    
    with open("compile_commands.json", "r") as f:
        compile_db = json.load(f)
    
    # 2. Finde Build-Verzeichnis
    build_dirs = []
    if os.path.exists('.pio/build'):
        build_dirs = [os.path.join('.pio/build', d) 
                     for d in os.listdir('.pio/build') 
                     if os.path.isdir(os.path.join('.pio/build', d))]
    
    if not build_dirs:
        print("FEHLER: Kein .pio/build Verzeichnis gefunden")
        return None
    
    results = {}
    
    for build_dir in build_dirs:
        env_name = os.path.basename(build_dir)
        print(f"\nAnalysiere Environment: {env_name}")
        
        # 3. Mappe Source-Dateien zu Objekt-Dateien
        ordered_objects = []
        
        for i, entry in enumerate(compile_db, 1):
            source_file = entry.get('file', '')
            command = entry.get('command', '')
            
            # Extrahiere Objekt-Datei aus Kommando
            import re
            obj_match = re.search(r'-o\s+(\S+\.o)', command)
            
            if obj_match:
                obj_file = obj_match.group(1)
                
                # Prüfe ob Objekt-Datei existiert
                if os.path.exists(obj_file):
                    ordered_objects.append({
                        'order': i,
                        'source': source_file,
                        'object': obj_file,
                        'exists': True
                    })
                else:
                    ordered_objects.append({
                        'order': i,
                        'source': source_file,
                        'object': obj_file,
                        'exists': False
                    })
        
        results[env_name] = ordered_objects
        
        # 4. Speichere Ergebnisse
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        with open(f"correct_build_order_{env_name}_{timestamp}.txt", "w") as f:
            f.write(f"KORREKTE BUILD-REIHENFOLGE für {env_name}\n")
            f.write("=" * 60 + "\n\n")
            f.write("Reihenfolge basiert auf compile_commands.json\n")
            f.write("(nicht auf Datei-Erstellungszeit)\n\n")
            
            for obj_info in ordered_objects:
                status = "✓" if obj_info['exists'] else "✗"
                f.write(f"{obj_info['order']:3d}: {status} {obj_info['source']}\n")
                f.write(f"     -> {obj_info['object']}\n\n")
        
        # 5. Erstelle korrektes Linker-Kommando
        with open(f"correct_link_command_{env_name}_{timestamp}.sh", "w") as f:
            f.write("#!/bin/bash\n")
            f.write(f"# Korrektes Linker-Kommando für {env_name}\n")
            f.write("# Reihenfolge basiert auf compile_commands.json\n\n")
            
            f.write("g++ \\\n")
            for obj_info in ordered_objects:
                if obj_info['exists']:
                    f.write(f"  {obj_info['object']} \\\n")
            f.write(f"  -o {build_dir}/firmware.elf\n")
        
        print(f"Erstellt: correct_build_order_{env_name}_{timestamp}.txt")
        print(f"Erstellt: correct_link_command_{env_name}_{timestamp}.sh")
        print(f"Objekt-Dateien: {len([o for o in ordered_objects if o['exists']])}/{len(ordered_objects)}")
    
    return results


get_correct_build_order()
