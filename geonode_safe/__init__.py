__version__= (0, 1, 0, 'alpha', 0)

def get_version():
    import geonode.utils
    return geonode.utils.get_version(__version__)
