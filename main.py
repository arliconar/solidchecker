import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from gui import MainWindow

def main():
    app = QApplication(sys.argv)
    
    # Set application-wide font
    font = QFont("Segoe UI", 9)
    app.setFont(font)

    # Simple clean styling sheet
    app.setStyleSheet("""
        QMainWindow {
            background-color: #F8F9FA;
        }
        QGroupBox {
            font-weight: bold;
            border: 1px solid #CED4DA;
            border-radius: 6px;
            margin-top: 6px;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }
        QPushButton {
            border-radius: 4px;
            border: 1px solid #BDC3C7;
            padding: 6px 12px;
            background-color: #FFFFFF;
        }
        QPushButton:hover {
            background-color: #EAECEE;
        }
        QTableWidget {
            border: 1px solid #CED4DA;
            gridline-color: #E0E0E0;
            background-color: #FFFFFF;
        }
        QHeaderView::section {
            background-color: #F1F3F5;
            font-weight: bold;
            padding: 6px;
            border: 1px solid #CED4DA;
        }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
