import os
import sys
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from youtube_downloader.backend.downloader import download_videos, fetch_channel_content
from youtube_downloader.utils.config import load_config, save_config


class DownloadWorker(QThread):
    """Worker thread for downloading videos."""

    progress_update = Signal(dict)
    log_message = Signal(str)
    finished = Signal()

    def __init__(self, urls: list[str], download_folder: str, quality: str) -> None:
        """Initialize the worker with URLs, download folder, and quality.

        Args:
            urls (list[str]): List of video URLs to download.
            download_folder (str): Folder to save downloaded videos.
            quality (str): Selected quality for downloading videos.
        """
        super().__init__()
        self.urls = urls
        self.download_folder = download_folder
        self.quality = quality
        self._is_aborted = False

    def run(self) -> None:
        """Main worker function that runs on thread start."""

        def progress_hook(status: dict[str, Any]) -> None:
            self.progress_update.emit(status)
            if self._is_aborted:
                raise Exception("Download aborted by user.")

        try:
            download_videos(
                self.urls,
                self.download_folder,
                quality=self.quality,
                progress_hook=progress_hook,
                logger_callback=lambda msg: self.log_message.emit(msg)
            )
        except Exception as e:
            self.log_message.emit(f"ERROR: {e}")
        finally:
            self.finished.emit()

    def abort(self) -> None:
        """Abort the download process."""
        self._is_aborted = True


class FetchChannelWorker(QThread):
    """Worker thread for fetching channel content."""

    content_fetched = Signal(dict)
    log_message = Signal(str)
    error = Signal(str)

    def __init__(self, channel_url: str) -> None:
        """Initialize the worker with channel URL.

        Args:
            channel_url (str): URL of the channel to fetch content from.
        """
        super().__init__()
        self.channel_url = channel_url

    def run(self) -> None:
        """Main worker function that runs on thread start."""
        try:
            content = fetch_channel_content(
                self.channel_url, logger_callback=lambda msg: self.log_message.emit(msg)
            )
            self.content_fetched.emit(content)
        except Exception as e:
            self.error.emit(str(e))


class LogsWidget(QWidget):
    """Widget for displaying log messages."""

    def __init__(self) -> None:
        """Initialize the LogsWidget."""
        super().__init__()
        self.init_ui()

    def init_ui(self) -> None:
        """Initialize the UI components."""
        layout = QVBoxLayout(self)

        label = QLabel("Logs:")
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)

        layout.addWidget(label)
        layout.addWidget(self.log_text)

    def append_log(self, message: str) -> None:
        """Append a log message to the text area.

        Args:
            message (str): Log message to append.
        """
        self.log_text.append(message)
        # Auto-scroll to the bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


class DownloadControlsWidget(QWidget):
    """Widget containing the common download controls for all tabs."""

    def __init__(self, log_callback: Callable[[str], None]) -> None:
        """Initialize the DownloadControlsWidget.

        Args:
            log_callback (Callable[[str], None]): Callback function for logging messages.
        """
        super().__init__()
        self.log_callback = log_callback
        self.config_data = load_config()
        self.download_folder = self.config_data.get(
            "download_folder", str(Path.home() / "Downloads")
        )
        self.init_ui()

    def init_ui(self) -> None:
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)  # Remove extra margins

        # Quality selection
        quality_layout = QHBoxLayout()
        label_quality = QLabel("Select Quality:")
        self.combo_quality = QComboBox()
        self.combo_quality.addItems(["Best", "1080p", "720p", "480p", "360p"])
        self.combo_quality.setCurrentText("Best")

        quality_layout.addWidget(label_quality)
        quality_layout.addWidget(self.combo_quality)

        # Download folder selection
        folder_layout = QHBoxLayout()
        label_folder = QLabel("Download Folder:")
        self.entry_folder = QLineEdit()
        self.entry_folder.setText(self.download_folder)
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self.browse_folder)

        folder_layout.addWidget(label_folder)
        folder_layout.addWidget(self.entry_folder, 1)
        folder_layout.addWidget(btn_browse)

        # Download and Abort buttons
        button_layout = QHBoxLayout()
        self.btn_download = QPushButton("Download")
        self.btn_abort = QPushButton("Abort")
        self.btn_abort.setEnabled(False)
        button_layout.addWidget(self.btn_download)
        button_layout.addWidget(self.btn_abort)

        # Status and progress
        self.label_current = QLabel("Current Video: Idle")
        self.progress_bar = QProgressBar()

        # Add widgets to layout
        layout.addLayout(quality_layout)
        layout.addLayout(folder_layout)
        layout.addLayout(button_layout)
        layout.addWidget(self.label_current)
        layout.addWidget(self.progress_bar)

    def browse_folder(self) -> None:
        """Open folder dialog to choose download folder."""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Download Folder", self.download_folder
        )
        if folder:
            self.download_folder = folder
            self.entry_folder.setText(folder)

    def start_download(self, urls: list[str]) -> None:
        """Start downloading the provided URLs.

        Args:
            urls (list[str]): List of URLs to download.
        """
        if not urls:
            return

        self.download_folder = self.entry_folder.text().strip()
        self.config_data["download_folder"] = self.download_folder
        save_config(self.config_data)

        selected_quality = self.combo_quality.currentText()
        quality_mapping = {
            "Best": "bestvideo+bestaudio/best",
            "1080p": "bestvideo[height<=1080]+bestaudio/best",
            "720p": "bestvideo[height<=720]+bestaudio/best",
            "480p": "bestvideo[height<=480]+bestaudio/best",
            "360p": "bestvideo[height<=360]+bestaudio/best",
        }
        selected_quality = quality_mapping.get(selected_quality, "best")

        self.btn_download.setEnabled(False)
        self.btn_abort.setEnabled(True)
        self.label_current.setText("Downloading...")

        # Create and start worker thread
        self.worker = DownloadWorker(urls, self.download_folder, selected_quality)
        self.worker.progress_update.connect(self.update_progress)
        self.worker.log_message.connect(self.log_callback)
        self.worker.finished.connect(self.download_finished)
        self.worker.start()

    def abort_download(self) -> None:
        """Abort the ongoing download."""
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.abort()
            self.btn_abort.setEnabled(False)
            self.label_current.setText("Aborting download...")

    def update_progress(self, status: dict[str, Any]) -> None:
        """Update progress UI based on download status.

        Args:
            status (dict[str, Any]): Status dictionary from the download process.
        """
        if status.get("status") == "downloading":
            downloaded = status.get("downloaded_bytes", 0)
            total = status.get("total_bytes", 1)
            if total > 0:
                percent = int(downloaded / total * 100)
                self.progress_bar.setValue(percent)
            self.label_current.setText(f"Downloading: {status.get('filename', '')}")
        elif status.get("status") == "finished":
            self.label_current.setText(f"Finished: {status.get('filename', '')}")
            self.progress_bar.setValue(0)

    def download_finished(self) -> None:
        """Handle download completion."""
        self.btn_download.setEnabled(True)
        self.btn_abort.setEnabled(False)
        self.label_current.setText("All downloads completed.")


class BatchWidget(QWidget):
    """Widget for batch URL downloading."""

    def __init__(self, log_callback: Callable[[str], None]) -> None:
        """Initialize the BatchWidget.

        Args:
            log_callback (Callable[[str], None]): Callback function for logging messages.
        """
        super().__init__()
        self.log_callback = log_callback
        self.init_ui()

    def init_ui(self) -> None:
        """Initialize the UI components."""
        layout = QVBoxLayout(self)

        # URLs input area
        label_urls = QLabel("Enter URL(s) (one per line):")
        self.text_urls = QTextEdit()

        # Create download controls
        self.download_controls = DownloadControlsWidget(self.log_callback)

        # Connect the download and abort buttons
        self.download_controls.btn_download.clicked.connect(self.start_download)
        self.download_controls.btn_abort.clicked.connect(self.download_controls.abort_download)

        # Add widgets to layout
        layout.addWidget(label_urls)
        layout.addWidget(self.text_urls, 1)
        layout.addWidget(self.download_controls)

    def start_download(self) -> None:
        """Start downloading the URLs from the text area."""
        urls_text = self.text_urls.toPlainText().strip()
        if not urls_text:
            QMessageBox.warning(self, "Input Error", "Please enter at least one URL.")
            return

        urls = [line.strip() for line in urls_text.splitlines() if line.strip()]
        self.download_controls.start_download(urls)


class ChannelWidget(QWidget):
    """Widget for channel URL download with selectable video tree."""

    def __init__(self, log_callback: Callable[[str], None]) -> None:
        """Initialize the ChannelWidget.

        Args:
            log_callback (Callable[[str], None]): Callback function for logging messages.
        """
        super().__init__()
        self.log_callback = log_callback
        self.init_ui()

    def init_ui(self) -> None:
        """Initialize the UI components."""
        layout = QVBoxLayout(self)

        # Channel URL input
        channel_layout = QHBoxLayout()
        label = QLabel("Channel URL:")
        self.entry_channel = QLineEdit()
        btn_fetch = QPushButton("Fetch Channel")
        btn_fetch.clicked.connect(self.fetch_channel)

        channel_layout.addWidget(label)
        channel_layout.addWidget(self.entry_channel, 1)
        channel_layout.addWidget(btn_fetch)

        # Tree view for video selection in a stacked widget
        self.stacked_widget = QStackedWidget()

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Videos")
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)

        # Spinner for loading
        self.spinner = QLabel()
        self.spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spinner.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        self.spinner.setText("Loading...")

        self.stacked_widget.addWidget(self.tree)
        self.stacked_widget.addWidget(self.spinner)

        # Create download controls
        self.download_controls = DownloadControlsWidget(self.log_callback)

        # Connect the download and abort buttons
        self.download_controls.btn_download.clicked.connect(self.start_download)
        self.download_controls.btn_abort.clicked.connect(self.download_controls.abort_download)

        # Add widgets to layout
        layout.addLayout(channel_layout)
        layout.addWidget(self.stacked_widget, 1)
        layout.addWidget(self.download_controls)

    def fetch_channel(self) -> None:
        """Fetch content from the provided channel URL and populate the tree."""
        channel_url = self.entry_channel.text().strip()
        if not channel_url:
            QMessageBox.warning(self, "Input Error", "Please enter a channel URL.")
            return

        self.tree.clear()
        self.download_controls.label_current.setText("Fetching channel content...")
        self.stacked_widget.setCurrentWidget(self.spinner)

        # Create and start worker thread
        self.fetch_worker = FetchChannelWorker(channel_url)
        self.fetch_worker.content_fetched.connect(self.populate_tree)
        self.fetch_worker.log_message.connect(self.log_callback)
        self.fetch_worker.error.connect(self.show_fetch_error)
        self.fetch_worker.start()

    def show_fetch_error(self, error_msg: str) -> None:
        """Display an error message when fetching fails.

        Args:
            error_msg (str): Error message to display.
        """
        QMessageBox.critical(self, "Error Fetching Channel", error_msg)
        self.download_controls.label_current.setText("Failed to fetch channel content.")
        self.stacked_widget.setCurrentWidget(self.tree)

    def populate_tree(self, content: dict[str, Any]) -> None:
        """Populate the tree with fetched channel content.

        Args:
            content (dict[str, Any]): Dictionary containing channel content.
        """
        # Define order for non-playlist sections
        sections_order = [
            ("videos", "Videos"),
            ("shorts", "Shorts"),
            ("lives", "Lives"),
            ("podcasts", "Podcasts"),
        ]

        for key, display_name in sections_order:
            items = content.get(key, [])
            if not items:
                continue
            parent_item = QTreeWidgetItem(self.tree, [display_name])
            parent_item.setFlags(
                parent_item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsAutoTristate
            )
            parent_item.setCheckState(0, Qt.CheckState.Unchecked)
            self._populate_recursive(parent_item, items)

        # Handle playlists separately
        playlists = content.get("playlists", {})
        if playlists:
            playlists_parent = QTreeWidgetItem(self.tree, ["Playlists"])
            playlists_parent.setFlags(
                playlists_parent.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsAutoTristate
            )
            playlists_parent.setCheckState(0, Qt.CheckState.Unchecked)

            for pl_title, pl_videos in playlists.items():
                if not pl_videos:
                    continue
                pl_item = QTreeWidgetItem(playlists_parent, [pl_title])
                pl_item.setFlags(
                    pl_item.flags()
                    | Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsAutoTristate
                )
                pl_item.setCheckState(0, Qt.CheckState.Unchecked)
                self._populate_recursive(pl_item, pl_videos)

        self.tree.collapseAll()
        self.download_controls.label_current.setText("Channel content loaded.")
        self.stacked_widget.setCurrentWidget(self.tree)

    def _populate_recursive(
        self, parent_item: QTreeWidgetItem, items: list[dict[str, Any]]
    ) -> None:
        """Helper method to populate tree nodes recursively for a list of items.

        Args:
            parent_item (QTreeWidgetItem): Parent tree item.
            items (list[dict[str, Any]]): List of items to populate.
        """
        for video in items:
            title = video.get("title", "No Title")
            item = QTreeWidgetItem(parent_item, [title])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            # Store video data in the item
            item.setData(0, Qt.ItemDataRole.UserRole, video)

    def start_download(self) -> None:
        """Start downloading the selected videos from the tree."""
        selected_urls = self._get_selected_urls()

        if not selected_urls:
            QMessageBox.warning(
                self, "Selection Error", "No videos selected for download."
            )
            return

        self.download_controls.start_download(selected_urls)

    def _get_selected_urls(self) -> list[str]:
        """Get the URLs of selected videos from the tree.

        Returns:
            list[str]: List of selected video URLs.
        """
        selected_urls = []

        def process_item(item: QTreeWidgetItem) -> None:
            # If this is a leaf node (video) and checked
            if item.childCount() == 0 and item.checkState(0) == Qt.CheckState.Checked:
                video_data = item.data(0, Qt.ItemDataRole.UserRole)
                if video_data and "full_url" in video_data:
                    selected_urls.append(video_data["full_url"])

            # Process children
            for i in range(item.childCount()):
                process_item(item.child(i))

        # Process all top-level items
        for i in range(self.tree.topLevelItemCount()):
            process_item(self.tree.topLevelItem(i))

        return selected_urls


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        """Initialize the MainWindow."""
        super().__init__()
        self.setWindowTitle("YouTube Video Downloader")
        self.setMinimumSize(800, 600)
        self.init_ui()

    def init_ui(self) -> None:
        """Initialize the UI components."""
        # Create tab widget
        self.tabs = QTabWidget()

        # Create logs widget first to provide log callback
        self.logs_widget = LogsWidget()
        log_callback = self.logs_widget.append_log

        # Create other widgets - each with their own download controls
        self.batch_widget = BatchWidget(log_callback)
        self.channel_widget = ChannelWidget(log_callback)

        # Add widgets to tabs
        self.tabs.addTab(self.batch_widget, "Batch URLs")
        self.tabs.addTab(self.channel_widget, "Channel")
        self.tabs.addTab(self.logs_widget, "Logs")

        # Set tabs as central widget
        self.setCentralWidget(self.tabs)

        # Try to set icon
        try:
            icon_path = os.path.join(
                "src", "youtube_downloader", "assets", "icons", "youtube.ico"
            )
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            print(f"Error setting icon: {e}")


def run() -> None:
    """Run the YouTube Downloader application."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
