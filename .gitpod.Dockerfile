FROM gitpod/workspace-full
                    
USER gitpod

RUN python3 -c "$(curl -fsSL https://raw.githubusercontent.com/platformio/platformio/master/scripts/get-platformio.py)"
