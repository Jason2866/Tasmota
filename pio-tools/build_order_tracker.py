Import("env")

class BuildOrderTracker:
    def __init__(self):
        self.compile_order = []
        self.link_objects = []
        self.session_id = int(time.time())
    
    def track_compile(self, target, source, env):
        """Verfolgt Kompilier-Reihenfolge"""
        if source and target:
            source_file = str(source[0])
            target_file = str(target[0])
            
            compile_info = {
                'timestamp': time.time(),
                'source': source_file,
                'target': target_file,
                'order': len(self.compile_order) + 1
            }
            
            self.compile_order.append(compile_info)
            print(f"[COMPILE] #{compile_info['order']:3d}: {source_file} -> {target_file}")
    
    def track_link(self, target, source, env):
        """Analysiert Link-Kommando und Objekt-Reihenfolge"""
        linkcom = env.get('LINKCOM', '')
        resolved = env.subst(linkcom, target=target, source=source)
        
        # Objekt-Dateien aus LINKCOM extrahieren
        import re
        objects_in_linkcom = re.findall(r'\S+\.o(?:bj)?', resolved)
        
        self.link_objects = objects_in_linkcom
        
        print(f"\n[LINK] Objekt-Dateien in LINKCOM-Reihenfolge:")
        for i, obj in enumerate(objects_in_linkcom):
            print(f"  {i+1:3d}: {obj}")
        
        # Vergleich: Kompilier- vs Link-Reihenfolge
        self.compare_orders()
        self.write_complete_log()
    
    def compare_orders(self):
        """Vergleicht Kompilier- und Link-Reihenfolge"""
        print(f"\n[COMPARE] Reihenfolgen-Vergleich:")
        
        # Kompilierte Objekte (in Kompilier-Reihenfolge)
        compiled_objects = [info['target'] for info in self.compile_order]
        
        print(f"Kompilier-Reihenfolge ({len(compiled_objects)}):")
        for i, obj in enumerate(compiled_objects):
            print(f"  {i+1:3d}: {obj}")
        
        print(f"Link-Reihenfolge ({len(self.link_objects)}):")
        for i, obj in enumerate(self.link_objects):
            print(f"  {i+1:3d}: {obj}")
        
        # Unterschiede finden
        if set(compiled_objects) != set(self.link_objects):
            print(f"[WARNING] Objekt-Listen unterscheiden sich!")
            only_compiled = set(compiled_objects) - set(self.link_objects)
            only_linked = set(self.link_objects) - set(compiled_objects)
            
            if only_compiled:
                print(f"  Nur kompiliert: {only_compiled}")
            if only_linked:
                print(f"  Nur gelinkt: {only_linked}")
    
    def write_complete_log(self):
        """Schreibt vollständiges Log"""
        log_file = f"build_order_{self.session_id}.log"
        
        with open(log_file, "w") as f:
            f.write(f"BUILD ORDER ANALYSIS\n")
            f.write(f"Session: {self.session_id}\n")
            f.write(f"Timestamp: {datetime.now()}\n\n")
            
            f.write(f"COMPILE ORDER ({len(self.compile_order)} files):\n")
            for info in self.compile_order:
                f.write(f"  {info['order']:3d}: {info['source']} -> {info['target']}\n")
            
            f.write(f"\nLINK ORDER ({len(self.link_objects)} objects):\n")
            for i, obj in enumerate(self.link_objects):
                f.write(f"  {i+1:3d}: {obj}\n")
            
            # Mapping: Source -> Object
            f.write(f"\nSOURCE TO OBJECT MAPPING:\n")
            for info in self.compile_order:
                f.write(f"  {info['source']} -> {info['target']}\n")

# Globaler Tracker
build_tracker = BuildOrderTracker()

# Hooks registrieren
env.AddPreAction("*.o", build_tracker.track_compile)
env.AddPreAction("$BUILD_DIR/${PROGNAME}.elf", build_tracker.track_link)
