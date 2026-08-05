# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2019 gfduszynski
"""Packaging metadata for cm_rgb."""

import os
from setuptools import setup


def read(fname):
    """Read a file relative to this setup.py, for use as the long description."""
    with open(os.path.join(os.path.dirname(__file__), fname), encoding="utf-8") as f:
        return f.read()

setup(
    name = "cm_rgb",
    version = "0.3.5",
    author = "gfduszynski",
    author_email = "gfduszynski@gmail.com",
    description = ("Utility to control RGB on AMD Wraith Prism"),
    license = "MIT",
    keywords = "rgb hid wraith",
    url = "http://github.com/gfduszynski/cm-rgb",
    packages=['cm_rgb'],
    scripts=[
        'scripts/cm-rgb-cli',
        'scripts/cm-rgb-gui',
        'scripts/cm-rgb-monitor'
    ],
    data_files=[
        ('share/applications', ['data/cm-rgb-gui.desktop']),
    ],
    long_description=read('README.md'),
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Topic :: Utilities",
        "License :: OSI Approved :: MIT License",
    ],
    install_requires=[
          'hidapi',
          'click' ,
          'psutil',
          'PyGObject'
    ],
)
