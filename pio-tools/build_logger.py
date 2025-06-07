import os
import json
import time
from datetime import datetime
import hashlib

class BuildLogger:
    def __init__(self, log_dir="build_logs"):
        self.log_dir = log_dir
        self.session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        self.ensure_log_dir()
        
    def ensure_log_dir(self):
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
    
    def get_timestamp(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def log_build_phase(self, phase, target, source, env):
        timestamp = self.get_timestamp()
        
        # Basis-Informationen sammeln
        build_info = {
            'timestamp': timestamp,
            'session_id': self.session_id,
            'phase': phase,
            'target': str(target[0]) if target else None,
            'source_files': [str(s) for s in source] if source else [],
            'source_count': len(source) if source else 0,
            'platform_info': {
                'platform': env.get('PIOPLATFORM', 'unknown'),
                'framework': env.get('PIOFRAMEWORK', []),
                'board': env.get('BOARD', 'unknown'),
                'build_type': env.get('BUILD_TYPE', 'release')
            },
            'compiler_info': {
                'cc': env.get('CC', 'unknown'),
                'cxx': env.get('CXX', 'unknown'),
                'ar': env.get('AR', 'unknown'),
                'ld': env.get('LINK', 'unknown')
            },
            'build_flags': {
                'cppflags': env.get('CPPFLAGS', []),
                'cxxflags': env.get('CXXFLAGS', []),
                'ccflags': env.get('CCFLAGS', []),
                'linkflags': env.get('LINKFLAGS', []),
                'build_flags': env.get('BUILD_FLAGS', [])
            },
            'paths': {
                'cpppath': env.get('CPPPATH', []),
                'libpath': env.get('LIBPATH', []),
                'build_dir': str(env.get('BUILD_DIR', '')),
                'project_dir': str(env.get('PROJECT_DIR', ''))
            },
            'defines_and_libs': {
                'cppdefines': env.get('CPPDEFINES', []),
                'libs': env.get('LIBS', [])
            }
        }
        
        # Kommandos erfassen
        commands = {}
        for cmd_type in ['CXXCOM', 'CCCOM', 'LINKCOM', 'ARCOM', 'ASCOM']:
            template = env.get(cmd_type)
            if template:
                try:
                    resolved = env.subst(template, target=target, source=source)
                    commands[cmd_type] = {
                        'template': str(template),
                        'resolved': resolved,
                        'length': len(resolved)
                    }
                except Exception as e:
                    commands[cmd_type] = {
                        'template': str(template),
                        'error': str(e)
                    }
        
        build_info['commands'] = commands
        
        # In verschiedene Dateien schreiben
        self.write_json_log(phase, build_info)
        self.write_readable_log(phase, build_info)
        self.write_commands_only(phase, build_info)
        
        # Konsolen-Output
        print(f"\n[BUILD-LOG] {timestamp} - {phase} - {build_info['target']}")
        
    def write_json_log(self, phase, build_info):
        """Vollständige Informationen als JSON"""
        filename = f"{self.log_dir}/build_{self.session_id}_{phase}.json"
        
        # Bestehende Daten laden oder neue Liste erstellen
        data = []
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except:
                data = []
        
        data.append(build_info)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def write_readable_log(self, phase, build_info):
        """Lesbare Textdatei"""
        filename = f"{self.log_dir}/build_{self.session_id}_{phase}.txt"
        
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"BUILD PHASE: {phase}\n")
            f.write(f"TIMESTAMP: {build_info['timestamp']}\n")
            f.write(f"TARGET: {build_info['target']}\n")
            f.write(f"SOURCE COUNT: {build_info['source_count']}\n")
            f.write(f"{'='*80}\n")
            
            # Platform Info
            f.write(f"\nPLATFORM INFO:\n")
            for key, value in build_info['platform_info'].items():
                f.write(f"  {key}: {value}\n")
            
            # Compiler Info
            f.write(f"\nCOMPILER INFO:\n")
            for key, value in build_info['compiler_info'].items():
                f.write(f"  {key}: {value}\n")
            
            # Commands
            f.write(f"\nCOMMANDS:\n")
            for cmd_type, cmd_info in build_info['commands'].items():
                f.write(f"\n  {cmd_type}:\n")
                if 'resolved' in cmd_info:
                    f.write(f"    Template: {cmd_info['template']}\n")
                    f.write(f"    Resolved: {cmd_info['resolved']}\n")
                    f.write(f"    Length: {cmd_info['length']} chars\n")
                else:
                    f.write(f"    Error: {cmd_info.get('error', 'Unknown')}\n")
            
            # Build Flags
            f.write(f"\nBUILD FLAGS:\n")
            for flag_type, flags in build_info['build_flags'].items():
                if flags:
                    f.write(f"  {flag_type}: {flags}\n")
            
            f.write(f"\n{'-'*80}\n")
    
    def write_commands_only(self, phase, build_info):
        """Nur die aufgelösten Kommandos"""
        filename = f"{self.log_dir}/commands_{self.session_id}_{phase}.sh"
        
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(f"\n# {build_info['timestamp']} - {phase} - {build_info['target']}\n")
            
            for cmd_type, cmd_info in build_info['commands'].items():
                if 'resolved' in cmd_info:
                    f.write(f"# {cmd_type}\n")
                    f.write(f"{cmd_info['resolved']}\n\n")
    
    def write_summary(self, env):
        """Build-Summary am Ende"""
        summary_file = f"{self.log_dir}/build_summary_{self.session_id}.txt"
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(f"BUILD SUMMARY\n")
            f.write(f"Session ID: {self.session_id}\n")
            f.write(f"Timestamp: {self.get_timestamp()}\n")
            f.write(f"Project: {env.get('PROJECT_DIR', 'unknown')}\n")
            f.write(f"Platform: {env.get('PIOPLATFORM', 'unknown')}\n")
            f.write(f"Board: {env.get('BOARD', 'unknown')}\n")
            f.write(f"Framework: {env.get('PIOFRAMEWORK', [])}\n")
            
            # Log-Dateien auflisten
            f.write(f"\nGenerated Log Files:\n")
            for file in os.listdir(self.log_dir):
                if self.session_id in file:
                    f.write(f"  - {file}\n")

# Globale Logger-Instanz
build_logger = BuildLogger()

def log_compile_phase(target, source, env):
    build_logger.log_build_phase("COMPILE", target, source, env)

def log_link_phase(target, source, env):
    build_logger.log_build_phase("LINK", target, source, env)

def log_archive_phase(target, source, env):
    build_logger.log_build_phase("ARCHIVE", target, source, env)

def log_build_complete(target, source, env):
    build_logger.log_build_phase("COMPLETE", target, source, env)
    build_logger.write_summary(env)

# Build-Hooks registrieren
env.AddPreAction("*.o", log_compile_phase)      # Compile-Phase
env.AddPreAction("*.a", log_archive_phase)      # Archive-Phase  
env.AddPreAction("$BUILD_DIR/${PROGNAME}.elf", log_link_phase)  # Link-Phase

# Post-Build Hook
env.AddPostAction("$BUILD_DIR/${PROGNAME}.elf", log_build_complete)

print(f"[BUILD-LOGGER] Initialisiert - Session: {build_logger.session_id}")
print(f"[BUILD-LOGGER] Log-Verzeichnis: {build_logger.log_dir}")
