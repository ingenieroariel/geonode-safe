#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os

from distutils.core import setup
geonode_safe = __import__('geonode_safe')


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name='geonode-safe',
    version=geonode_safe.get_version(),
    description='GeoNode SAFE plugin',
    long_description=read('README'),
    author='Ariel Núñez',
    author_email='ingenieroariel@gmail.com',
    url='http://github.com/GFDRR/geonode-safe/',
    platforms=['any'],
    license='GPLv3',
    zip_safe=False,
    install_requires=[
        'python-safe>=0.5',       # pip install python-safe
        'GeoNodePy',              # sudo apt-get install geonode
    ],
    packages = ['geonode_safe',],
    package_data = {'geonode_safe': ['geonode_safe/templates/*', 'geonode_safe/locale']},
    scripts = [],
    classifiers = [
        'Development Status :: 2 - Pre-Alpha',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GPL License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Internet :: WWW/HTTP :: WSGI',
        'Topic :: Scientific/Engineering :: GIS',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: Libraries :: Python Modules',
   ],
)
