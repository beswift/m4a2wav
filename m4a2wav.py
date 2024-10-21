import sys
import os
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, 
                               QFileDialog, QLabel, QProgressBar, QListWidget, QHBoxLayout,
                               QSlider, QStyle, QListWidgetItem, QMenu)
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QColor
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from pydub import AudioSegment

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

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("M4A to WAV Converter")
        self.setGeometry(100, 100, 600, 500)
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

    def update_file_list_item(self, file_path):
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == file_path:
                item.setBackground(QColor(200, 255, 200))  # Light green background
                item.setText(f"{os.path.basename(file_path)} (Converted)")
                break

    def conversion_finished(self):
        self.progress_bar.setValue(100)
        self.status_label.setText("Conversion complete!")
        self.select_button.setEnabled(True)
        self.output_dir_button.setEnabled(True)

    def load_media(self, file_path):
        self.media_player.setSource(QUrl.fromLocalFile(file_path))
        self.play_button.setEnabled(True)

    def toggle_playback(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def set_position(self, position):
        self.media_player.setPosition(position)

    def position_changed(self, position):
        self.position_slider.setValue(position)

    def duration_changed(self, duration):
        self.position_slider.setRange(0, duration)

    def show_context_menu(self, position):
        menu = QMenu()
        remove_action = menu.addAction("Remove")
        action = menu.exec(self.file_list.mapToGlobal(position))
        if action == remove_action:
            self.remove_selected_file()

    def remove_selected_file(self):
        current_item = self.file_list.currentItem()
        if current_item:
            file_path = current_item.data(Qt.ItemDataRole.UserRole)
            self.input_files.remove(file_path)
            self.file_list.takeItem(self.file_list.row(current_item))
            if file_path in self.converted_files:
                del self.converted_files[file_path]

    def preview_converted_file(self, item):
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if file_path in self.converted_files:
            converted_file = self.converted_files[file_path]
            self.preview_label.setText(f"Preview: {os.path.basename(converted_file)}")
            self.load_media(converted_file)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())