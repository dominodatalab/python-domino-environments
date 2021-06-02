import re

from setuptools import find_packages, setup


def get_version():
    try:
        fp = open(f"domino_environments/_version.py")
    except EnvironmentError:
        return None

    re_version = re.compile(r'__version__ = "([^"]+)"')
    for line in fp.readlines():
        match = re_version.search(line)
        if match:
            return match.group(1)

    return None


def get_requirements():
    with open("requirements.txt") as fp:
        return fp.readlines()


setup(
    name="python-domino-environments",
    version=get_version(),
    author="Domino Data Lab",
    author_email="support@dominodatalab.com",
    packages=find_packages(),
    scripts=[],
    url="https://www.dominodatalab.com/",
    license="LICENSE",
    description="Extension on the Python bindings for the Domino API to work with environments",
    long_description="",
    install_requires=get_requirements(),
)
