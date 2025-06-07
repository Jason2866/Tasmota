import time
from datetime import datetime

Import("env")

class ActionWrapperTiming:
    def __init__(self, env):
        self.start_time = time.time()
        self.env = env
        self.log_timing("SCRIPT_START")
        
        # Sofort Wrapper installieren
        self.install_wrappers()
        
    def log_timing(self, event):
        elapsed = time.time() - self.start_time
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[TIMING] {timestamp} (+{elapsed:.3f}s) {event}")
        
    def install_wrappers(self):
        self.log_timing("WRAPPER_INSTALL_START")
        
        # Original Actions sichern
        self.original_object_action = self.env['BUILDERS']['Object'].action
        
        # Wrapper erstellen
        from SCons.Action import Action
        
        def compile_wrapper(target, source, env):
            self.log_timing(f"COMPILE_START: {source[0]}")
            
            # Vollständiges Kommando erfassen
            if hasattr(self.original_object_action, 'genstring'):
                full_cmd = self.original_object_action.genstring(target, source, env)
                self.log_complete_command(target, source, full_cmd)
            
            # Original ausführen
            result = self.original_object_action(target, source, env)
            
            self.log_timing(f"COMPILE_END: {source[0]}")
            return result
        
        # Wrapper installieren
        self.env['BUILDERS']['Object'].action = Action(compile_wrapper)
        self.log_timing("WRAPPER_INSTALL_COMPLETE")
    
    def log_complete_command(self, target, source, command):
        with open("complete_commands.log", "a") as f:
            f.write(f"# {datetime.now()}\n")
            f.write(f"# {source[0]} -> {target[0]}\n")
            f.write(f"{command}\n\n")

# SOFORT starten
wrapper_timing = ActionWrapperTiming(env)

# Normale Hooks (kommen nach Wrapper)
def normal_hook(target, source, env):
    wrapper_timing.log_timing("NORMAL_HOOK")

env.AddPreAction("*.o", normal_hook)

wrapper_timing.log_timing("SCRIPT_END")
