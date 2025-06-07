import os
import sys
import subprocess
import re
import json
from datetime import datetime

Import("env")

def parse_verbose_output(output):
    """Parst den Verbose-Output und extrahiert alle Kommandos"""
    
    compile_commands = []
    link_commands = []
    archive_commands = []
    
    # Compile-Kommandos (C/C++)
    compile_patterns = [
        r'.*?g\+\+.*?-c.*?\.cpp.*?-o.*?\.o',
        r'.*?gcc.*?-c.*?\.c.*?-o.*?\.o',
        r'.*?xtensa-esp32.*?-c.*?-o.*?\.o',
        r'.*?riscv32.*?-c.*?-o.*?\.o'
    ]
    
    for pattern in compile_patterns:
        matches = re.findall(pattern, output, re.MULTILINE)
        compile_commands.extend([cmd.strip() for cmd in matches])
    
    # Link-Kommandos
    link_patterns = [
        r'.*?g\+\+.*?\.o.*?-o.*?\.elf',
        r'.*?xtensa-esp32.*?\.o.*?-o.*?\.elf',
        r'.*?riscv32.*?\.o.*?-o.*?\.elf'
    ]
    
    for pattern in link_patterns:
        matches = re.findall(pattern, output, re.MULTILINE)
        link_commands.extend([cmd.strip() for cmd in matches])
    
    # Archive-Kommandos
    archive_patterns = [
        r'.*?ar.*?rcs.*?\.a.*?\.o',
        r'.*?xtensa-esp32.*?ar.*?\.a',
        r'.*?riscv32.*?ar.*?\.a'
    ]
    
    for pattern in archive_patterns:
        matches = re.findall(pattern, output, re.MULTILINE)
        archive_commands.extend([cmd.strip() for cmd in matches])
    
    return compile_commands, link_commands, archive_commands

def save_parsed_commands(compile_cmds, link_cmds, archive_cmds, full_output):
    """Speichert geparste Kommandos"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Shell-Script mit allen Kommandos
    with open(f"build_commands_{timestamp}.sh", "w") as f:
        f.write("#!/bin/bash\n")
        f.write(f"# Generated: {datetime.now()}\n")
        f.write(f"# Total Commands: {len(compile_cmds) + len(link_cmds) + len(archive_cmds)}\n\n")
        
        f.write("# COMPILE COMMANDS\n")
        for cmd in compile_cmds:
            f.write(f"{cmd}\n")
        
        f.write("\n# ARCHIVE COMMANDS\n")
        for cmd in archive_cmds:
            f.write(f"{cmd}\n")
        
        f.write("\n# LINK COMMANDS\n")
        for cmd in link_cmds:
            f.write(f"{cmd}\n")
    
    # JSON-Format
    data = {
        'timestamp': datetime.now().isoformat(),
        'compile_commands': compile_cmds,
        'link_commands': link_cmds,
        'archive_commands': archive_cmds,
        'total_commands': len(compile_cmds) + len(link_cmds) + len(archive_cmds)
    }
    
    with open(f"build_commands_{timestamp}.json", "w") as f:
        json.dump(data, f, indent=2)
    
    # Vollständiger Output
    with open(f"pio_verbose_output_{timestamp}.log", "w") as f:
        f.write(full_output)
    
    print(f"\n=== BUILD COMMANDS EXTRACTED ===")
    print(f"Compile Commands: {len(compile_cmds)}")
    print(f"Link Commands: {len(link_cmds)}")
    print(f"Archive Commands: {len(archive_cmds)}")
    print(f"Total: {len(compile_cmds) + len(link_cmds) + len(archive_cmds)}")

def check_verbose_mode():
    """Prüft ob Verbose-Modus aktiv ist"""
    
    # Prüfe SCONSFLAGS Environment-Variable
    sconsflags = os.environ.get('SCONSFLAGS', '')
    if '-v' in sconsflags or '--verbose' in sconsflags:
        return True
    
    # Prüfe Kommandozeilen-Argumente
    if '--verbose' in sys.argv or '-v' in sys.argv:
        return True
    
    # Prüfe ob SCons mit Debug/Verbose gestartet wurde
    if '--debug' in sys.argv:
        return True
    
    return False

def pre_script_verbose_parser(env):
    """Pre-Script das Verbose-Modus erzwingt und Output parst"""
    
    verbose_active = check_verbose_mode()
    
    print(f'[VERBOSE-PARSER] Script gestartet')
    print(f'[VERBOSE-PARSER] sys.argv: {sys.argv}')
    print(f'[VERBOSE-PARSER] SCONSFLAGS: {os.environ.get("SCONSFLAGS", "not set")}')
    print(f'[VERBOSE-PARSER] Verbose aktiv: {verbose_active}')
    
    if verbose_active:
        print('[VERBOSE-PARSER] Verbose-Modus erkannt - Parse-Modus aktiviert')
        
        # Rekursionsverhinderung
        if os.environ.get('PIO_COMMANDS_PARSED') == '1':
            print('[VERBOSE-PARSER] Kommandos bereits geparst, fahre mit normalem Build fort')
            return True
        
        # Markiere dass wir parsen werden
        os.environ['PIO_COMMANDS_PARSED'] = '1'
        
        print('[VERBOSE-PARSER] Starte Build-Parsing...')
        
        try:
            # Bestimme das PlatformIO-Kommando
            pio_cmd = ['pio', 'run', '-v']
            
            # Versuche aktuelles Environment zu ermitteln
            try:
                current_env = env.get('PIOENV')
                if current_env:
                    pio_cmd.extend(['-e', current_env])
            except:
                pass
            
            print(f'[VERBOSE-PARSER] Führe aus: {" ".join(pio_cmd)}')
            
            # Führe PlatformIO mit Verbose aus
            result = subprocess.run(
                pio_cmd, 
                cwd=os.getcwd(), 
                capture_output=True, 
                text=True
            )
            
            full_output = result.stdout + result.stderr
            
            # Parse die Kommandos
            compile_cmds, link_cmds, archive_cmds = parse_verbose_output(full_output)
            
            # Speichere Ergebnisse
            save_parsed_commands(compile_cmds, link_cmds, archive_cmds, full_output)
            
            print('[VERBOSE-PARSER] Parsing abgeschlossen, beende Script')
            sys.exit(result.returncode)
            
        except Exception as e:
            print(f'[VERBOSE-PARSER] Fehler beim Parsing: {e}')
            return False
    
    else:
        print('[VERBOSE-PARSER] Kein Verbose-Modus, starte PlatformIO neu mit -v')
        
        # Rekursionsverhinderung
        if os.environ.get('PIO_VERBOSE_RESTART') == '1':
            print('[VERBOSE-PARSER] Rekursion erkannt, Abbruch')
            sys.exit(1)
        
        # Markiere Neustart
        os.environ['PIO_VERBOSE_RESTART'] = '1'
        
        try:
            # Starte PlatformIO mit Verbose-Modus
            pio_cmd = ['pio', 'run', '-v']
            
            # Versuche aktuelles Environment hinzuzufügen
            try:
                current_env = env.get('PIOENV')
                if current_env:
                    pio_cmd.extend(['-e', current_env])
            except:
                pass
            
            print(f'[VERBOSE-PARSER] Starte PlatformIO neu: {" ".join(pio_cmd)}')
            
            result = subprocess.run(pio_cmd, cwd=os.getcwd())
            sys.exit(result.returncode)
            
        except Exception as e:
            print(f'[VERBOSE-PARSER] Fehler beim Neustart: {e}')
            sys.exit(1)

# Für PlatformIO extra_scripts
if 'env' in globals():
    pre_script_verbose_parser(env)
else:
    print('[VERBOSE-PARSER] Kein PlatformIO Environment gefunden')
