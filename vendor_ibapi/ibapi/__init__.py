"""
Copyright (C) 2019 Interactive Brokers LLC. All rights reserved. This code is subject to the terms
 and conditions of the IB API Non-Commercial License or the IB API Commercial License, as applicable.
"""

""" Package implementing the Python API for the TWS/IB Gateway """

VERSION = {
    'major': 9,
    'minor': 81,
    'patch': 1,
    'extra': 1}


def get_version_string():
    version = '{major}.{minor}.{patch}-{extra}'.format(**VERSION)
    if( VERSION['extra'] <= 0):
        version = '{major}.{minor}.{patch}'.format(**VERSION)
    return version

__version__ = get_version_string()
