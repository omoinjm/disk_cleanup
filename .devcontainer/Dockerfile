# See here for image contents: https://github.com/microsoft/vscode-dev-containers/tree/v0.134.0/containers/python-3/.devcontainer/base.Dockerfile
ARG VARIANT="3"
FROM mcr.microsoft.com/vscode/devcontainers/python:0-${VARIANT}

ARG USERNAME=vscode

# [Optional] Remove Yarn repository source and install additional OS packages.
RUN if [ -f /etc/apt/sources.list.d/yarn.list ]; then rm /etc/apt/sources.list.d/yarn.list; fi \
    && apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
        software-properties-common \
        parted \
        dosfstools \
        exfatprogs \
        util-linux \
        python3-pip \
        python3-venv

# Set up bash history
RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
    && mkdir -p /commandhistory \
    && touch /commandhistory/.bash_history \
    && chown -R $USERNAME:$USERNAME /commandhistory \
    && echo "$SNIPPET" >> "/home/$USERNAME/.bashrc" \
    && echo "$SNIPPET" >> "/root/.bashrc"
