import requests

tasmota32_ini_url = "https://raw.githubusercontent.com/arendst/Tasmota/development/platformio_tasmota32.ini"
print("Download ",tasmota32_ini_url)
r = requests.get(tasmota32_ini_url, stream=True)
for line in r.iter_lines():
    items = line.decode('utf-8').split("=")
    if "platform" == items[0].strip():
        framework = items[1].strip()
        print (framework)

