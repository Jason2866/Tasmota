import requests
import subprocess
import json


tasmota32_ini_url = "https://raw.githubusercontent.com/arendst/Tasmota/development/platformio_tasmota32.ini"
print("Download ",tasmota32_ini_url)
r = requests.get(tasmota32_ini_url, stream=True)
framework = ""
for line in r.iter_lines():
    items = line.decode('utf-8').split("=")
    if "platform" == items[0].strip():
        framework = items[1].strip()
        print (framework)
cmd = ("pio","platform","install", framework)
returncode = subprocess.call(cmd, shell=False)
if returncode == 0:
    print("Framework installed ...")
else:
    print("Could not install Framework!!")
    
with open(".platformio/platforms/espressif32/platform.json") as json_file:
        data = json.load(json_file)
        for package in data['packages']:
            print(package)
    



