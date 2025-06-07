Import("env")

def analyze_linkcom(target, source, env):
    """Analysiert LINKCOM und extrahiert alle Objekt-Dateien"""
    
    linkcom_template = env.get('LINKCOM')
    if linkcom_template:
        # LINKCOM auflösen
        resolved_linkcom = env.subst(linkcom_template, target=target, source=source)
        
        print(f"\n{'='*80}")
        print(f"LINKCOM ANALYSE")
        print(f"{'='*80}")
        print(f"Template: {linkcom_template}")
        print(f"Aufgelöst: {resolved_linkcom}")
        
        # Objekt-Dateien extrahieren
        import re
        object_files = re.findall(r'\S+\.o(?:bj)?', resolved_linkcom)
        
        print(f"\nGefundene Objekt-Dateien ({len(object_files)}):")
        for i, obj_file in enumerate(object_files):
            print(f"  {i+1:3d}: {obj_file}")
        
        # In Datei schreiben
        with open("linkcom_analysis.log", "a") as f:
            f.write(f"\n# {datetime.now()}\n")
            f.write(f"# Target: {target}\n")
            f.write(f"LINKCOM: {resolved_linkcom}\n")
            f.write(f"Object-Files: {object_files}\n\n")
        
        return object_files

# Hook für Link-Phase
env.AddPreAction("$BUILD_DIR/${PROGNAME}.elf", analyze_linkcom)
