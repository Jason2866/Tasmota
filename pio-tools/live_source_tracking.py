# live_source_tracking.py
Import("env")

source_timeline = []

def track_source_changes():
    """Überwacht Änderungen in der Source-Liste"""
    current_sources = env.get("SOURCES", [])
    
    if not hasattr(track_source_changes, 'last_sources'):
        track_source_changes.last_sources = []
    
    if current_sources != track_source_changes.last_sources:
        import datetime
        source_timeline.append({
            'timestamp': datetime.datetime.now().isoformat(),
            'added': list(set(current_sources) - set(track_source_changes.last_sources)),
            'removed': list(set(track_source_changes.last_sources) - set(current_sources)),
            'total_count': len(current_sources)
        })
        track_source_changes.last_sources = current_sources.copy()

def save_source_timeline(source, target, env):
    """Speichert die Source-Timeline"""
    if source_timeline:
        import json
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        with open(f"source_timeline_{timestamp}.json", 'w') as f:
            json.dump(source_timeline, f, indent=2, default=str)
        
        print(f"Source-Timeline gespeichert: source_timeline_{timestamp}.json")

# Regelmäßiges Tracking (experimentell)
env.AddPreAction("buildprog", lambda s, t, e: track_source_changes())
env.AddPostAction("buildprog", save_source_timeline)
