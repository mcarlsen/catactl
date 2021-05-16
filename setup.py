from setuptools import find_packages, setup

setup(
    name='cddalib',
    version='0.0.1',
    packages=find_packages(),
    install_requires=[
        'requests>=2.25.1,<2.26',
        'click>=8.0.0,<8.1',
    ],
    entry_points={
        'console_scripts': [
            "catactl=cddalib.catactl:catactl",
        ],
    }
)
