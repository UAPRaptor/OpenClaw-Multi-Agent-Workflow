from setuptools import setup, find_packages

setup(
    name="openclaw-mission-control",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "openclaw": [
            "corpus/**/*",
            "web/static/**/*",
        ]
    },
    install_requires=[
        "fastapi>=0.110.0",
        "uvicorn>=0.29.0",
        "watchdog>=4.0.0",
        "typer>=0.12.0",
        "psutil>=5.9.0",
        "jinja2>=3.1.0",
        "python-multipart>=0.0.9",
    ],
    entry_points={
        "console_scripts": [
            "openclaw=openclaw.cli:app",
        ]
    },
    python_requires=">=3.10",
)
