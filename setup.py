import sys
from setuptools import setup, Extension

if sys.version_info[:2] < (3, 5):
    raise NotImplementedError("Required python version 3.5 or greater")

settings = {
    'name': 'squall',
    'version': '0.2.dev0',
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

settings['ext_modules'] = [
    Extension('squall._squall', **{
              'extra_compile_args': ['-std=c++11'],
              'include_dirs': ['./cxx'],
              'sources': ['squall/_squall/dispatcher.cpp'],
              'libraries': ['ev']})
]

try:
    setup(**settings)
except:
    print("WARNING! Cannot build C extension for event dispatching, "
          "will be used failback module.\n\n")
    del settings['ext_modules']
    settings['py_modules'].append('squall._tornado')
    settings['install_requires'].append('tornado >= 4.3')
    setup(**settings)
