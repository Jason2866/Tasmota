import os
import pickle
import time
from datetime import datetime
import hashlib

Import("env")

class SConsCompatibleLogger:
    def __init__(self, log_dir="build_logs"):
        self.log_dir = log_dir
        self.session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        self.ensure_log_dir()
        
    def ensure_log_dir(self):
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
    
    def get_timestamp(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def serialize_scons_object(self, obj):
        """Konvertiert SCons-Objekte in serialisierbare Formate"""
        if hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes)):
            try:
                # Listen und Tupel
                return [self.serialize_scons_object(item) for item in obj]
            except:
                return str(obj)
        elif hasattr(obj, '__dict__'):
            # Objekte mit Attributen
            try:
                return {
                    '_type': type(obj).__name__,
                    '_str': str(obj),
                    'attributes': {k: self.serialize_scons_object(v) 
                                 for k, v in obj.__dict__.items() 
                                 if not k.startswith('_')}
                }
            except:
                return str(obj)
        else:
            # Primitive Typen oder nicht serialisierbare Objekte
            try:
                # Test ob JSON-serialisierbar
                import json
                json.dumps(obj)
                return obj
            except:
                return str(obj)
    
    def extract_env_data(self, env):
        """Extrahiert relevante Daten aus SCons Environment"""
        safe_data = {}
        
        # Wichtige Keys die wir extrahieren wollen
        important_keys = [
            'CC', 'CXX', 'AR', 'LINK', 'AS',
            'CPPFLAGS', 'CXXFLAGS', 'CCFLAGS', 'LINKFLAGS', 'ASFLAGS',
            'CPPPATH', 'LIBPATH', 'LIBS', 'CPPDEFINES',
            'BUILD_FLAGS', 'BUILD_DIR', 'PROJECT_DIR',
            'PIOPLATFORM', 'PIOFRAMEWORK', 'BOARD', 'BUILD_TYPE',
            'CXXCOM', 'CCCOM', 'LINKCOM', 'ARCOM', 'ASCOM'
        ]
        
        for key in important_keys:
            try:
                value = env.get(key)
                if value is not None:
                    safe_data[key] = self.serialize_scons_object(value)
            except Exception as e:
                safe_data[key] = f"ERROR: {str(e)}"
        
        return safe_data
    
    def log_build_phase(self, phase, target, source, env):
        timestamp = self.get_timestamp()
        
        # Sichere Datenextraktion
        build_info = {
            'timestamp': timestamp,
            'session_id': self.session_id,
            'phase': phase,
            'target': self.serialize_scons_object(target),
            'source': self.serialize_scons_object(source),
            'source_count': len(source) if source else 0,
            'env_data': self.extract_env_data(env)
        }
        
        # Kommandos sicher extrahieren
        commands = {}
        for cmd_type in ['CXXCOM', 'CCCOM', 'LINKCOM', 'ARCOM', 'ASCOM']:
            try:
                template = env.get(cmd_type)
                if template:
                    resolved = env.subst(template, target=target, source=source)
                    commands[cmd_type] = {
                        'template': str(template),
                        'resolved': str(resolved),
                        'length': len(str(resolved))
                    }
            except Exception as e:
                commands[cmd_type] = {'error': str(e)}
        
        build_info['commands'] = commands
        
        # In verschiedene Formate schreiben
        self.write_pickle_log(phase, build_info)
        self.write_text_log(phase, build_info)
        self.write_commands_log(phase, build_info)
        
        print(f"[BUILD-LOG] {timestamp} - {phase} - {build_info['target']}")
    
    def write_pickle_log(self, phase, build_info):
        """Vollständige Daten als Pickle (Python-spezifisch aber vollständig)"""
        filename = f"{self.log_dir}/build_{self.session_id}_{phase}.pkl"
        
        data = []
        if os.path.exists(filename):
            try:
                with open(filename, 'rb') as f:
                    data = pickle.load(f)
            except:
                data = []
        
        data.append(build_info)
        
        with open(filename, 'wb') as f:
            pickle.dump(data, f)
    
    def write_text_log(self, phase, build_info):
        """Menschenlesbare Textdatei"""
        filename = f"{self.log_dir}/build_{self.session_id}_{phase}.txt"
        
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"BUILD PHASE: {phase}\n")
            f.write(f"TIMESTAMP: {build_info['timestamp']}\n")
            f.write(f"TARGET: {build_info['target']}\n")
            f.write(f"SOURCE COUNT: {build_info['source_count']}\n")
            f.write(f"{'='*80}\n")
            
            # Environment-Daten
            f.write(f"\nENVIRONMENT DATA:\n")
            for key, value in build_info['env_data'].items():
                if isinstance(value, list) and len(value) > 5:
                    f.write(f"  {key}: [{len(value)} items] {value[:3]}...\n")
                else:
                    f.write(f"  {key}: {value}\n")
            
            # Kommandos
            f.write(f"\nCOMMANDS:\n")
            for cmd_type, cmd_info in build_info['commands'].items():
                f.write(f"\n  {cmd_type}:\n")
                for key, value in cmd_info.items():
                    if key == 'resolved' and len(str(value)) > 200:
                        f.write(f"    {key}: {str(value)[:200]}...\n")
                    else:
                        f.write(f"    {key}: {value}\n")
            
            f.write(f"\n{'-'*80}\n")
    
    def write_commands_log(self, phase, build_info):
        """Nur ausführbare Kommandos"""
        filename = f"{self.log_dir}/commands_{self.session_id}_{phase}.sh"
        
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(f"\n# {build_info['timestamp']} - {phase}\n")
            f.write(f"# Target: {build_info['target']}\n")
            
            for cmd_type, cmd_info in build_info['commands'].items():
                if 'resolved' in cmd_info:
                    f.write(f"\n# {cmd_type}\n")
                    f.write(f"{cmd_info['resolved']}\n")
    
    def write_csv_log(self, phase, build_info):
        """CSV für einfache Analyse"""
        filename = f"{self.log_dir}/build_summary_{self.session_id}.csv"
        
        # Header schreiben wenn Datei nicht existiert
        write_header = not os.path.exists(filename)
        
        with open(filename, 'a', encoding='utf-8') as f:
            if write_header:
                f.write("timestamp,phase,target,source_count,platform,board,framework\n")
            
            env_data = build_info['env_data']
            f.write(f"{build_info['timestamp']},{phase},{build_info['target']},"
                   f"{build_info['source_count']},{env_data.get('PIOPLATFORM', '')},"
                   f"{env_data.get('BOARD', '')},{env_data.get('PIOFRAMEWORK', '')}\n")

# Globale Logger-Instanz
build_logger = SConsCompatibleLogger()

def log_compile_phase(target, source, env):
    build_logger.log_build_phase("COMPILE", target, source, env)

def log_link_phase(target, source, env):
    build_logger.log_build_phase("LINK", target, source, env)

def log_archive_phase(target, source, env):
    build_logger.log_build_phase("ARCHIVE", target, source, env)

def log_build_complete(target, source, env):
    build_logger.log_build_phase("COMPLETE", target, source, env)

# Build-Hooks registrieren
env.AddPreAction("*.o", log_compile_phase)
env.AddPreAction("*.a", log_archive_phase)  
env.AddPreAction("$BUILD_DIR/${PROGNAME}.elf", log_link_phase)
env.AddPostAction("$BUILD_DIR/${PROGNAME}.elf", log_build_complete)

print(f"[BUILD-LOGGER] Initialisiert - Session: {build_logger.session_id}")
print(f"[BUILD-LOGGER] Log-Verzeichnis: {build_logger.log_dir}")
