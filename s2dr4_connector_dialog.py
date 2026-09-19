import os
import time
import requests
import traceback
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.PyQt.QtWidgets import QDialog, QMessageBox, QFileDialog
from qgis.core import (QgsProject, QgsVectorLayer, QgsRasterLayer, 
                       QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsMessageLog, Qgis)

# This loads your .ui file so that PyQt can populate your plugin with the elements from Qt Designer
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 's2dr4_connector_dialog_base.ui'))

class S2DR4Worker(QThread):
    """Worker thread to run HTTP requests without freezing QGIS UI."""
    progress_update = pyqtSignal(int, str)
    feature_done = pyqtSignal(str, str) # title, file_path
    finished = pyqtSignal(bool, str) # success, message
    
    def __init__(self, api_url, date_str, layer, output_dir, band="MS"):
        super().__init__()
        self.api_url = api_url.rstrip('/')
        self.date_str = date_str
        self.layer = layer
        self.output_dir = output_dir
        self.band = band
        self.is_running = True

    def run(self):
        try:
            features = list(self.layer.getFeatures())
            total = len(features)
            
            if total == 0:
                self.finished.emit(False, "Layer titik (Point) kosong.")
                return

            source_crs = self.layer.crs()
            target_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())

            for i, feat in enumerate(features):
                if not self.is_running:
                    break
                    
                geom = feat.geometry()
                if geom.isNull():
                    continue
                
                geom.transform(transform)
                point = geom.asPoint()
                lon, lat = point.x(), point.y()
                
                self.progress_update.emit(int((i / total) * 100), f"Memproses Titik {i+1}/{total} (Lon: {lon:.4f}, Lat: {lat:.4f})...")
                
                endpoint = f"{self.api_url}/infer"
                payload = {
                    "lon": lon,
                    "lat": lat,
                    "date": self.date_str
                }
                
                try:
                    self.progress_update.emit(int((i / total) * 100), f"Mengirim antrean ke Colab AI (Titik {i+1})...")
                    response = requests.post(endpoint, json=payload, timeout=60)
                    
                    if response.status_code == 200:
                        resp_data = response.json()
                        job_id = resp_data.get("job_id")
                        status_url = f"{self.api_url}/status/{job_id}"
                        download_url = f"{self.api_url}/download/{job_id}?band={self.band}"
                        
                        is_done = False
                        error_msg = ""
                        while not is_done and self.is_running:
                            time.sleep(5)
                            s_resp = requests.get(status_url, timeout=30)
                            if s_resp.status_code == 200:
                                s_data = s_resp.json()
                                status = s_data.get("status")
                                if status == "completed":
                                    is_done = True
                                elif status == "error":
                                    is_done = True
                                    error_msg = s_data.get("error", "Unknown error")
                                else:
                                    self.progress_update.emit(int((i / total) * 100), f"Colab sedang memproses Titik {i+1}... (Estimasi 3-5 menit)")
                                    
                        if error_msg:
                            QgsMessageLog.logMessage(f"Titik {i+1} AI Error: {error_msg}", 'S2DR4', Qgis.Warning)
                            continue
                            
                        if not self.is_running:
                            break
                            
                        self.progress_update.emit(int((i / total) * 100), f"Titik {i+1} selesai. Mengunduh hasil ({self.band})...")
                        
                        # Streaming download
                        dl_resp = requests.get(download_url, stream=True, timeout=600)
                        if dl_resp.status_code == 200:
                            filename = f"S2L3Ax10_{self.date_str.replace('-','')}_{lon:.4f}_{lat:.4f}_{self.band}.tif"
                            if 'content-disposition' in dl_resp.headers:
                                cd = dl_resp.headers['content-disposition']
                                if 'filename=' in cd:
                                    original = cd.split('filename=')[1].strip('"')
                                    name_part, ext = os.path.splitext(original)
                                    filename = f"{name_part}_lon{lon:.4f}_lat{lat:.4f}{ext}"
                            
                            out_path = os.path.join(self.output_dir, filename)
                            with open(out_path, 'wb') as f:
                                for chunk in dl_resp.iter_content(chunk_size=1024*1024):
                                    if chunk:
                                        f.write(chunk)
                            
                            self.feature_done.emit(filename, out_path)
                        else:
                            QgsMessageLog.logMessage(f"Titik {i+1} Gagal Download. Kode: {dl_resp.status_code}", 'S2DR4', Qgis.Warning)
                    else:
                        QgsMessageLog.logMessage(f"Titik {i+1} Gagal Antre. Kode: {response.status_code}", 'S2DR4', Qgis.Warning)
                except Exception as e:
                    QgsMessageLog.logMessage(f"Request Error Titik {i+1}: {str(e)}", 'S2DR4', Qgis.Critical)
            
            if self.is_running:
                self.progress_update.emit(100, "Semua titik selesai diproses.")
                self.finished.emit(True, "Pemrosesan batch selesai!")
                
        except Exception as e:
            err_msg = traceback.format_exc()
            self.finished.emit(False, f"Terjadi kesalahan internal:\\n{str(e)}")
            QgsMessageLog.logMessage(err_msg, 'S2DR4', Qgis.Critical)

    def stop(self):
        self.is_running = False

class S2DR4ConnectorDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        """Constructor."""
        super(S2DR4ConnectorDialog, self).__init__(parent)
        self.setupUi(self)
        self.worker = None

        # Connect UI signals
        self.btn_browse.clicked.connect(self.browse_folder)
        self.btn_process.clicked.connect(self.start_processing)
        self.btn_cancel.clicked.connect(self.cancel_processing)

    def refresh_layers(self):
        self.combo_layer.clear()
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == 0:
                self.combo_layer.addItem(layer.name(), layer.id())

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Pilih Folder Output TIF")
        if folder:
            self.input_outdir.setText(folder)

    def start_processing(self):
        api_url = self.input_url.text().strip()
        date_str = self.input_date.text().strip()
        out_dir = self.input_outdir.text().strip()
        layer_id = self.combo_layer.currentData()
        
        band_selection = self.combo_band.currentText()
        band = "TCI"
        if "MS" in band_selection:
            band = "MS"
        elif "NDVI" in band_selection:
            band = "NDVI"
        elif "IRP" in band_selection:
            band = "IRP"
        
        if not api_url or not date_str or not out_dir or not layer_id:
            QMessageBox.warning(self, "Peringatan", "Semua kolom harus diisi!")
            return
            
        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            QMessageBox.critical(self, "Error", "Layer tidak ditemukan!")
            return
            
        self.btn_process.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("Status: Menghubungi server Colab...")
        
        self.worker = S2DR4Worker(api_url, date_str, layer, out_dir, band)
        self.worker.progress_update.connect(self.on_progress)
        self.worker.feature_done.connect(self.on_feature_done)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_progress(self, val, text):
        self.progress_bar.setValue(val)
        self.lbl_status.setText(f"Status: {text}")

    def on_feature_done(self, title, file_path):
        layer = QgsRasterLayer(file_path, title)
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            QgsMessageLog.logMessage(f"Berhasil memuat: {title}", 'S2DR4', Qgis.Success)
        else:
            QgsMessageLog.logMessage(f"Gagal memuat raster: {file_path}", 'S2DR4', Qgis.Critical)

    def on_finished(self, success, message):
        self.btn_process.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        if success:
            QMessageBox.information(self, "Selesai", message)
            self.lbl_status.setText("Status: Selesai.")
        else:
            QMessageBox.critical(self, "Error", message)
            self.lbl_status.setText("Status: Dibatalkan/Error.")

    def cancel_processing(self):
        if self.worker:
            self.worker.stop()
            self.lbl_status.setText("Status: Membatalkan proses...")
