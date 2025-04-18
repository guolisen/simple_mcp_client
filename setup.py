#!/usr/bin/env python
"""Setup script for Simple MCP Client."""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="simple-mcp-client",
    version="0.2.4",
    description="A simple MCP client for testing MCP servers",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Lewis Guo",
    author_email="guolisen@gmail.com",
    url="https://github.com/guolisen/simple-mcp-client",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "simple_mcp_client": ["config/default_config.json"],
    },
    entry_points={
        "console_scripts": [
            "simple-mcp-client=simple_mcp_client.main:main",
        ],
    },
    install_requires=[
        "mcp>=1.0.0",
        "httpx>=0.20.0",
        "prompt-toolkit>=3.0.0",
        "click>=8.0.0",
        "rich>=10.0.0",
        "python-dotenv>=0.19.0",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.10",
)
