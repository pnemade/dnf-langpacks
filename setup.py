#!/usr/bin/env python
"""
Build script for dnf-langpacks
"""
from setuptools import setup, find_packages

setup (name = "dnf-langpacks",
    version = '0.12.0',
    packages = find_packages(), 
    description = "Automatic installation of langpacks of packages being installed.",
    author = 'Parag Nemade',
    author_email = 'pnemade@redhat.com',
    license = 'GPLv2+',
    platforms=["Linux"],

    data_files=[('/usr/lib/python2.7/site-packages/dnf-plugins', ['langpacks.py']),
                 ('/usr/share/man/man8', ['dnf.plugin.langpacks.8']),
                 ('/etc/dnf/plugins/', ['langpacks.conf'])],

    classifiers=['License :: OSI Approved ::  GNU General Public License (GPL)',
                 'Operating System :: Unix',
                 'Programming Language :: Python',
                 ],
)
