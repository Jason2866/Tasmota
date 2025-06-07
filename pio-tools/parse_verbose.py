import os
import sys
import subprocess
import re
import json
from datetime import datetime

Import("env")

def create_bypass_script():
    """Erstellt ein temporäres Script das den Parser umgeht"""
    
    bypass_script = """
import os
import sys

# Verhindere Parser-Ausführung
os.environ['PIO_COMMANDS_PARSED'] = '1'
os.environ['PIO_PARSER_BYPASS'] = '1'

# Führe normalen Build aus
print("[BYPASS] Parser umgangen, normaler Build")
"""
    
    with open("bypass_parser.py", "w") as f:
        f.write(bypass_script)
    
    return "bypass_parser.py"

def run_platformio_with_bypass():
    """Führt PlatformIO mit Parser-Bypass aus"""
    
    # Erstelle Bypass-Script
    bypass_file = create_bypass_script()
    
    try:
        # Temporäre platformio.ini mit Bypass erstellen
        original_ini = "platformio.ini"
        backup_ini = "platformio.ini.backup"
        temp_ini = "platformio_temp.ini"
        
        # Backup der Original-INI
        if os.path.exists(original_ini):
            with open(original_ini, 'r') as f:
                original_content = f.read()
            
            with open(backup_ini, 'w') as f:
                f.write(original_content)
            
            # Modifizierte INI erstellen (ohne Pre-Script)
            modified_content = re.sub(
                r'extra_scripts\s*=\s*pre:.*\.py', 
                f'extra_scripts = pre:{bypass_file}', 
                original_content
            )
            
            with open(temp_ini, 'w') as f:
                f.write(modified_content)
        
        # PlatformIO mit temporärer Konfiguration ausführen
        cmd = [sys.executable, '-m', 'platformio', 'run', '-v', '-c', temp_ini]
        
        print(f"[VERBOSE-PARSER] Führe aus: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=300
        )
        
        return result.stdout + result.stderr, result.returncode
        
    except Exception as e:
        print(f"[VERBOSE-PARSER] Fehler: {e}")
        return str(e), 1
    
    finally:
        # Cleanup
        for temp_file in [bypass_file, temp_ini]:
            if os.path.exists(temp_file):
                os.remove(temp_file)

def parse_verbose_output(output):
    """Parst Verbose-Output"""
    
    compile_commands = []
    link_commands = []
    
    # Compile-Kommandos
    compile_patterns = [
        r'.*?(?:g\+\+|gcc|clang).*?-c.*?\.(?:cpp|c|cc).*?-o.*?\.o',
        r'.*?xtensa-esp32.*?-c.*?-o.*?\.o'
    ]
    
    for pattern in compile_patterns:
        matches = re.findall(pattern, output, re.MULTILINE)
        compile_commands.extend([cmd.strip() for cmd in matches])
    
    # Link-Kommandos  
    link_patterns = [
        r'.*?(?:g\+\+|gcc).*?\.o.*?-o.*?\.elf',
        r'.*?xtensa-esp32.*?\.o.*?-o.*?\.elf'
    ]
    
    for pattern in link_patterns:
        matches = re.findall(pattern, output, re.MULTILINE)
        link_commands.extend([cmd.strip() for cmd in matches])
    
    return compile_commands, link_commands

def save_commands(compile_cmds, link_cmds, full_output):
    """Speichert extrahierte Kommandos"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Shell-Script
    with open(f"build_commands_{timestamp}.sh", "w") as f:
        f.write("#!/bin/bash\n\n")
        f.write("# COMPILE COMMANDS\n")
        for cmd in compile_cmds:
            f.write(f"{cmd}\n")
        f.write("\n# LINK COMMANDS\n")
        for cmd in link_cmds:
            f.write(f"{cmd}\n")
    
    # Vollständiger Output
    with open(f"verbose_output_{timestamp}.log", "w") as f:
        f.write(full_output)
    
    print(f"\n=== KOMMANDOS EXTRAHIERT ===")
    print(f"Compile: {len(compile_cmds)}")
    print(f"Link: {len(link_cmds)}")
    print(f"Dateien: build_commands_{timestamp}.sh, verbose_output_{timestamp}.log")

def pre_script_parser(env):
    """Hauptfunktion - verhindert Deadlock"""
    
    # Prüfe ob wir im Bypass-Modus sind
    if os.environ.get('PIO_PARSER_BYPASS') == '1':
        print('[BYPASS] Parser übersprungen')
        return True
    
    # Prüfe Rekursion
    if os.environ.get('PIO_COMMANDS_PARSED') == '1':
        print('[VERBOSE-PARSER] Bereits verarbeitet')
        return True
    
    print('[VERBOSE-PARSER] Starte Kommando-Extraktion...')
    
    # Markiere als verarbeitet
    os.environ['PIO_COMMANDS_PARSED'] = '1'
    
    # Führe PlatformIO mit Bypass aus
    output, returncode = run_platformio_with_bypass()
    
    if returncode == 0:
        # Parse und speichere Kommandos
        compile_cmds, link_cmds = parse_verbose_output(output)
        save_commands(compile_cmds, link_cmds, output)
        print('[VERBOSE-PARSER] Erfolgreich abgeschlossen')
    else:
        print(f'[VERBOSE-PARSER] Fehler: Return Code {returncode}')
    
    # Beende das Script hier - nicht den gesamten Build
    sys.exit(0)

# Für PlatformIO extra_scripts
if 'env' in globals():
    pre_script_parser(env)
