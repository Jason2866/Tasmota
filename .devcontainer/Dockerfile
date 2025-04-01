FROM debian:bullseye-slim
#FROM mcr.microsoft.com/vscode/devcontainers/base:ubuntu

ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

ENV DEBIAN_FRONTEND=noninteractive
# Install dependencies
RUN apt-get update \
    && apt-get -qqy install \
        apt-utils \
        ca-certificates \
        dialog \
        git \
        sudo \
        unzip \
        wget \
        bc \
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
        srecord \
        xz-utils \
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

# Set Python 3.13.2 as the default Python version
RUN ln -sf /usr/local/bin/python3.13 /usr/bin/python && \
    ln -sf /usr/local/bin/python3.13 /usr/bin/python3 && \
    ln -sf /usr/local/bin/pip3.13 /usr/bin/pip && \
    ln -sf /usr/local/bin/pip3.13 /usr/bin/pip3

# Verify default Python version
RUN python --version && python3 --version

ENV DEBIAN_FRONTEND=dialog

# Create a non-root user with sudo privileges
RUN if [ ${USER_UID:-0} -ne 0 ] && [ ${USER_GID:-0} -ne 0 ]; then \
        groupadd --gid $USER_GID $USERNAME \
        && useradd -s /bin/bash --uid $USER_UID --gid $USER_GID -m $USERNAME \
        && echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME \
        && chmod 0440 /etc/sudoers.d/$USERNAME \
    ; fi

# Optional: Install PlatformIO udev rules
RUN curl -fsSL https://raw.githubusercontent.com/platformio/platformio-core/develop/platformio/assets/system/99-platformio-udev.rules \
    -o /etc/udev/rules.d/99-platformio-udev.rules

# Add user to necessary groups (uncomment if needed)
RUN usermod -a -G dialout $USERNAME
RUN usermod -a -G plugdev $USERNAME

# Restart udev service to apply new rules (uncomment if needed)
# RUN service udev restart

USER $USERNAME
