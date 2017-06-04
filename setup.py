import sys
from setuptools import setup


if sys.version_info[:2] < (3, 5):
    raise NotImplementedError("Required python version 3.5 or greater")


setup(**{
    'name': 'Squall',
    'version': '0.1.dev170604',
    'author': 'Alexey Poryadin',
    'author_email': 'alexey.poryadin@gmail.com',
    'description': "The Squall this is set of modules which implements"
                   "the cooperative multitasking based on event-driven"
                   "switching async/await coroutines.",
    'namespace_packages': ['squall'],
    'packages': ['squall.core'],
    'setup_requires': ['pytest-runner'],
    'tests_require': ['pytest', 'pytest_catchlog'],
    'zip_safe': False
})
