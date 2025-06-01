Import("env")
import os
import pickle
import gzip
import hashlib
import configparser
import shutil
import glob
import time

def get_cache_file_path():
    """Generiert Pfad zur LDF-Cache-Datei für das aktuelle Environment"""
    env_name = env.get("PIOENV")
    project_dir = env.get("PROJECT_DIR")
    cache_dir = os.path.join(project_dir, ".pio", "ldf_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{env_name}_scons_complete.pkl.gz")

def find_all_platformio_files():
    """Findet alle platformio*.ini Dateien im Projekt"""
    project_dir = env.get("PROJECT_DIR")
    
    ini_patterns = ['platformio.ini', 'platformio_*.ini']
    ini_files = []
    for pattern in ini_patterns:
        found_files = glob.glob(os.path.join(project_dir, pattern))
        ini_files.extend(found_files)
    
    ini_files = list(set(ini_files))
    ini_files.sort()
    return ini_files

def find_env_definition_file(env_name):
    """Findet die Datei, die das spezifische Environment definiert"""
    ini_files = find_all_platformio_files()
    
    for ini_file in ini_files:
        try:
            config = configparser.ConfigParser(allow_no_value=True)
            config.read(ini_file, encoding='utf-8')
            
            section_name = f"env:{env_name}"
            if config.has_section(section_name):
                return ini_file
        except:
            continue
    
    return None

def backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
    """Findet und modifiziert die korrekte platformio*.ini Datei"""
    env_file = find_env_definition_file(env_name)
    
    if not env_file:
        project_dir = env.get("PROJECT_DIR")
        env_file = os.path.join(project_dir, "platformio.ini")
    
    if not os.path.exists(env_file):
        return False
    
    backup_file = f"{env_file}.ldf_backup"
    if not os.path.exists(backup_file):
        shutil.copy2(env_file, backup_file)
        print(f"✓ Backup erstellt: {os.path.basename(backup_file)}")
    
    try:
        config = configparser.ConfigParser(allow_no_value=True)
        config.read(env_file, encoding='utf-8')
        
        section_name = f"env:{env_name}"
        
        if not config.has_section(section_name):
            return False
        
        if set_ldf_off:
            config.set(section_name, "lib_ldf_mode", "off")
            print(f"✓ lib_ldf_mode = off gesetzt in {os.path.basename(env_file)}")
        else:
            if config.has_option(section_name, "lib_ldf_mode"):
                config.remove_option(section_name, "lib_ldf_mode")
                print(f"✓ lib_ldf_mode entfernt aus {os.path.basename(env_file)}")
        
        with open(env_file, 'w', encoding='utf-8') as f:
            config.write(f, space_around_delimiters=True)
        
        return True
        
    except Exception as e:
        print(f"⚠ Fehler beim Modifizieren von {os.path.basename(env_file)}: {e}")
        return False

def get_current_ldf_mode(env_name):
    """Ermittelt aktuellen LDF-Modus aus allen platformio*.ini Dateien"""
    ini_files = find_all_platformio_files()
    merged_config = configparser.ConfigParser(allow_no_value=True)
    
    for ini_file in ini_files:
        try:
            temp_config = configparser.ConfigParser(allow_no_value=True)
            temp_config.read(ini_file, encoding='utf-8')
            
            for section_name in temp_config.sections():
                if not merged_config.has_section(section_name):
                    merged_config.add_section(section_name)
                
                for option, value in temp_config.items(section_name):
                    merged_config.set(section_name, option, value)
        except:
            continue
    
    section_name = f"env:{env_name}"
    if merged_config.has_section(section_name):
        if merged_config.has_option(section_name, 'lib_ldf_mode'):
            return merged_config.get(section_name, 'lib_ldf_mode')
    
    if merged_config.has_section('env'):
        if merged_config.has_option('env', 'lib_ldf_mode'):
            return merged_config.get('env', 'lib_ldf_mode')
    
    return 'chain'

def freeze_exact_scons_configuration():
    """Friert die exakte SCons-Konfiguration nach dem ersten LDF-Durchlauf ein"""
    
    # Komplettes SCons Dictionary erfassen
    scons_dict = env.Dictionary()
    
    # Exakte Kopie aller Variablen erstellen
    frozen_config = {}
    
    for key, value in scons_dict.items():
        try:
            # Tiefe Kopie für Listen und komplexe Strukturen
            if isinstance(value, list):
                frozen_config[key] = value[:]  # Shallow copy für Listen
            elif isinstance(value, dict):
                frozen_config[key] = value.copy()  # Shallow copy für Dicts
            elif hasattr(value, '__dict__'):
                # SCons-Objekte als String-Repräsentation speichern
                frozen_config[key] = str(value)
            else:
                # Primitive Typen direkt kopieren
                frozen_config[key] = value
                
        except Exception as e:
            # Fallback: String-Repräsentation
            frozen_config[key] = str(value)
            print(f"⚠ {key}: Fallback zu String - {e}")
    
    return frozen_config

def restore_exact_scons_configuration(frozen_config):
    """Stellt die exakte SCons-Konfiguration wieder her"""
    
    if not frozen_config:
        return False
    
    restored_count = 0
    
    # Alle Variablen exakt wiederherstellen
    for key, value in frozen_config.items():
        try:
            # Direkte Zuweisung ins SCons Environment
            env[key] = value
            restored_count += 1
            
        except Exception as e:
            print(f"⚠ Wiederherstellung {key} fehlgeschlagen: {e}")
    
    print(f"✓ {restored_count} SCons-Variablen exakt wiederhergestellt")
    return restored_count > 0

def early_cache_check_and_restore():
    """Prüft Cache und stellt SCons-Environment wieder her"""
    print(f"🔍 Cache-Prüfung (EXAKTE SCons-Konfiguration)...")
    
    frozen_config = load_frozen_configuration()
    
    if not frozen_config:
        print(f"📝 Kein SCons-Cache - LDF wird normal ausgeführt")
        return False
    
    current_ldf_mode = get_current_ldf_mode(env.get("PIOENV"))
    
    if current_ldf_mode != 'off':
        print(f"🔄 LDF noch aktiv - SCons-Cache wird nach Build erstellt")
        return False
    
    print(f"⚡ SCons-Cache verfügbar - stelle exakte Konfiguration wieder her")
    
    # EXAKTE SCons-Konfiguration wiederherstellen
    success = restore_exact_scons_configuration(frozen_config)
    
    return success

def verify_frozen_restoration():
    """Verifikation des wiederhergestellten SCons-Environments"""
    print(f"\n🔍 SCons-Environment-Verifikation...")
    
    # Prüfe kritische SCons-Variablen
    critical_scons_vars = [
        "CPPPATH", "CPPDEFINES", "BUILD_FLAGS", "LIBS", 
        "CCFLAGS", "CXXFLAGS", "LINKFLAGS", "PIOBUILDFILES"
    ]
    
    all_ok = True
    for var in critical_scons_vars:
        if var in env and env[var]:
            if var == "CPPPATH":
                paths = env[var]
                print(f"   ✅ {var}: {len(paths)} Include-Pfade")
                
                # Kritische lib/default/headers-Prüfung
                project_dir = env.get("PROJECT_DIR")
                lib_default = os.path.join(project_dir, "lib", "default", "headers")
                found = any(lib_default in str(path) for path in paths)
                
                if found:
                    print(f"      ✅ lib/default/headers: VERFÜGBAR")
                else:
                    print(f"      ❌ lib/default/headers: FEHLT")
                    all_ok = False
                    
            elif hasattr(env[var], '__len__') and not isinstance(env[var], str):
                print(f"   ✅ {var}: {len(env[var])} Einträge")
            else:
                print(f"   ✅ {var}: Vorhanden")
        else:
            print(f"   ❌ {var}: Fehlt")
            all_ok = False
    
    # Zusätzliche SCons-spezifische Prüfungen
    scons_dict_size = len(env.Dictionary())
    print(f"   📊 SCons Dictionary: {scons_dict_size} Variablen")
    
    if all_ok:
        print(f"✅ SCons-Environment vollständig wiederhergestellt")
    else:
        print(f"❌ SCons-Environment UNVOLLSTÄNDIG")
    
    return all_ok

def calculate_config_hash():
    """Berechnet Hash der Konfiguration"""
    relevant_values = [
        f"BOARD:{env.get('BOARD', '')}",
        f"PLATFORM:{env.get('PLATFORM', '')}",
        f"PIOENV:{env.get('PIOENV', '')}"
    ]
    
    ini_files = find_all_platformio_files()
    
    for ini_file in sorted(ini_files):
        if os.path.exists(ini_file) and not ini_file.endswith('.ldf_backup'):
            try:
                with open(ini_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    file_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
                    relevant_values.append(f"{os.path.basename(ini_file)}:{file_hash}")
            except:
                pass
    
    relevant_values.sort()
    config_string = "|".join(relevant_values)
    return hashlib.md5(config_string.encode('utf-8')).hexdigest()

def save_frozen_configuration(frozen_config):
    """Speichert die eingefrorene Konfiguration robust"""
    cache_file = get_cache_file_path()
    temp_file = cache_file + ".tmp"
    
    try:
        # Metadaten hinzufügen
        save_data = {
            'frozen_scons_config': frozen_config,
            'config_hash': calculate_config_hash(),
            'freeze_timestamp': time.time(),
            'env_name': env.get("PIOENV"),
            'freeze_version': '1.0'
        }
        
        # Atomares Schreiben
        with gzip.open(temp_file, 'wb') as f:
            pickle.dump(save_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        # Validierung der geschriebenen Datei
        with gzip.open(temp_file, 'rb') as f:
            test_data = pickle.load(f)
            if 'frozen_scons_config' not in test_data:
                raise ValueError("Validierung fehlgeschlagen")
        
        # Atomarer Move
        shutil.move(temp_file, cache_file)
        
        file_size = os.path.getsize(cache_file)
        var_count = len(frozen_config)
        
        print(f"✓ Exakte SCons-Konfiguration gespeichert:")
        print(f"   📁 {os.path.basename(cache_file)} ({file_size} Bytes)")
        print(f"   📊 {var_count} SCons-Variablen eingefroren")
        
        return True
        
    except Exception as e:
        print(f"❌ Fehler beim Speichern der Konfiguration: {e}")
        # Cleanup
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def load_frozen_configuration():
    """Lädt die eingefrorene Konfiguration"""
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        return None
    
    try:
        with gzip.open(cache_file, 'rb') as f:
            data = pickle.load(f)
        
        # Validierung
        if 'frozen_scons_config' not in data:
            print("⚠ Ungültiges Format der eingefrorenen Konfiguration")
            return None
        
        # Hash-Prüfung
        current_hash = calculate_config_hash()
        saved_hash = data.get('config_hash')
        
        if current_hash != saved_hash:
            print("⚠ Konfiguration geändert - eingefrorene Konfiguration ungültig")
            return None
        
        frozen_config = data['frozen_scons_config']
        var_count = len(frozen_config)
        
        print(f"✓ Eingefrorene Konfiguration geladen: {var_count} Variablen")
        return frozen_config
        
    except Exception as e:
        print(f"❌ Fehler beim Laden der eingefrorenen Konfiguration: {e}")
        return None

# =============================================================================
# HAUPTLOGIK - EXAKTE SCONS-KONFIGURATION KONSERVIEREN
# =============================================================================

print(f"\n🎯 Exakte SCons-Konfigurationskonservierung für: {env.get('PIOENV')}")

# Cache-Prüfung und SCons-Environment-Wiederherstellung
cache_restored = early_cache_check_and_restore()

if cache_restored:
    print(f"🚀 Build mit EXAKTER SCons-Konfiguration - LDF übersprungen!")
    
    if not verify_frozen_restoration():
        print(f"❌ KRITISCHER FEHLER: SCons-Environment unvollständig!")
        print(f"💡 Löschen Sie '.pio/ldf_cache/' und starten Sie neu")

else:
    print(f"📝 Normaler LDF-Durchlauf - erfasse EXAKTE SCons-Konfiguration...")
    
    def post_build_freeze_configuration(source, target, env):
        """Post-Build: Friere exakte SCons-Konfiguration ein"""
        print(f"\n❄️  Post-Build: Friere exakte SCons-Konfiguration ein...")
        
        # Erfasse EXAKTE Konfiguration nach LDF-Durchlauf
        frozen_config = freeze_exact_scons_configuration()
        
        if len(frozen_config) > 50:  # Mindestens 50 SCons-Variablen
            if save_frozen_configuration(frozen_config):
                print(f"\n🎯 EXAKTE SCons-Konfiguration eingefroren:")
                print(f"   ❄️  Alle {len(frozen_config)} SCons-Variablen konserviert")
                
                # WICHTIG: Setze LDF auf off ERST NACH erfolgreichem Speichern
                env_name = env.get("PIOENV")
                if backup_and_modify_correct_ini_file(env_name, set_ldf_off=True):
                    print(f"✓ lib_ldf_mode = off für Lauf 2 gesetzt")
                    print(f"🚀 Lauf 2: Identische Konfiguration garantiert!")
                else:
                    print(f"⚠ lib_ldf_mode konnte nicht gesetzt werden")
                
            else:
                print(f"❌ Einfrieren der Konfiguration fehlgeschlagen")
        else:
            print(f"❌ Unvollständige SCons-Konfiguration - nicht eingefroren")
    
    env.AddPostAction("buildprog", post_build_freeze_configuration)

print(f"🏁 Exakte Konfigurationskonservierung initialisiert")
print(f"💡 Reset: rm -rf .pio/ldf_cache/\n")
