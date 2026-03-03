from setuptools import find_packages, setup

setup(
    name="alliantie-gen-ai",
    version="0.1.0",
    description="A collection of generative AI tools for De Alliantie.",
    author="DCC Data Science",
    author_email="dcc@de-alliantie.nl",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    license="Copyright (C) 2026 De Alliantie",
    python_requires=">=3.10",
)
