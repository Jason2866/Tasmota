import os
import sys
import subprocess
import re
import json
from datetime import datetime

Import("env")

def find_platformio_executable():
    """Findet den korrekten PlatformIO-Pfad"""
    
    # Mögliche PlatformIO-Pfade
    possible_paths = [
        'pio',
        'platformio', 
        '~/.platformio/penv/bin/pio',
        '~/.platformio/penv/Scripts/pio.exe',
        sys.executable + ' -m platformio',
        'python -m platformio',
        'python3 -m platformio'
    ]
    
    for path in possible_paths:
        try:
            if path.startswith('python'):
                # Teste Python-Modul Aufruf
                result = subprocess.run(
                    path.split() + ['--version'], 
                    capture_output=True, 
                    text=True, 
                    timeout=10
                )
                if result.returncode == 0:
                    return path.split()
            else:
                # Teste direkten Aufruf
                expanded_path = os.path.expanduser(path)
                result = subprocess.run(
                    [expanded_path, '--version'], 
                    capture_output=True, 
                    text=True, 
                    timeout=10
                )
                if result.returncode == 0:
                    return [expanded_path]
        except:
            continue
    
    return None

def run_platformio_verbose():
    """Führt PlatformIO mit Verbose-Modus aus"""
    
    # Finde PlatformIO
    pio_cmd = find_platformio_executable()
    if not pio_cmd:
        return "FEHLER: PlatformIO CLI nicht gefunden"
    
    print(f"[VERBOSE-PARSER] Verwende PlatformIO: {' '.join(pio_cmd)}")
    
    try:
        # Führe PlatformIO run -v aus
        cmd = pio_cmd + ['run', '-v']
        
        print(f"[VERBOSE-PARSER] Führe aus: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=300  # 5 Minuten Timeout
        )
        
        full_output = result.stdout + result.stderr
        
        print(f"[VERBOSE-PARSER] Return Code: {result.returncode}")
        print(f"[VERBOSE-PARSER] Output Length: {len(full_output)} Zeichen")
        
        return full_output, result.returncode
        
    except subprocess.TimeoutExpired:
        return "FEHLER: PlatformIO Timeout", 1
    except Exception as e:
        return f"FEHLER: {str(e)}", 1

def parse_verbose_output(output):
    """Parst den Verbose-Output"""
    
    compile_commands = []
    link_commands = []
    archive_commands = []
    
    # Verbesserte Regex-Patterns
    compile_patterns = [
        r'.*?(?:g\+\+|gcc|clang\+\+|clang).*?-c.*?\.(?:cpp|c|cc|cxx).*?-o.*?\.o',
        r'.*?xtensa-esp32.*?-c.*?-o.*?\.o',
        r'.*?riscv32.*?-c.*?-o.*?\.o',
        r'.*?arm-none-eabi.*?-c.*?-o.*?\.o'
    ]
    
    for pattern in compile_patterns:
        matches = re.findall(pattern, output, re.MULTILINE | re.IGNORECASE)
        compile_commands.extend([cmd.strip() for cmd in matches])
    
    # Link-Kommandos
    link_patterns = [
        r'.*?(?:g\+\+|gcc|ld).*?\.o.*?-o.*?\.elf',
        r'.*?xtensa-esp32.*?\.o.*?-o.*?\.elf',
        r'.*?riscv32.*?\.o.*?-o.*?\.elf',
        r'.*?arm-none-eabi.*?\.o.*?-o.*?\.elf'
    ]
    
    for pattern in link_patterns:
        matches = re.findall(pattern, output, re.MULTILINE | re.IGNORECASE)
        link_commands.extend([cmd.strip() for cmd in matches])
    
    # Archive-Kommandos
    archive_patterns = [
        r'.*?ar.*?rcs.*?\.a.*?\.o',
        r'.*?xtensa-esp32.*?ar.*?\.a',
        r'.*?arm-none-eabi-ar.*?\.a'
    ]
    
    for pattern in archive_patterns:
        matches = re.findall(pattern, output, re.MULTILINE | re.IGNORECASE)
        archive_commands.extend([cmd.strip() for cmd in matches])
    
    return compile_commands, link_commands, archive_commands

def save_parsed_commands(compile_cmds, link_cmds, archive_cmds, full_output):
    """Speichert alle geparsten Kommandos"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Shell-Script
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
    
    # JSON
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
    """Hauptfunktion für Pre-Script"""
    
    # Rekursionsverhinderung
    if os.environ.get('PIO_COMMANDS_PARSED') == '1':
        print('[VERBOSE-PARSER] Bereits geparst, fahre fort')
        return True
    
    print('[VERBOSE-PARSER] Starte PlatformIO Verbose-Parsing...')
    
    # Markiere dass wir parsen
    os.environ['PIO_COMMANDS_PARSED'] = '1'
    
    # Führe PlatformIO aus
    output, returncode = run_platformio_verbose()
    
    if returncode != 0:
        print(f'[VERBOSE-PARSER] PlatformIO fehlgeschlagen: {output}')
        return False
    
    # Parse Kommandos
    compile_cmds, link_cmds, archive_cmds = parse_verbose_output(output)
    
    # Speichere Ergebnisse
    save_parsed_commands(compile_cmds, link_cmds, archive_cmds, output)
    
    print('[VERBOSE-PARSER] Parsing abgeschlossen')
    sys.exit(returncode)

# Für PlatformIO extra_scripts
if 'env' in globals():
    pre_script_verbose_parser(env)
else:
    print('[VERBOSE-PARSER] Standalone-Ausführung')
    # Für direkten Test
    output, code = run_platformio_verbose()
    if code == 0:
        compile_cmds, link_cmds, archive_cmds = parse_verbose_output(output)
        save_parsed_commands(compile_cmds, link_cmds, archive_cmds, output)
