import os.path
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
# Initialize Qt resources from file resources.py
import S2DR4_Connector_Official.resources
from .s2dr4_connector_dialog import S2DR4ConnectorDialog
from .s2dr4_grid_dialog import S2DR4GridDialog

class S2DR4Connector:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = u'&S2DR4 Connector'
        self.first_start = None
        self.dialog = None

    def add_action(self,
                   icon_path,
                   text,
                   callback,
                   enabled_flag=True,
                   add_to_menu=True,
                   add_to_toolbar=True,
                   status_tip=None,
                   whats_this=None,
                   parent=None):
        """Add a toolbar icon to the toolbar."""

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)
        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.svg')
        self.add_action(
            icon_path,
            text=u'S2DR4 Connector (Download)',
            callback=self.run,
            parent=self.iface.mainWindow())
            
        icon_grid_path = os.path.join(os.path.dirname(__file__), 'icon_grid.svg')
        self.add_action(
            icon_grid_path,
            text=u'S2DR4 Grid Generator',
            callback=self.run_grid,
            parent=self.iface.mainWindow())
            
        self.first_start = True
        self.first_start_grid = True

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)

    def run(self):
        """Run method that performs all the real work"""
        if self.first_start == True:
            self.first_start = False
            self.dialog = S2DR4ConnectorDialog(self.iface.mainWindow())
            
        self.dialog.refresh_layers()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def run_grid(self):
        """Run the grid generator"""
        if self.first_start_grid == True:
            self.first_start_grid = False
            self.grid_dialog = S2DR4GridDialog(self.iface.mainWindow())
            
        self.grid_dialog.refresh_layers()
        self.grid_dialog.show()
        self.grid_dialog.raise_()
        self.grid_dialog.activateWindow()
