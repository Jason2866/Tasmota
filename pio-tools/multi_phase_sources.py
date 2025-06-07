# multi_phase_sources.py
Import("env")

build_phases = {}

def capture_sources_phase(phase_name):
    """Erfasst Sources zu verschiedenen Zeitpunkten"""
    def capture(source, target, env):
        sources = env.get("SOURCES", [])
        build_phases[phase_name] = {
            'timestamp': datetime.datetime.now().isoformat(),
            'count': len(sources),
            'sources': [str(s) for s in sources]
        }
        print(f"[{phase_name}] {len(sources)} Sources erfasst")
    return capture

def save_all_phases(source, target, env):
    """Speichert alle erfassten Phasen"""
    import json
    import datetime
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    with open(f"build_phases_{timestamp}.json", 'w') as f:
        json.dump(build_phases, f, indent=2)
    
    print(f"Build-Phasen gespeichert: build_phases_{timestamp}.json")

# Verschiedene Phasen erfassen
env.AddPreAction("buildprog", capture_sources_phase("PRE_BUILD"))
env.AddPostAction("$BUILD_DIR/${PROGNAME}.elf", capture_sources_phase("POST_COMPILE"))
env.AddPostAction("buildprog", capture_sources_phase("POST_BUILD"))
env.AddPostAction("buildprog", save_all_phases)
