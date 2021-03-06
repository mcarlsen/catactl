from setuptools import find_packages, setup

setup(
    name='catalib',
    version='0.0.2',
    packages=find_packages(),
    tests_require=[
        'pytest>=6.2.4,<6.3',
    ],
    install_requires=[
        'requests>=2.25.1,<2.26',
        'click>=8.0.0,<8.1',
        'psutil>=5.8.0,<5.9',
    ],
    entry_points={
        'console_scripts': [
            "catactl=catactl.catactl:catactl",
        ],
    },
)
