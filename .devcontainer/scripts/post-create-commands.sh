# Git config (optional)
if [ -n "$GIT_USER_EMAIL" ] && [ -n "$GIT_USER_NAME" ]; then
    git config --global user.email "$GIT_USER_EMAIL"
    git config --global user.name "$GIT_USER_NAME"
fi

# SSH setup (optional)
if [ -f ~/.ssh/id_rsa ]; then
    chmod 600 ~/.ssh/id_rsa
    eval $(ssh-agent -s)
    ssh-add ~/.ssh/id_rsa

    echo "chmod 600 ~/.ssh/id_rsa" >>~/.bashrc
    echo "eval \$(ssh-agent -s)" >>~/.bashrc
    echo "ssh-add ~/.ssh/id_rsa" >>~/.bashrc
fi

git config --global --add safe.directory /workspaces

# Install into an isolated virtual environment
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

# Bootstrap pip if it's missing (needed for some slim Python distributions)
python3 -m pip --version >/dev/null 2>&1 || curl -sS https://bootstrap.pypa.io/get-pip.py | python3
pip install --upgrade pip

# Install the project in editable mode
pip install -e .
