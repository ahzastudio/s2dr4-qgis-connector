import os
import math
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                                 QComboBox, QDoubleSpinBox, QPushButton, QMessageBox)
from qgis.core import (QgsProject, QgsVectorLayer, QgsCoordinateReferenceSystem, 
                       QgsCoordinateTransform, QgsGeometry, QgsPointXY, QgsFeature, 
                       QgsField, QgsMessageLog, Qgis)
from qgis.PyQt.QtCore import QVariant

class S2DR4GridDialog(QDialog):
    def __init__(self, parent=None):
        super(S2DR4GridDialog, self).__init__(parent)
        self.setWindowTitle("S2DR4 Grid Generator")
        self.resize(400, 250)
        
        layout = QVBoxLayout(self)
        
        # Layer Selection
        layer_layout = QHBoxLayout()
        layer_label = QLabel("Layer Polygon (AOI):")
        self.combo_layer = QComboBox()
        layer_layout.addWidget(layer_label)
        layer_layout.addWidget(self.combo_layer)
        layout.addLayout(layer_layout)
        
        # Tile Size
        size_layout = QHBoxLayout()
        size_label = QLabel("Ukuran Tile (meter):")
        self.spin_size = QDoubleSpinBox()
        self.spin_size.setRange(100, 20000)
        self.spin_size.setValue(4000)
        self.spin_size.setDecimals(0)
        size_layout.addWidget(size_label)
        size_layout.addWidget(self.spin_size)
        layout.addLayout(size_layout)
        
        # Overlap
        overlap_layout = QHBoxLayout()
        overlap_label = QLabel("Overlap antar Tile (meter):")
        self.spin_overlap = QDoubleSpinBox()
        self.spin_overlap.setRange(0, 5000)
        self.spin_overlap.setValue(100)
        self.spin_overlap.setDecimals(0)
        overlap_layout.addWidget(overlap_label)
        overlap_layout.addWidget(self.spin_overlap)
        layout.addLayout(overlap_layout)
        
        # Output Name
        self.btn_generate = QPushButton("Buat Grid Titik")
        self.btn_generate.clicked.connect(self.generate_grid)
        layout.addWidget(self.btn_generate)
        
        self.lbl_status = QLabel("Status: Siap.")
        layout.addWidget(self.lbl_status)
        
        self.refresh_layers()

    def refresh_layers(self):
        self.combo_layer.clear()
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            # Only polygon layers
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == 2:
                self.combo_layer.addItem(layer.name(), layer.id())

    def generate_grid(self):
        layer_id = self.combo_layer.currentData()
        if not layer_id:
            QMessageBox.warning(self, "Peringatan", "Pilih layer Polygon terlebih dahulu!")
            return
            
        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            return
            
        tile_size = self.spin_size.value()
        overlap = self.spin_overlap.value()
        step = tile_size - overlap
        
        if step <= 0:
            QMessageBox.warning(self, "Peringatan", "Overlap tidak boleh lebih besar dari ukuran Tile!")
            return
            
        self.btn_generate.setEnabled(False)
        self.lbl_status.setText("Status: Membangun Grid...")
        
        try:
            # Setup CRS Transformations
            source_crs = layer.crs()
            # Use EPSG:3857 (Web Mercator) as a generic metric CRS for distance math near equator
            metric_crs = QgsCoordinateReferenceSystem("EPSG:3857")
            out_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            
            transform_to_metric = QgsCoordinateTransform(source_crs, metric_crs, QgsProject.instance())
            transform_to_out = QgsCoordinateTransform(metric_crs, out_crs, QgsProject.instance())
            
            # Combine all features into one geometry to get overall bounding box
            all_geoms = []
            for feat in layer.getFeatures():
                geom = feat.geometry()
                if not geom.isNull():
                    geom.transform(transform_to_metric)
                    all_geoms.append(geom)
            
            if not all_geoms:
                raise Exception("Polygon kosong atau tidak valid.")
                
            combined_geom = QgsGeometry.unaryUnion(all_geoms)
            bbox = combined_geom.boundingBox()
            
            # Create Memory Layer for output points
            out_layer = QgsVectorLayer("Point?crs=EPSG:4326", f"Grid S2DR4 ({int(tile_size)}m)", "memory")
            provider = out_layer.dataProvider()
            provider.addAttributes([QgsField("id", QVariant.Int), QgsField("tile_size", QVariant.Int)])
            out_layer.updateFields()
            
            # Generate Grid Points
            x_min, x_max = bbox.xMinimum(), bbox.xMaximum()
            y_min, y_max = bbox.yMinimum(), bbox.yMaximum()
            
            # We add padding to ensure edges are covered
            x = x_min + (tile_size / 2)
            features_to_add = []
            point_id = 1
            
            # We cover slightly beyond the max to avoid gaps
            # Optimize: Buffer the combined AOI geometry ONCE instead of buffering every point
            # This increases the generation speed by orders of magnitude for complex polygons
            buffered_aoi = combined_geom.buffer(tile_size / 2, 5)
            
            current_x = x_min
            while current_x <= x_max + (tile_size / 2):
                current_y = y_min
                while current_y <= y_max + (tile_size / 2):
                    # Point geometry in Metric
                    pt_geom_metric = QgsGeometry.fromPointXY(QgsPointXY(current_x, current_y))
                    
                    # If the point falls within the buffered AOI, keep this centroid
                    if pt_geom_metric.intersects(buffered_aoi):
                        # Transform point to EPSG:4326 for S2DR4 compatibility
                        pt_geom_out = QgsGeometry(pt_geom_metric)
                        pt_geom_out.transform(transform_to_out)
                        
                        feat = QgsFeature()
                        feat.setGeometry(pt_geom_out)
                        feat.setAttributes([point_id, int(tile_size)])
                        features_to_add.append(feat)
                        point_id += 1
                        
                    current_y += step
                current_x += step
                
            if features_to_add:
                provider.addFeatures(features_to_add)
                QgsProject.instance().addMapLayer(out_layer)
                QMessageBox.information(self, "Selesai", f"Berhasil membuat {len(features_to_add)} titik grid centroids!")
            else:
                QMessageBox.warning(self, "Kosong", "Tidak ada titik yang dihasilkan. Periksa polygon AOI.")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            QgsMessageLog.logMessage(str(e), 'S2DR4 Grid Generator', Qgis.Critical)
            
        finally:
            self.lbl_status.setText("Status: Selesai.")
            self.btn_generate.setEnabled(True)
