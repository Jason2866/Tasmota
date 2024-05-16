FROM gitpod/workspace-python-3.11

USER gitpod

RUN sudo apt-get update && sudo apt-get install -yq \
    clang \
