env = DefaultEnvironment()
platform = env.PioPlatform()

from genericpath import exists
import os
import json
import hashlib
import sys
from os.path import join, getsize
import csv
import requests
import shutil
import subprocess
import codecs
from colorama import Fore, Back, Style
from SCons.Script import COMMAND_LINE_TARGETS
from platformio.project.config import ProjectConfig

def get_cache_file_path():
    """Generiert Pfad zur LDF-Cache-Datei für das aktuelle Environment"""
    env_name = env.get("PIOENV")
    cache_dir = os.path.join(env.GetProjectDir(), ".pio", "ldf_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{env_name}_deps.json")

def get_config_hash():
    """Erstellt Hash der relevanten Konfiguration für Cache-Invalidierung"""
    config_items = [
        str(env.get("LIB_DEPS", [])),
        str(env.get("BUILD_FLAGS", [])),
        env.get("BOARD", ""),
        env.get("PLATFORM", "")
    ]
    config_string = "|".join(config_items)
    return hashlib.md5(config_string.encode()).hexdigest()

def load_cached_deps():
    """Lädt gecachte Dependencies falls vorhanden und gültig"""
    cache_file = get_cache_file_path()
    
    if not os.path.exists(cache_file):
        return None
    
    try:
        with open(cache_file, 'r') as f:
            cache_data = json.load(f)
        
        # Prüfe ob Cache noch gültig ist
        if cache_data.get("config_hash") == get_config_hash():
            print(f"✓ LDF Cache geladen für {env.get('PIOENV')}")
            return cache_data.get("dependencies", [])
        else:
            print(f"⚠ LDF Cache ungültig für {env.get('PIOENV')} - wird neu erstellt")
            
    except (json.JSONDecodeError, KeyError):
        print(f"⚠ LDF Cache beschädigt für {env.get('PIOENV')} - wird neu erstellt")
    
    return None

def save_deps_cache(dependencies):
    """Speichert Dependencies im Cache"""
    cache_file = get_cache_file_path()
    cache_data = {
        "config_hash": get_config_hash(),
        "dependencies": dependencies,
        "timestamp": env.get("UNIX_TIME", 0)
    }
    
    with open(cache_file, 'w') as f:
        json.dump(cache_data, f, indent=2)
    
    print(f"✓ LDF Cache gespeichert für {env.get('PIOENV')}")

def apply_cached_deps():
    """Wendet gecachte Dependencies an"""
    cached_deps = load_cached_deps()
    
    if cached_deps is not None:
        # Deaktiviere LDF und setze explizite Dependencies
        env.Replace(LIB_LDF_MODE="off")
        env.Replace(LIB_DEPS=cached_deps)
        return True
    
    return False

def capture_ldf_results():
    """Erfasst LDF-Ergebnisse nach dem Build"""
    def post_build_callback(source, target, env):
        # Sammle alle verwendeten Libraries
        lib_deps = []
        libdeps_dir = os.path.join(env.GetProjectDir(), ".pio", "libdeps", env.get("PIOENV"))
        
        if os.path.exists(libdeps_dir):
            for lib_dir in os.listdir(libdeps_dir):
                lib_path = os.path.join(libdeps_dir, lib_dir)
                if os.path.isdir(lib_path):
                    # Versuche Library-Namen aus library.json zu extrahieren
                    library_json = os.path.join(lib_path, "library.json")
                    if os.path.exists(library_json):
                        try:
                            with open(library_json, 'r') as f:
                                lib_info = json.load(f)
                                lib_name = lib_info.get("name", lib_dir)
                                lib_deps.append(lib_name)
                        except:
                            lib_deps.append(lib_dir)
                    else:
                        lib_deps.append(lib_dir)
        
        # Speichere Dependencies im Cache
        if lib_deps:
            save_deps_cache(lib_deps)
    
    env.AddPostAction("$BUILD_DIR/${PROGNAME}.elf", post_build_callback)

# Hauptlogik
if not apply_cached_deps():
    print(f"🔍 Erster Build für {env.get('PIOENV')} - LDF wird ausgeführt")
    capture_ldf_results()
else:
    print(f"⚡ Verwende LDF Cache für {env.get('PIOENV')} - Build beschleunigt")

