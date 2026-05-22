"""Bootstrap module to clean up PATH conflicts and register local DLL directories on Windows.

This ensures PyTorch, Torchaudio, and Faster-Whisper load the compatible CUDA/cuDNN
libraries bundled in the virtual environment instead of conflicting system installations.
"""
from __future__ import annotations

import os
import sys

def bootstrap_paths() -> None:
    if sys.platform != "win32":
        return

    # Clean up system PATH to avoid DLL symbol mismatches from conflicting system CUDA installations
    path_dirs = os.environ.get("PATH", "").split(os.path.pathsep)
    new_dirs = []
    for d in path_dirs:
        # Filter out system NVIDIA CUDA paths that conflict with internal versions
        if "NVIDIA GPU Computing Toolkit" in d or "CUDA" in d:
            continue
        new_dirs.append(d)
    os.environ["PATH"] = os.path.pathsep.join(new_dirs)

    # Register local DLL directories to DLL search path
    try:
        # Find site-packages directories from sys.path
        site_packages_dirs = [p for p in sys.path if "site-packages" in p]
        
        # Add fallback search locations for site-packages in case it's not in sys.path
        venv_dir = os.path.dirname(os.path.dirname(sys.executable))
        fallback_sp = os.path.join(venv_dir, "Lib", "site-packages")
        if fallback_sp not in site_packages_dirs and os.path.exists(fallback_sp):
            site_packages_dirs.append(fallback_sp)

        for sp in site_packages_dirs:
            # 1. Register NVIDIA libraries (cublas, cudnn, etc.) inside venv
            nvidia_base = os.path.join(sp, "nvidia")
            if os.path.exists(nvidia_base):
                for root, dirs, files in os.walk(nvidia_base):
                    if "bin" in dirs:
                        bin_dir = os.path.join(root, "bin")
                        if any(f.endswith(".dll") for f in os.listdir(bin_dir)):
                            os.add_dll_directory(bin_dir)
            
            # 2. Register PyTorch lib directory inside venv
            torch_lib = os.path.join(sp, "torch", "lib")
            if os.path.exists(torch_lib):
                os.add_dll_directory(torch_lib)
    except Exception:
        pass

# Run bootstrap on module import
bootstrap_paths()
