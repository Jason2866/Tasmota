FROM debian:bullseye-slim

ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update \
    && apt-get -qqy install \
        udev \
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

# Add udev rule for PlatformIO ports
RUN mkdir -p /etc/udev/rules.d/ && \
    wget -q https://raw.githubusercontent.com/platformio/platformio-core/develop/platformio/assets/system/99-platformio-udev.rules -O /etc/udev/rules.d/99-platformio-udev.rules

ENV DEBIAN_FRONTEND=dialog

# Set up the workspace
WORKDIR /workspace

# Create a non-root user with sudo privileges and add to dialout group
RUN if [ ${USER_UID:-0} -ne 0 ] && [ ${USER_GID:-0} -ne 0 ]; then \
        groupadd --gid $USER_GID $USERNAME \
        && useradd -s /bin/bash --uid $USER_UID --gid $USER_GID -m $USERNAME \
        && usermod -a -G dialout $USERNAME \
        && echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME \
        && chmod 0440 /etc/sudoers.d/$USERNAME \
    ; fi

# Set default user
ARG USERNAME=vscode
RUN useradd -ms /bin/bash $USERNAME && \
    usermod -aG sudo $USERNAME

# Switch to the non-root user
USER $USERNAME

# Final setup
CMD [ "bash" ]
