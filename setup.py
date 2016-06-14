import sys

from setuptools import setup

if sys.version_info[:2] < (3, 5):
    raise NotImplementedError("Required python version 3.5 or greater")

settings = {
    'name': 'squall',
    'version': '0.1a1',
    'namespace_packages': ['squall'],
    'py_modules': ['squall.coroutine',
                   'squall.network',
                   'squall.gateway'],
    'author': "Alexey Poryadin",
    'author_email': "alexey.poryadin@gmail.com",
    'description': "The Squall is the nano-framework that"
                   " implements cooperative event-driven"
                   " concurrency and asynchronous networking.",
    'install_requires': [],
    'zip_safe': False,
}

settings['install_requires'].append('tornado>=4.3')

setup(**settings)
