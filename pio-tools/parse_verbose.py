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
    print(f"\nDateien erstellt:")
    print(f"  - build_commands_{timestamp}.sh")
    print(f"  - build_commands_{timestamp}.json")
    print(f"  - pio_verbose_output_{timestamp}.log")

def pre_script_verbose_parser(env):
    """Pre-Script das Verbose-Modus erzwingt und Output parst"""
    
    # Prüfen ob wir bereits im Verbose-Modus sind
    verbose_flag = env.GetProjectOption('verbose', False)
    
    if verbose_flag:
        print('[VERBOSE-PARSER] Verbose-Modus erkannt - Parse-Modus aktiviert')
        
        # Prüfen ob wir bereits geparst haben (Rekursionsverhinderung)
        if os.environ.get('PIO_COMMANDS_PARSED') == '1':
            print('[VERBOSE-PARSER] Kommandos bereits geparst, fahre mit normalem Build fort')
            return True
        
        # Markiere dass wir parsen werden
        os.environ['PIO_COMMANDS_PARSED'] = '1'
        
        print('[VERBOSE-PARSER] Starte Build-Parsing...')
        
        # Aktuelles PlatformIO-Kommando mit Verbose ausführen und Output erfassen
        try:
            cwd = os.getcwd()
            
            # Bestimme das ursprüngliche Kommando
            original_args = sys.argv[:]
            if 'pio' not in original_args[0]:
                # Wir sind in einem SCons-Kontext, verwende pio run
                cmd = ['pio', 'run', '-v']
            else:
                # Erweitere bestehende Argumente um -v
                cmd = original_args[:]
                if '-v' not in cmd:
                    cmd.append('-v')
            
            print(f'[VERBOSE-PARSER] Führe aus: {" ".join(cmd)}')
            
            # Führe Kommando aus und erfasse Output
            result = subprocess.run(
                cmd, 
                cwd=cwd, 
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
        print('[VERBOSE-PARSER] Kein Verbose-Modus, starte neu mit -v')
        
        # Rekursionsverhinderung
        if os.environ.get('PIO_VERBOSE_RESTART') == '1':
            print('[VERBOSE-PARSER] Rekursion erkannt, Abbruch')
            sys.exit(1)
        
        # Markiere Neustart
        os.environ['PIO_VERBOSE_RESTART'] = '1'
        
        try:
            cwd = os.getcwd()
            
            # Bestimme Neustart-Kommando
            if len(sys.argv) > 1:
                # Erweitere bestehende Argumente
                cmd = sys.argv[:]
                if '-v' not in cmd:
                    cmd.append('-v')
            else:
                # Standard pio run mit verbose
                cmd = ['pio', 'run', '-v']
            
            print(f'[VERBOSE-PARSER] Starte neu: {" ".join(cmd)}')
            
            result = subprocess.run(cmd, cwd=cwd)
            sys.exit(result.returncode)
            
        except Exception as e:
            print(f'[VERBOSE-PARSER] Fehler beim Neustart: {e}')
            sys.exit(1)

# Für PlatformIO extra_scripts
if 'env' in globals():
    pre_script_verbose_parser(env)
else:
    print('[VERBOSE-PARSER] Kein PlatformIO Environment gefunden')
