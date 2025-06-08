import os
import json
import subprocess
from os.path import join
from datetime import datetime

Import("env")
env = DefaultEnvironment()

def get_correct_build_order():
    """Kombiniert compile_commands.json (Reihenfolge) mit Build-Artefakten (Pfade)"""

    build_dir = env.subst("$BUILD_DIR")
    path_compile_commands = join(build_dir, "compile_commands.json")
    # 1. Lade compile_commands.json für korrekte Reihenfolge
    if not os.path.exists(path_compile_commands):
        print("FEHLER: compile_commands.json nicht gefunden")
        return None

    with open(path_compile_commands, "r") as f:
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

def environment_specific_compiledb_restart():
    """Environment-spezifische compiledb mit env-spezifischem Dateinamen"""
    
    current_targets = COMMAND_LINE_TARGETS[:]
    is_build_target = (
        not current_targets or
        any(target in ["build", "buildprog"] for target in current_targets)
    )
    
    if not is_build_target:
        return
    
    env_name = env.get("PIOENV")
    
    if not env_name:
        print("✗ Fehler: Kein Environment definiert")
        sys.exit(1)
    
    # Environment-spezifischer Dateiname
    compile_db_path = os.path.join(env.subst("$PROJECT_DIR"), f"compile_commands_{env_name}.json")
    
    if os.path.exists(compile_db_path):
        return  # Environment-spezifische JSON existiert bereits
    
    print("=" * 60)
    print(f"COMPILE_COMMANDS_{env_name.upper()}.JSON FEHLT - ERSTELLE UND STARTE NEU")
    print("=" * 60)
    
    project_dir = env.subst("$PROJECT_DIR")
    original_args = sys.argv[1:]  # Alle ursprünglichen pio run Argumente
    
    try:
        print(f"Environment: {env_name}")
        print("1. Breche aktuellen Build ab...")
        print(f"2. Erstelle compile_commands_{env_name}.json...")
        
        # Environment-spezifische compiledb Erstellung
        compiledb_cmd = ["pio", "run", "-e", env_name, "-t", "compiledb"]
        print(f"   Ausführe: {' '.join(compiledb_cmd)}")
        
        result = subprocess.run(compiledb_cmd, cwd=project_dir)
        
        if result.returncode != 0:
            print(f"✗ Fehler bei compile_commands_{env_name}.json Erstellung")
            sys.exit(1)
        
        # Umbenennen der erstellten compile_commands.json zu environment-spezifischem Namen
        standard_path = os.path.join(project_dir, "compile_commands.json")
        if os.path.exists(standard_path):
            os.rename(standard_path, compile_db_path)
            print(f"✓ compile_commands_{env_name}.json erfolgreich erstellt")
        else:
            print("✗ Standard compile_commands.json nicht gefunden")
            sys.exit(1)
        
        # Starte mit ursprünglichen Argumenten neu
        print("3. Starte ursprünglichen Build neu...")
        restart_cmd = ["pio", "run"] + original_args
        print(f"   Ausführe: {' '.join(restart_cmd)}")
        
        restart_result = subprocess.run(restart_cmd, cwd=project_dir)
        sys.exit(restart_result.returncode)
        
    except Exception as e:
        print(f"✗ Fehler: {e}")
        sys.exit(1)

environment_specific_compiledb_restart()
get_correct_build_order()
