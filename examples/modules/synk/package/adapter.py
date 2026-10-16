"""External command adapter; Core contains no Synk-specific integration."""
import shutil
import subprocess


def version(arguments):
    command = shutil.which('codex-sync') or shutil.which('contextopus-synk')
    if not command:
        return {'available': False, 'reason': 'Synk executable is not on PATH'}
    result = subprocess.run([command, '--version'], capture_output=True, text=True, timeout=10)
    return {'available': True, 'command': command, 'returncode': result.returncode, 'version': result.stdout.strip(), 'stderr': result.stderr.strip()}
