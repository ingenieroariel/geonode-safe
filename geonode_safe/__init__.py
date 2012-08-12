__version__= (0, 1, 0, 'alpha', 0)

def get_version():
    from safe.common.version import get_version
    return get_version(__version__)
