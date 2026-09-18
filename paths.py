# -*- coding: utf-8 -*-
"""Project resource and writable-data paths for source-based execution."""
import os


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def resource_dir():
    return PROJECT_DIR


def data_dir():
    if os.environ.get("FARBOD_DATA_DIR"):
        path = os.path.abspath(os.environ["FARBOD_DATA_DIR"])
        os.makedirs(path, exist_ok=True)
        return path
    return PROJECT_DIR


def iso_dir():
    """Where uploaded .iso files are stored. Kept separate from instance/
    (which holds the small sqlite DB) since ISOs can be several GB each."""
    path = os.path.join(data_dir(), "instance", "isos")
    os.makedirs(path, exist_ok=True)
    return path
