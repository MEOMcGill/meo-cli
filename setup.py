from setuptools import setup

setup(
    name="meo-cli",
    version="0.1.0",
    py_modules=["main"],
    install_requires=[
        "requests",
        "typer",
        "typing_extensions",
    ],
    entry_points={
        "console_scripts": [
            "meo=main:main",
        ],
    },
)