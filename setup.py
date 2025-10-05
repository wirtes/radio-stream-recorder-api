"""Setup configuration for the Radio Stream Recorder API."""

from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="radio-stream-recorder-api",
    version="1.0.0",
    description="API for recording radio streams with metadata processing and file transfer",
    packages=find_packages(),
    install_requires=requirements,
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "radio-recorder=main:app",
        ],
    },
)