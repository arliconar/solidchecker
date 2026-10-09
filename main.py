import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtCore import Qt
from gui import MainWindow

STYLESHEET = """
        QWidget {
            color: #0F172A;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 13px;
        }
        QMainWindow {
            background-color: #F1F5F9;
        }
        QFrame#headerFrame {
            background-color: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 8px;
            padding: 4px 8px;
        }
        QLabel {
            color: #0F172A;
            background: transparent;
        }
        QGroupBox {
            font-weight: 600;
            color: #0F172A;
            border: 1px solid #CBD5E1;
            border-radius: 8px;
            margin-top: 10px;
            padding-top: 14px;
            background-color: #FFFFFF;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
            background-color: #FFFFFF;
            color: #0F172A;
        }
        QPushButton {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #CBD5E1;
            border-radius: 6px;
            padding: 6px 14px;
            font-weight: 500;
        }
        QPushButton:hover {
            background-color: #F8FAFC;
            border-color: #94A3B8;
        }
        QPushButton:pressed {
            background-color: #E2E8F0;
        }
        QPushButton:disabled {
            background-color: #F1F5F9;
            color: #94A3B8;
            border-color: #E2E8F0;
        }
        QPushButton#btnAnalyze {
            background-color: #2563EB;
            color: #FFFFFF;
            border: 1px solid #1D4ED8;
            border-radius: 6px;
            font-weight: 600;
            padding: 6px 16px;
        }
        QPushButton#btnAnalyze:hover {
            background-color: #1D4ED8;
        }
        QPushButton#btnAnalyze:disabled {
            background-color: #CBD5E1;
            color: #94A3B8;
            border: 1px solid #CBD5E1;
        }
        QComboBox {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #CBD5E1;
            border-radius: 6px;
            padding: 5px 10px;
            min-height: 22px;
        }
        QComboBox:hover {
            border-color: #94A3B8;
        }
        QComboBox:focus {
            border: 1px solid #2563EB;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 24px;
            border-left: 1px solid #E2E8F0;
        }
        QComboBox QAbstractItemView {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #CBD5E1;
            selection-background-color: #DBEAFE;
            selection-color: #1E3A8A;
            outline: none;
        }
        QLineEdit {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #CBD5E1;
            border-radius: 6px;
            padding: 5px 10px;
        }
        QLineEdit:focus {
            border: 1px solid #2563EB;
        }
        QCheckBox {
            color: #0F172A;
            spacing: 6px;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 1px solid #CBD5E1;
            border-radius: 4px;
            background-color: #FFFFFF;
        }
        QCheckBox::indicator:checked {
            background-color: #2563EB;
            border-color: #2563EB;
        }
        QTableWidget {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #CBD5E1;
            border-radius: 6px;
            gridline-color: #E2E8F0;
            selection-background-color: #DBEAFE;
            selection-color: #1E3A8A;
        }
        QHeaderView::section {
            background-color: #F8FAFC;
            color: #334155;
            font-weight: 600;
            padding: 8px 6px;
            border: none;
            border-right: 1px solid #E2E8F0;
            border-bottom: 2px solid #CBD5E1;
        }
        QProgressBar {
            border: 1px solid #CBD5E1;
            border-radius: 6px;
            background-color: #E2E8F0;
            text-align: center;
            color: #0F172A;
            font-weight: 600;
            height: 18px;
        }
        QProgressBar::chunk {
            background-color: #2563EB;
            border-radius: 5px;
        }
"""

def apply_app_theme(app):
    app.setStyle("Fusion")
    
    # Configure consistent high-contrast Light Palette (prevents Windows Dark Mode issues)
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#F1F5F9"))
    palette.setColor(QPalette.WindowText, QColor("#0F172A"))
    palette.setColor(QPalette.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.AlternateBase, QColor("#F8FAFC"))
    palette.setColor(QPalette.ToolTipBase, QColor("#0F172A"))
    palette.setColor(QPalette.ToolTipText, QColor("#FFFFFF"))
    palette.setColor(QPalette.Text, QColor("#0F172A"))
    palette.setColor(QPalette.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ButtonText, QColor("#0F172A"))
    palette.setColor(QPalette.BrightText, QColor("#DC2626"))
    palette.setColor(QPalette.Highlight, QColor("#2563EB"))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)

    # Set application-wide font
    font = QFont("Segoe UI", 9)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET)

import traceback
from datetime import datetime
from PySide6.QtWidgets import QMessageBox

def exception_hook(exctype, value, tb):
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    sys.__excepthook__(exctype, value, tb)
    try:
        with open("crash_log.txt", "a", encoding="utf-8") as f:
            f.write(f"\n--- ERROR/CRASH REGISTRADO: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            f.write(error_msg)
            f.write("-" * 60 + "\n")
    except Exception:
        pass

    app = QApplication.instance()
    if app:
        try:
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle("Error Inesperado - SolidChecker")
            msg_box.setText("Ocurrió un error inesperado en la aplicación.")
            msg_box.setInformativeText(f"Se ha guardado un reporte técnico en 'crash_log.txt'.\n\nDetalle: {value}")
            msg_box.setDetailedText(error_msg)
            msg_box.exec()
        except Exception:
            pass

def main():
    sys.excepthook = exception_hook
    app = QApplication(sys.argv)
    apply_app_theme(app)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
