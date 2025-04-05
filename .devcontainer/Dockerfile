FROM python:slim-bullseye

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

# Add udev rule for PlatformIO ports
RUN mkdir -p /etc/udev/rules.d/ && \
    wget -q https://raw.githubusercontent.com/platformio/platformio-core/develop/platformio/assets/system/99-platformio-udev.rules -O /etc/udev/rules.d/99-platformio-udev.rules

ENV DEBIAN_FRONTEND=dialog

# Set up the workspace
WORKDIR /workspaces

# Create a non-root user with sudo privileges and add to dialout group
RUN if [ ${USER_UID:-0} -ne 0 ] && [ ${USER_GID:-0} -ne 0 ]; then \
        groupadd --gid $USER_GID $USERNAME \
        && useradd -s /bin/bash --uid $USER_UID --gid $USER_GID -m $USERNAME \
        && usermod -a -G dialout $USERNAME \
        && echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME \
        && chmod 0440 /etc/sudoers.d/$USERNAME \
    ; fi


# Switch to the non-root user
USER $USERNAME

# Final setup
CMD [ "bash" ]
