"""
Lanzador de Wiki Procedimientos.

Se puede ejecutar con doble clic o desde una consola:

    python iniciar_wiki.py

No requiere módulos externos.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
SERVER_FILE = BASE_DIR / "server.py"
DEFAULT_URL = "http://127.0.0.1:8080"
STARTUP_TIMEOUT_SECONDS = 15


def pause(message: str = "Pulse INTRO para cerrar...") -> None:
    """Mantiene la consola abierta cuando se produce un error."""
    try:
        input(f"\n{message}")
    except (EOFError, KeyboardInterrupt):
        pass


def check_python() -> bool:
    """Comprueba que la versión de Python sea compatible."""
    minimum = (3, 10)
    current = sys.version_info[:3]

    print(f"Python........ {current[0]}.{current[1]}.{current[2]}")

    if current < minimum:
        print("ERROR: se necesita Python 3.10 o superior.")
        return False

    print("Estado Python. OK")
    return True


def check_server_file() -> bool:
    """Comprueba que server.py exista en la misma carpeta."""
    if not SERVER_FILE.exists():
        print(f"ERROR: no se encuentra {SERVER_FILE.name}")
        print(f"Carpeta revisada: {BASE_DIR}")
        return False
    return True


def wait_until_available(url: str, process: subprocess.Popen) -> bool:
    """Espera hasta que el servidor responda o termine con error."""
    deadline = time.time() + STARTUP_TIMEOUT_SECONDS

    while time.time() < deadline:
        if process.poll() is not None:
            return False

        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return 200 <= response.status < 500
        except Exception:
            time.sleep(0.35)

    return False


def main() -> int:
    os.chdir(BASE_DIR)

    print("=" * 48)
    print("          WIKI DE PROCEDIMIENTOS")
    print("=" * 48)
    print(f"Carpeta....... {BASE_DIR}")

    if not check_python() or not check_server_file():
        pause()
        return 1

    print("Servidor...... iniciando")
    print("Navegador..... se abrirá automáticamente")
    print("-" * 48)

    creation_flags = 0
    if os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    try:
        process = subprocess.Popen(
            [sys.executable, str(SERVER_FILE)],
            cwd=str(BASE_DIR),
            creationflags=creation_flags,
        )
    except OSError as exc:
        print(f"ERROR al iniciar el servidor: {exc}")
        pause()
        return 1

    # server.py ya abre normalmente el navegador. Esta comprobación sirve
    # como respaldo si el navegador no se abre automáticamente.
    if wait_until_available(DEFAULT_URL, process):
        print(f"Wiki disponible: {DEFAULT_URL}")
        try:
            webbrowser.open(DEFAULT_URL)
        except Exception:
            pass
    else:
        if process.poll() is not None:
            print("El servidor se cerró durante el inicio.")
        else:
            print("No se pudo confirmar el inicio en el puerto 8080.")
            print("El servidor puede haber seleccionado otro puerto.")
        print("Revise los mensajes mostrados por server.py.")

    print("\nPara detener la wiki, cierre esta ventana o pulse Ctrl+C.")

    try:
        return process.wait()
    except KeyboardInterrupt:
        print("\nCerrando Wiki Procedimientos...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
