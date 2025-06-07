Import("env")

def analyze_linkcom_variables(target, source, env):
    """Analysiert alle LINKCOM-relevanten Variablen"""
    
    print(f"\n[LINKCOM] Variablen-Analyse:")
    
    # Wichtige Link-Variablen
    link_vars = {
        'LINKCOM': env.get('LINKCOM'),
        'SOURCES': env.get('SOURCES'),
        '_LIBFLAGS': env.get('_LIBFLAGS'),
        '_LIBDIRFLAGS': env.get('_LIBDIRFLAGS'),
        'LIBS': env.get('LIBS'),
        'LIBPATH': env.get('LIBPATH'),
        'LINKFLAGS': env.get('LINKFLAGS')
    }
    
    for var_name, var_value in link_vars.items():
        if var_value:
            resolved = env.subst(str(var_value), target=target, source=source)
            print(f"  {var_name}: {resolved}")
    
    # $SOURCES speziell analysieren
    sources_resolved = env.subst('$SOURCES', target=target, source=source)
    print(f"\n[SOURCES] Aufgelöst: {sources_resolved}")
    
    # Alle Objekt-Dateien aus verschiedenen Quellen
    all_objects = []
    
    # Aus SOURCES
    import re
    objects_from_sources = re.findall(r'\S+\.o(?:bj)?', sources_resolved)
    all_objects.extend(objects_from_sources)
    
    # Aus LINKCOM
    linkcom_resolved = env.subst(env.get('LINKCOM', ''), target=target, source=source)
    objects_from_linkcom = re.findall(r'\S+\.o(?:bj)?', linkcom_resolved)
    
    print(f"\nObjekt-Dateien Vergleich:")
    print(f"  Aus $SOURCES: {len(objects_from_sources)} Dateien")
    print(f"  Aus LINKCOM: {len(objects_from_linkcom)} Dateien")
    
    return {
        'sources_objects': objects_from_sources,
        'linkcom_objects': objects_from_linkcom,
        'linkcom_full': linkcom_resolved
    }

env.AddPreAction("$BUILD_DIR/${PROGNAME}.elf", analyze_linkcom_variables)
