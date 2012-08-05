#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os

from distutils.core import setup
geonode_safe = __import__('geonode_safe')

if os.path.exists('README.rst'):
    long_description = codecs.open('README.rst', 'r', 'utf-8').read()
else:
    long_description = 'See http://github.com/GFDRR/geonode-safe'


setup(
    name='geonode-safe',
    version=geonode_safe.get_version(),
    description='GeoNode SAFE plugin',
    author='Ariel Núñez',
    author_email='ingenieroariel@gmail.com',
    url='http://github.com/GFDRR/geonode-safe/',
    platforms=['any'],
    license=,
    packages=packages,
    data_files=data_files,
   #zip_safe=False,
    install_requires=[
        'safe>=0.5',       # pip install python-safe
        'geonode>=1.2',    # sudo apt-get install geonode
    ],
    packages = ['geonode_safe', 'risiko'],
    package_dir = {'geonode_safe': 'geonode_safe'},
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
        'Programming Language :: Python :: 2.5',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Internet :: WWW/HTTP :: WSGI',
        'Topic :: Scientific/Engineering :: GIS',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: Libraries :: Python Modules',
   ],
   long_description=long_description,
)
