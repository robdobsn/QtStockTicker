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
    if VERSION["extra"] <= 0:
        return "{major}.{minor}.{patch}".format(**VERSION)
    return "{major}.{minor}.{patch}.post{extra}".format(**VERSION)

__version__ = get_version_string()
