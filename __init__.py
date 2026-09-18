def classFactory(iface):
    """Load S2DR4Connector class from file s2dr4_connector.
    
    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    from .s2dr4_connector import S2DR4Connector
    return S2DR4Connector(iface)
