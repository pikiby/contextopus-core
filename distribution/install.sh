#!/bin/sh
# Bootstrap the reviewed starter bundle with the official uv installer.
set -eu
starter_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
starter_yes=false
starter_plan=false
for starter_arg in "$@"; do
    case "$starter_arg" in
        --yes) starter_yes=true ;;
        --plan) starter_plan=true ;;
    esac
done

# Planning must not install uv, download Python or create an environment.
if "$starter_plan"; then
    for starter_python in python3 python; do
        if command -v "$starter_python" >/dev/null 2>&1 &&
           "$starter_python" -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then
            exec "$starter_python" -B "$starter_dir/install.py" "$@"
        fi
    done
    echo 'Preview requires an existing Python 3.12+. Nothing was installed.' >&2
    exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
    starter_uv_dir="${XDG_BIN_HOME:-$HOME/.local/bin}"
    if [ -x "$starter_uv_dir/uv" ]; then
        PATH="$starter_uv_dir:$PATH"
        export PATH
    else
        echo 'Contextopus needs uv to install Python and application dependencies.'
        echo 'Download uv 0.13.1 from https://astral.sh/uv/0.13.1/install.sh?'
        if ! "$starter_yes"; then
            printf 'Install uv in %s without changing shell profiles? [y/N] ' "$starter_uv_dir"
            read -r starter_answer
            case "$starter_answer" in y|Y|yes|YES) ;; *) exit 1 ;; esac
        fi
        starter_download=$(mktemp)
        trap 'rm -f "$starter_download"' EXIT HUP INT TERM
        if command -v curl >/dev/null 2>&1; then
            curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
                https://astral.sh/uv/0.13.1/install.sh -o "$starter_download"
        elif command -v wget >/dev/null 2>&1; then
            wget --https-only -q https://astral.sh/uv/0.13.1/install.sh -O "$starter_download"
        else
            echo 'Install curl or wget, or obtain uv from https://docs.astral.sh/uv/.' >&2
            exit 1
        fi
        UV_INSTALL_DIR="$starter_uv_dir" UV_NO_MODIFY_PATH=1 sh "$starter_download"
        rm -f "$starter_download"
        trap - EXIT HUP INT TERM
        PATH="$starter_uv_dir:$PATH"
        export PATH
    fi
fi

exec uv run --no-project --no-config --python 3.12 python -B "$starter_dir/install.py" "$@"
