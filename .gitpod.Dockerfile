FROM gitpod/workspace-python-3.11

USER gitpod

RUN apt-get update && apt-get install -yq \
    clang \
