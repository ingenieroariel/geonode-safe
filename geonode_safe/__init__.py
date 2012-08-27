__version__= (0, 1, 0, 'final', 0)

def get_version():
    from geonode_safe.version import get_version
    return get_version(__version__)
