"""
Script to install project requirements automatically.
"""

import subprocess
import sys
import os


def install():
    """
    Check and install requirements using pip.
    """
    # Change to project root directory if script is run from deployment/
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    os.chdir(project_root)

    requirements = ["requirements.txt", "requirements-dev.txt"]
    for req in requirements:
        if os.path.exists(req):
            print(f"Checking/Installing {req}...")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "-r", req]
                )
            except subprocess.CalledProcessError as e:
                print(f"Error installing {req}: {e}")
                sys.exit(1)

    print("All requirements processed successfully.")


if __name__ == "__main__":
    install()
