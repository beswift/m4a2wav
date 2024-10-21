import sys
import os
import numpy as np
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, 
                               QFileDialog, QLabel, QProgressBar, QListWidget, QHBoxLayout,
                               QSlider, QStyle, QListWidgetItem, QMenu, QStyledItemDelegate)
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QColor, QBrush, QPainter, QLinearGradient, QFont, QPen
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWebEngineWidgets import QWebEngineView
from pydub import AudioSegment
import pyqtgraph as pg
import soundfile as sf
from bokeh.plotting import figure
from bokeh.resources import CDN
from bokeh.embed import file_html
from bokeh.models import HoverTool, BoxZoomTool, ResetTool, PanTool, WheelZoomTool

class ConversionThread(QThread):
    progress = Signal(int)
    file_converted = Signal(str, str)  # original file, converted file
    finished = Signal()

    def __init__(self, input_files, output_dir):
        super().__init__()
        self.input_files = input_files
        self.output_dir = output_dir

    def run(self):
        total_files = len(self.input_files)
        for i, input_file in enumerate(self.input_files):
            output_file = os.path.join(self.output_dir, os.path.splitext(os.path.basename(input_file))[0] + ".wav")
            audio = AudioSegment.from_file(input_file, format="m4a")
            audio.export(output_file, format="wav")
            self.progress.emit(int((i + 1) / total_files * 100))
            self.file_converted.emit(input_file, output_file)
        self.finished.emit()

class GradientItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.data(Qt.ItemDataRole.UserRole + 1):  # Check if it's a converted file
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Set up the font
            font = QFont("Arial", 10)
            painter.setFont(font)

            # Create the gradient
            gradient = QLinearGradient(option.rect.topLeft(), option.rect.topRight())
            gradient.setColorAt(0.0, QColor("#78FFD6"))
            gradient.setColorAt(1.0, QColor("#007991"))
            
            # Draw the text
            painter.setPen(QPen(gradient, 1))
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignVCenter, "  " + index.data())

            painter.restore()
        else:
            super().paint(painter, option, index)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("M4A to WAV Converter")
        self.setGeometry(100, 100, 1000, 800)
        self.setAcceptDrops(True)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # File selection area
        file_selection_layout = QHBoxLayout()
        self.select_button = QPushButton("Select M4A File(s)")
        self.select_button.clicked.connect(self.select_files)
        file_selection_layout.addWidget(self.select_button)

        self.output_dir_button = QPushButton("Select Output Directory")
        self.output_dir_button.clicked.connect(self.select_output_dir)
        file_selection_layout.addWidget(self.output_dir_button)

        layout.addLayout(file_selection_layout)

        # File list
        self.file_list = QListWidget()
        self.file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self.show_context_menu)
        self.file_list.itemClicked.connect(self.preview_converted_file)
        self.file_list.setItemDelegate(GradientItemDelegate())
        layout.addWidget(self.file_list)

        # Output directory label
        self.output_dir_label = QLabel("Output Directory: Not selected")
        layout.addWidget(self.output_dir_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        # Bokeh waveform visualization
        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)


        # Audio preview area
        preview_layout = QHBoxLayout()
        self.play_button = QPushButton()
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_button.clicked.connect(self.toggle_playback)
        preview_layout.addWidget(self.play_button)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.sliderMoved.connect(self.set_position)
        preview_layout.addWidget(self.position_slider)

        layout.addLayout(preview_layout)

        self.preview_label = QLabel("No file selected for preview")
        layout.addWidget(self.preview_label)

        self.input_files = []
        self.output_dir = ""
        self.converted_files = {}  # Dictionary to store original:converted file pairs

        # Set up media player
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.positionChanged.connect(self.position_changed)
        self.media_player.durationChanged.connect(self.duration_changed)

        self.current_audio_data = None
        self.current_audio_pos = 0

         # Real-time audio visualization
        self.audio_plot = pg.PlotWidget()
        self.audio_curve = self.audio_plot.plot(pen='#77ff88')
        layout.addWidget(self.audio_plot)
               # Timer for updating real-time visualization
        self.visualization_timer = QTimer()
        self.visualization_timer.timeout.connect(self.update_visualization)
        self.visualization_timer.start(50)  # Update every 50 ms

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        new_files = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith('.m4a'):
                new_files.append(file_path)
                self.add_file_to_list(file_path)
        if new_files and self.output_dir:
            self.input_files.extend(new_files)
            self.start_conversion(new_files)

    def add_file_to_list(self, file_path):
        item = QListWidgetItem(os.path.basename(file_path))
        item.setData(Qt.ItemDataRole.UserRole, file_path)
        item.setData(Qt.ItemDataRole.UserRole + 1, False)  # Not converted yet
        self.file_list.addItem(item)

    def select_files(self):
        file_dialog = QFileDialog(self)
        files, _ = file_dialog.getOpenFileNames(self, "Select M4A File(s)", "", "M4A Files (*.m4a)")
        if files:
            for file in files:
                if file not in self.input_files:
                    self.input_files.append(file)
                    self.add_file_to_list(file)
            if self.output_dir:
                self.start_conversion(files)

    def select_output_dir(self):
        dir_dialog = QFileDialog(self)
        self.output_dir = dir_dialog.getExistingDirectory(self, "Select Output Directory")
        if self.output_dir:
            self.output_dir_label.setText(f"Output Directory: {self.output_dir}")

    def start_conversion(self, files):
        self.select_button.setEnabled(False)
        self.output_dir_button.setEnabled(False)
        self.status_label.setText("Converting...")
        self.progress_bar.setValue(0)

        self.conversion_thread = ConversionThread(files, self.output_dir)
        self.conversion_thread.progress.connect(self.update_progress)
        self.conversion_thread.file_converted.connect(self.file_converted)
        self.conversion_thread.finished.connect(self.conversion_finished)
        self.conversion_thread.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def file_converted(self, original_file, converted_file):
        self.converted_files[original_file] = converted_file
        self.update_file_list_item(original_file)
        self.preview_label.setText(f"Preview: {os.path.basename(converted_file)}")
        self.load_media(converted_file)
        self.display_waveform(converted_file)

    def update_file_list_item(self, file_path):
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == file_path:
                item.setData(Qt.ItemDataRole.UserRole + 1, True)  # Mark as converted
                item.setText(f"{os.path.basename(file_path)} (Converted)")
                self.file_list.repaint()
                break

    def conversion_finished(self):
        self.progress_bar.setValue(100)
        self.status_label.setText("Conversion complete!")
        self.select_button.setEnabled(True)
        self.output_dir_button.setEnabled(True)

    def load_media(self, file_path):
        self.media_player.setSource(QUrl.fromLocalFile(file_path))
        self.play_button.setEnabled(True)
        self.current_audio_data, _ = sf.read(file_path)
        self.current_audio_pos = 0

    def toggle_playback(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def set_position(self, position):
        self.media_player.setPosition(position)

    def position_changed(self, position):
        self.position_slider.setValue(position)
        self.current_audio_pos = int(position / 1000 * 44100)  # Assuming 44.1kHz sample rate

    def duration_changed(self, duration):
        self.position_slider.setRange(0, duration)

    def show_context_menu(self, position):
        menu = QMenu()
        remove_action = menu.addAction("Remove")
        reconvert_action = menu.addAction("Reconvert")
        action = menu.exec(self.file_list.mapToGlobal(position))
        if action == remove_action:
            self.remove_selected_file()
        elif action == reconvert_action:
            self.reconvert_selected_file()

    def remove_selected_file(self):
        current_item = self.file_list.currentItem()
        if current_item:
            file_path = current_item.data(Qt.ItemDataRole.UserRole)
            if file_path in self.input_files:
                self.input_files.remove(file_path)
            self.file_list.takeItem(self.file_list.row(current_item))
            if file_path in self.converted_files:
                del self.converted_files[file_path]

    def reconvert_selected_file(self):
        current_item = self.file_list.currentItem()
        if current_item:
            file_path = current_item.data(Qt.ItemDataRole.UserRole)
            if self.output_dir:
                self.start_conversion([file_path])

    def preview_converted_file(self, item):
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if file_path in self.converted_files:
            converted_file = self.converted_files[file_path]
            self.preview_label.setText(f"Preview: {os.path.basename(converted_file)}")
            self.load_media(converted_file)
            self.display_waveform(converted_file)

    def display_waveform(self, file_path):
        audio_data, sample_rate = sf.read(file_path)
        time = np.arange(0, len(audio_data)) / sample_rate

        p = figure(title="Audio Waveform", x_axis_label="Time (s)", y_axis_label="Amplitude",
                tools="pan,box_zoom,wheel_zoom,reset,hover",
                active_drag="pan",
                active_scroll="wheel_zoom",
                width=800, height=300)

        # Add the waveform
        gradient = ["#78FFD6", "#007991"]  # Start and end colors of the gradient
        p.line(time, audio_data, line_color="#78FFD6", line_alpha=0.8)

        # Customize the plot
        p.background_fill_color = "#f0f0f0"  # Light gray background
        p.border_fill_color = None
        p.outline_line_color = None
        p.grid.grid_line_color = "#e0e0e0"  # Lighter gray for grid lines
        p.axis.axis_line_color = '#007991'
        p.axis.major_tick_line_color = '#007991'
        p.axis.axis_label_text_color = '#007991'
        p.axis.major_label_text_color = '#007991'
        p.title.text_color = '#007991'

        # Add hover tool
        hover = p.select_one(HoverTool)
        hover.tooltips = [("Time", "@x{0.000}s"), ("Amplitude", "@y")]
        hover.mode = 'vline'

        # Create the HTML
        html = file_html(p, CDN, "Audio Waveform")
        self.web_view.setHtml(html)
        self.web_view.show()

    def update_visualization(self):
        if self.current_audio_data is not None and self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            chunk_size = 1000
            end_pos = min(self.current_audio_pos + chunk_size, len(self.current_audio_data))
            chunk = self.current_audio_data[self.current_audio_pos:end_pos]
            self.audio_curve.setData(chunk)
            self.current_audio_pos = end_pos
            if self.current_audio_pos >= len(self.current_audio_data):
                self.current_audio_pos = 0

    def toggle_playback(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        else:
            self.media_player.play()
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())