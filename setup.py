import sys

from setuptools import setup

if sys.version_info[:2] < (3, 5):
    raise NotImplementedError("Required python version 3.5 or greater")

settings = {
    'name': 'squall',
    'version': '0.1a3',
    'namespace_packages': ['squall'],
    'py_modules': ['squall.coroutine',
                   'squall.network',
                   'squall.gateway'],
    'author': "Alexey Poryadin",
    'author_email': "alexey.poryadin@gmail.com",
    'description': "The Squall is the nano-framework that"
                   " implements cooperative event-driven"
                   " concurrency and asynchronous networking.",
    'install_requires': ['squall-cxx>=0.1a2'],
    'dependency_links': [
        'git+https://github.com/Alesh/Squall-CXX.git@master#egg=squall-cxx-0.1a2'
    ],
    'zip_safe': False,
}

try:
    setup(**settings)
except BaseException as exc:
    settings['py_modules'].append('squall.failback')
    settings['install_requires'].remove('squall.cxx')
    settings['install_requires'].append('tornado >= 4.3')
    print("\nWARNING! Cannot install event dispatcher from 'squall.cxx'")
    print("WARNING! Will be used failback event dispatcher based on tornado\n")
    setup(**settings)
