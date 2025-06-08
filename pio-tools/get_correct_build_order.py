import os
import sys
import json
import subprocess
import shutil
from os.path import join

Import("env")
env = DefaultEnvironment()

def get_correct_build_order():
    """Kombiniert compile_commands.json (Reihenfolge) mit Build-Artefakten (Pfade)"""
    env_pio = env.get("PIOENV")
    project_dir = env.subst("$PROJECT_DIR")
    compiledb_dir = os.path.join(project_dir, ".pio", "compiledb")
    path_compile_commands = os.path.join(compiledb_dir, f"compile_commands_{env_pio}.json")
    # 1. Lade compile_commands.json für korrekte Reihenfolge
    if not os.path.exists(path_compile_commands):
        return None

    with open(path_compile_commands, "r") as f:
        compile_db = json.load(f)
    
    # 2. Finde Build-Verzeichnis
    build_dir = os.path.join(env.subst("$BUILD_DIR"))
    if not build_dir:
        print("FEHLER: build Verzeichnis nicht gefunden")
        return None
    
    results = {}
    env_name = os.path.basename(build_dir)

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
            ordered_objects.append({
                'order': i,
                'source': source_file,
                'object': obj_file,
            })
        
    results[env_name] = ordered_objects
        
    # 4. Speichere Ergebnisse
    with open(f"correct_build_order_{env_name}.txt", "w") as f:
#        f.write(f"KORREKTE BUILD-REIHENFOLGE für {env_name}\n")
#        f.write("Reihenfolge basiert auf compile_commands.json\n\n")
        for obj_info in ordered_objects:
#            f.write(f"{obj_info['order']:3d}: {obj_info['source']}\n")
            f.write(f"{obj_info['source']}\n")
#            f.write(f"{obj_info['object']}\n")
        
    # 5. Erstelle korrekte Linker Reihenfolge
    with open(f"correct_link_order_{env_name}.txt", "w") as f:
#        f.write(f"#KORREKTE LINKER-REIHENFOLGE für {env_name}\n")
#        f.write("# Reihenfolge basiert auf compile_commands.json\n\n")
        for obj_info in ordered_objects:
            f.write(f"{obj_info['object']}\n")
        
    print(f"Erstellt: correct_build_order_{env_name}.txt")
    print(f"Erstellt: correct_link_order_{env_name}.txt")
    
    return results

def environment_specific_compiledb_restart():
    """Environment-spezifische compiledb mit Verschieben und Umbenennen"""
    
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
    
    # Pfade definieren
    project_dir = env.subst("$PROJECT_DIR")
    compiledb_dir = os.path.join(project_dir, ".pio", "compiledb")
    standard_compile_db_path = os.path.join(project_dir, "compile_commands.json")
    target_compile_db_path = os.path.join(compiledb_dir, f"compile_commands_{env_name}.json")
    
    # Prüfe ob environment-spezifische Datei bereits existiert
    if os.path.exists(target_compile_db_path):
        #print(f"✓ compile_commands_{env_name}.json bereits vorhanden")
        return
    
    print("=" * 60)
    print(f"COMPILE_COMMANDS_{env_name.upper()}.JSON FEHLT")
    print("=" * 60)
    
    # Rekonstruiere korrekte PlatformIO Argumente
    pio_args = []
    
    # Environment hinzufügen
    pio_args.extend(["-e", env_name])
    
    # Targets hinzufügen (falls vorhanden)
    if current_targets:
        for target in current_targets:
            if target not in ["compiledb"]:  # compiledb ausschließen
                pio_args.extend(["-t", target])
    
    try:
        print(f"Environment: {env_name}")
        print("1. Breche aktuellen Build ab...")
        print("2. Erstelle compile_commands.json...")
        
        # Erstelle Zielverzeichnis falls es nicht existiert
        os.makedirs(compiledb_dir, exist_ok=True)
        
        # Lösche eventuell vorhandene Standard-Datei
        if os.path.exists(standard_compile_db_path):
            os.remove(standard_compile_db_path)
            print("   Alte compile_commands.json gelöscht")
        
        # Environment-spezifische compiledb Erstellung
        compiledb_cmd = ["pio", "run", "-e", env_name, "-t", "compiledb"]
        print(f"   Ausführe: {' '.join(compiledb_cmd)}")
        
        result = subprocess.run(compiledb_cmd, cwd=project_dir)
        
        if result.returncode != 0:
            print(f"✗ Fehler bei compile_commands.json Erstellung")
            sys.exit(1)
        
        # Prüfe ob Standard-Datei erstellt wurde
        if not os.path.exists(standard_compile_db_path):
            print(f"✗ compile_commands.json wurde nicht erstellt")
            sys.exit(1)
        
        # Verschiebe und benenne um
        print(f"3. Verschiebe zu compile_commands_{env_name}.json...")
        shutil.move(standard_compile_db_path, target_compile_db_path)
        
        # Prüfe ob Verschiebung erfolgreich war
        if os.path.exists(target_compile_db_path):
            file_size = os.path.getsize(target_compile_db_path)
            print(f"✓ compile_commands_{env_name}.json erfolgreich erstellt ({file_size} bytes)")
        else:
            print(f"✗ Fehler beim Verschieben der Datei")
            sys.exit(1)
        
        # Starte ursprünglichen Build neu
        print("4. Starte ursprünglichen Build neu...")
        restart_cmd = ["pio", "run"] + pio_args
        print(f"   Ausführe: {' '.join(restart_cmd)}")
        print("=" * 60)
        
        restart_result = subprocess.run(restart_cmd, cwd=project_dir)
        sys.exit(restart_result.returncode)
        
    except FileNotFoundError as e:
        print(f"✗ Datei nicht gefunden: {e}")
        sys.exit(1)
    except PermissionError as e:
        print(f"✗ Berechtigung verweigert: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Unerwarteter Fehler: {e}")
        sys.exit(1)

# Führe Check sofort aus
environment_specific_compiledb_restart()
get_correct_build_order()
