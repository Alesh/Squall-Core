import sys
from setuptools import setup, Extension

if sys.version_info[:2] < (3, 5):
    raise NotImplementedError("Required python version 3.5 or greater")

settings = {
    'name': 'squall',
    'version': '0.3.dev0',
    'namespace_packages': ['squall'],
    'package_dir': {'squall': './squall/python'},
    'py_modules': ['squall.coroutine',
                   'squall.network',
                   'squall.stream'],
    'author': "Alexey Poryadin",
    'author_email': "alexey.poryadin@gmail.com",
    'description': "The Squall is the nano-framework that"
                   " implements cooperative event-driven"
                   " concurrency and asynchronous networking.",
    'install_requires': [],
    'packages': [],
}

settings['ext_modules'] = [
    Extension('_squall', **{
              'extra_compile_args': ['-std=c++11'],
              'include_dirs': ['./'],
              'sources': ['./squall/python/_squall/!module.cxx'],
              'libraries': ['ev', 'boost_python-py35']})
]

try:
    setup(**settings)
except:
    print("WARNING! Cannot build C extension for event dispatching, "
          "will be used failback module.\n\n")
    del settings['ext_modules']
    settings['package_dir'][''] = './squall/python/failback'
    settings['install_requires'].append('tornado >= 4.3')
    settings['packages'].append('_squall')
    setup(**settings)
