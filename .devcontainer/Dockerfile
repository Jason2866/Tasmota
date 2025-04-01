FROM debian:bullseye-slim
#FROM mcr.microsoft.com/vscode/devcontainers/base:ubuntu

ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID


ENV DEBIAN_FRONTEND=noninteractive
# Install dependencies for building Python
RUN apt-get update \
    && apt-get install -y \
        wget \
        build-essential \
        libssl-dev \
        zlib1g-dev \
        libncurses5-dev \
        libgdbm-dev \
        libnss3-dev \
        libsqlite3-dev \
        libreadline-dev \
        libffi-dev \
        curl \
        libbz2-dev \
    && rm -rf /var/lib/apt/lists/*

# Download and build Python 3.13.2
RUN wget https://www.python.org/ftp/python/3.13.2/Python-3.13.2.tgz \
    && tar -xvf Python-3.13.2.tgz \
    && cd Python-3.13.2 \
    && ./configure --enable-optimizations \
    && make -j$(nproc) \
    && make altinstall \
    && cd .. \
    && rm -rf Python-3.13.2 Python-3.13.2.tgz

# Verify Python installation
RUN python3.13 --version

ENV DEBIAN_FRONTEND=dialog

RUN if [ ${USER_UID:-0} -ne 0 ] && [ ${USER_GID:-0} -ne 0 ]; then \
        groupadd --gid $USER_GID $USERNAME \
        && useradd -s /bin/bash --uid $USER_UID --gid $USER_GID -m $USERNAME \
        && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME\
        && chmod 0440 /etc/sudoers.d/$USERNAME \
    ; fi

# https://docs.platformio.org/en/latest/faq.html#platformio-udev-rules
# curl -fsSL https://raw.githubusercontent.com/platformio/platformio-core/develop/platformio/assets/system/99-platformio-udev.rules | sudo tee /etc/udev/rules.d/99-platformio-udev.rules
#RUN curl -fsSL https://raw.githubusercontent.com/platformio/platformio-core/develop/platformio/assets/system/99-platformio-udev.rules
#RUN cp 99-platformio-udev.rules /etc/udev/rules.d/99-platformio-udev.rules

#RUN usermod -a -G dialout $USERNAME
#RUN usermod -a -G plugdev $USERNAME

# Restart udev service to use the newly installed udev rules
# RUN service udev restart

USER $USERNAME
#RUN curl -fsSL https://raw.githubusercontent.com/pioarduino/pioarduino-core-installer/pioarduino/get-platformio.py -o /tmp/get-platformio.py \
#    && python3 /tmp/get-platformio.py \
#    && rm /tmp/get-platformio.py