#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安装脚本
"""
from setuptools import setup, find_packages

setup(
    name="ble-host",
    version="1.0.0",
    description="BLE Host上位机程序",
    author="Your Name",
    packages=find_packages(),
    install_requires=[
        "pyserial>=3.5",
        "matplotlib>=3.7.0",
        "numpy>=1.24.0",
    ],
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "ble-host=src.main_gui:main",
        ],
    },
)

