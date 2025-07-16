"""
Setup configuration for Apple Search Ads Python Client.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="apple-search-ads-client",
    version="1.0.7",
    author="Bickster LLC",
    author_email="support@bickster.com",
    description="A Python client for Apple Search Ads API v5",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/bickster/apple-search-ads-python",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Libraries",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "pytest-mock>=3.10.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
            "sphinx>=6.0.0",
            "sphinx-rtd-theme>=1.0.0",
        ]
    },
    project_urls={
        "Bug Reports": "https://github.com/bickster/apple-search-ads-python/issues",
        "Source": "https://github.com/bickster/apple-search-ads-python",
        "Documentation": "https://apple-search-ads-python.readthedocs.io/",
    },
    keywords="apple search ads api marketing advertising ios app store",
)