import os
import sys
import csv
import tempfile
import openpyxl
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QCheckBox, QProgressBar, QMessageBox,
    QFileDialog, QGroupBox, QFrame, QSplitter
)

from classroom_api import ClassroomManager
from analyzer import analyze_submissions

def _format_date(dt):
    if not dt:
        return "N/A"
    if hasattr(dt, "strftime"):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)


class AuthWorker(QThread):
    finished_signal = Signal(bool, object, str)

    def __init__(self, manager):
        super().__init__()
        self.manager = manager

    def run(self):
        try:
            user_info = self.manager.login()
            self.finished_signal.emit(True, user_info, "")
        except Exception as e:
            self.finished_signal.emit(False, None, str(e))


class CoursesWorker(QThread):
    finished_signal = Signal(bool, list, str)

    def __init__(self, manager):
        super().__init__()
        self.manager = manager

    def run(self):
        try:
            courses = self.manager.get_courses()
            self.finished_signal.emit(True, courses, "")
        except Exception as e:
            self.finished_signal.emit(False, [], str(e))


class CourseworkWorker(QThread):
    finished_signal = Signal(bool, list, str)

    def __init__(self, manager, course_id):
        super().__init__()
        self.manager = manager
        self.course_id = course_id

    def run(self):
        try:
            coursework = self.manager.get_coursework(self.course_id)
            self.finished_signal.emit(True, coursework, "")
        except Exception as e:
            self.finished_signal.emit(False, [], str(e))


class AnalyzeWorker(QThread):
    progress_signal = Signal(int, int, str)
    finished_signal = Signal(bool, dict, str)

    def __init__(self, manager, course_id, coursework_id):
        super().__init__()
        self.manager = manager
        self.course_id = course_id
        self.coursework_id = coursework_id

    def run(self):
        try:
            temp_dir = tempfile.mkdtemp(prefix="solidchecker_")
            
            def progress_callback(curr, tot, msg):
                self.progress_signal.emit(curr, tot, msg)

            records = self.manager.fetch_submissions(
                self.course_id,
                self.coursework_id,
                temp_dir,
                progress_callback=progress_callback
            )

            self.progress_signal.emit(len(records), len(records), "Analizando metadatos de archivos SolidWorks...")
            analysis_data = analyze_submissions(records, temp_dir)
            self.finished_signal.emit(True, analysis_data, "")
        except Exception as e:
            self.finished_signal.emit(False, {}, str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SolidChecker - Analizador de Autores SolidWorks (Google Classroom)")
        self.resize(1200, 800)

        self.manager = ClassroomManager()
        self.courses_data = []
        self.coursework_data = []
        self.all_results = []
        self.duplicate_summary = {}

        app = QApplication.instance()
        if app and not app.styleSheet():
            from main import apply_app_theme
            apply_app_theme(app)

        self._setup_ui()
        self._check_initial_auth()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # ------------------ HEADER / AUTH BAR ------------------
        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        header_frame.setFrameShape(QFrame.NoFrame)
        header_layout = QHBoxLayout(header_frame)

        title_label = QLabel("🛠️ SolidChecker")
        title_font = QFont("Segoe UI", 16, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #0F172A;")
        header_layout.addWidget(title_label)

        subtitle_label = QLabel("Analizador de metadatos de autoría y corrupción en entregas de SolidWorks")
        subtitle_label.setStyleSheet("color: #64748B; font-size: 13px;")
        header_layout.addWidget(subtitle_label)

        header_layout.addStretch()

        self.user_label = QLabel("Estado: No autenticado")
        self.user_label.setStyleSheet("font-weight: bold; color: #DC2626;")
        header_layout.addWidget(self.user_label)

        self.btn_auth = QPushButton("🔑 Iniciar Sesión con Google")
        self.btn_auth.setCursor(Qt.PointingHandCursor)
        self.btn_auth.clicked.connect(self._handle_auth_click)
        header_layout.addWidget(self.btn_auth)

        main_layout.addWidget(header_frame)

        # ------------------ SELECTION PANEL ------------------
        select_group = QGroupBox("Selección de Clase y Tarea")
        select_layout = QHBoxLayout(select_group)
        select_layout.setSpacing(12)

        lbl_course = QLabel("Clase / Curso:")
        self.combo_courses = QComboBox()
        self.combo_courses.setMinimumWidth(280)
        self.combo_courses.currentIndexChanged.connect(self._on_course_changed)

        lbl_work = QLabel("Tarea / Entrega:")
        self.combo_coursework = QComboBox()
        self.combo_coursework.setMinimumWidth(280)

        self.btn_analyze = QPushButton("📥 Descargar y Analizar")
        self.btn_analyze.setObjectName("btnAnalyze")
        self.btn_analyze.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.btn_analyze.setCursor(Qt.PointingHandCursor)
        self.btn_analyze.clicked.connect(self._start_analysis)
        self.btn_analyze.setEnabled(False)

        select_layout.addWidget(lbl_course)
        select_layout.addWidget(self.combo_courses)
        select_layout.addWidget(lbl_work)
        select_layout.addWidget(self.combo_coursework)
        select_layout.addWidget(self.btn_analyze)

        main_layout.addWidget(select_group)

        # ------------------ STATS & FILTER BAR ------------------
        filter_frame = QFrame()
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_stats = QLabel("Sumario: 0 analizados | ⚠️ 0 duplicados | 💥 0 dañados")
        self.lbl_stats.setFont(QFont("Segoe UI", 10, QFont.Bold))
        filter_layout.addWidget(self.lbl_stats)

        filter_layout.addStretch()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Buscar por alumno, pieza o autor...")
        self.search_box.setFixedWidth(220)
        self.search_box.textChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.search_box)

        self.chk_duplicates_only = QCheckBox("⚠️ Solo duplicados")
        self.chk_duplicates_only.stateChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.chk_duplicates_only)

        self.chk_corrupted_only = QCheckBox("💥 Solo dañados")
        self.chk_corrupted_only.stateChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.chk_corrupted_only)

        self.btn_export_excel = QPushButton("📊 Exportar Excel")
        self.btn_export_excel.setCursor(Qt.PointingHandCursor)
        self.btn_export_excel.clicked.connect(self._export_to_excel)
        self.btn_export_excel.setEnabled(False)
        filter_layout.addWidget(self.btn_export_excel)

        self.btn_export_csv = QPushButton("📄 Exportar CSV")
        self.btn_export_csv.setCursor(Qt.PointingHandCursor)
        self.btn_export_csv.clicked.connect(self._export_to_csv)
        self.btn_export_csv.setEnabled(False)
        filter_layout.addWidget(self.btn_export_csv)

        main_layout.addWidget(filter_frame)

        # ------------------ RESULTS TABLE ------------------
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Estado",
            "Alumno (Classroom)",
            "Pieza / Archivo",
            "Tipo",
            "Autor Registrado (SolidWorks)",
            "Último Guardado Por",
            "Fecha Creación",
            "Detalles / Diagnóstico"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Interactive)
        header.setSectionResizeMode(5, QHeaderView.Interactive)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 170)
        self.table.setColumnWidth(2, 190)
        self.table.setColumnWidth(4, 220)
        self.table.setColumnWidth(5, 170)
        self.table.setAlternatingRowColors(True)

        main_layout.addWidget(self.table)

        # ------------------ PROGRESS BAR & STATUS ------------------
        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.lbl_status = QLabel("Listo")
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.lbl_status)

        main_layout.addLayout(progress_layout)

    def _check_initial_auth(self):
        if self.manager.is_authenticated():
            user_info = self.manager.get_user_info()
            if user_info:
                email = user_info.get('email', 'Usuario')
                self.user_label.setText(f"Conectado: {email}")
                self.user_label.setStyleSheet("font-weight: bold; color: #2E7D32;")
                self.btn_auth.setText("🚪 Cerrar Sesión")
                self._load_courses()
            else:
                self._prompt_login()
        else:
            self.user_label.setText("Estado: No autenticado")
            self.user_label.setStyleSheet("font-weight: bold; color: #D32F2F;")
            self.btn_auth.setText("🔑 Iniciar Sesión con Google")

    def _handle_auth_click(self):
        if self.manager.is_authenticated():
            self.manager.logout()
            self.user_label.setText("Estado: No autenticado")
            self.user_label.setStyleSheet("font-weight: bold; color: #D32F2F;")
            self.btn_auth.setText("🔑 Iniciar Sesión con Google")
            self.combo_courses.clear()
            self.combo_coursework.clear()
            self.btn_analyze.setEnabled(False)
        else:
            self._prompt_login()

    def _prompt_login(self):
        if not self.manager.is_credentials_file_present():
            QMessageBox.warning(
                self,
                "Falta el archivo credentials.json",
                "Para conectarte a Google Classroom, necesitas el archivo 'credentials.json' "
                "(OAuth 2.0 Client ID para aplicaciones de escritorio).\n\n"
                "Por favor, coloca el archivo 'credentials.json' en la misma carpeta de la aplicación."
            )
            return

        self.lbl_status.setText("Iniciando sesión en el navegador...")
        self.btn_auth.setEnabled(False)

        self.auth_worker = AuthWorker(self.manager)
        self.auth_worker.finished_signal.connect(self._on_auth_finished)
        self.auth_worker.start()

    def _on_auth_finished(self, success, user_info, error_msg):
        self.btn_auth.setEnabled(True)
        if success and user_info:
            email = user_info.get('email', 'Usuario')
            self.user_label.setText(f"Conectado: {email}")
            self.user_label.setStyleSheet("font-weight: bold; color: #2E7D32;")
            self.btn_auth.setText("🚪 Cerrar Sesión")
            self.lbl_status.setText("Sesión iniciada con éxito.")
            self._load_courses()
        else:
            self.lbl_status.setText(f"Error de autenticación: {error_msg}")
            QMessageBox.critical(self, "Error de Iniciar Sesión", f"No se pudo iniciar sesión:\n{error_msg}")

    def _load_courses(self):
        self.lbl_status.setText("Cargando clases de Google Classroom...")
        self.combo_courses.clear()
        self.combo_coursework.clear()

        self.courses_worker = CoursesWorker(self.manager)
        self.courses_worker.finished_signal.connect(self._on_courses_loaded)
        self.courses_worker.start()

    def _on_courses_loaded(self, success, courses, error_msg):
        if success:
            self.courses_data = courses
            self.combo_courses.clear()
            if not courses:
                self.lbl_status.setText("No se encontraron clases activas en tu cuenta.")
                return

            for c in courses:
                display = f"{c['name']} ({c['section']})" if c['section'] else c['name']
                self.combo_courses.addItem(display, c['id'])

            self.lbl_status.setText(f"Se cargaron {len(courses)} clases.")
        else:
            self.lbl_status.setText("Error cargando clases.")
            QMessageBox.critical(self, "Error", f"No se pudieron obtener las clases:\n{error_msg}")

    def _on_course_changed(self, index):
        if index < 0 or not self.courses_data:
            return

        course_id = self.combo_courses.itemData(index)
        if not course_id:
            return

        self.lbl_status.setText("Cargando tareas de la clase...")
        self.combo_coursework.clear()
        self.btn_analyze.setEnabled(False)

        self.coursework_worker = CourseworkWorker(self.manager, course_id)
        self.coursework_worker.finished_signal.connect(self._on_coursework_loaded)
        self.coursework_worker.start()

    def _on_coursework_loaded(self, success, coursework, error_msg):
        if success:
            self.coursework_data = coursework
            self.combo_coursework.clear()
            if not coursework:
                self.lbl_status.setText("Esta clase no tiene tareas creadas.")
                return

            for cw in coursework:
                self.combo_coursework.addItem(cw['title'], cw['id'])

            self.btn_analyze.setEnabled(True)
            self.lbl_status.setText(f"Se cargaron {len(coursework)} tareas.")
        else:
            self.lbl_status.setText("Error cargando tareas.")
            QMessageBox.critical(self, "Error", f"No se pudieron obtener las tareas:\n{error_msg}")

    def _start_analysis(self):
        course_index = self.combo_courses.currentIndex()
        work_index = self.combo_coursework.currentIndex()

        if course_index < 0 or work_index < 0:
            return

        course_id = self.combo_courses.itemData(course_index)
        work_id = self.combo_coursework.itemData(work_index)

        self.btn_analyze.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("Iniciando descarga y análisis...")

        self.analyze_worker = AnalyzeWorker(self.manager, course_id, work_id)
        self.analyze_worker.progress_signal.connect(self._on_analysis_progress)
        self.analyze_worker.finished_signal.connect(self._on_analysis_finished)
        self.analyze_worker.start()

    def _on_analysis_progress(self, current, total, status_text):
        if total > 0:
            val = int((current / total) * 100)
            self.progress_bar.setValue(val)
        self.lbl_status.setText(status_text)

    def _on_analysis_finished(self, success, analysis_data, error_msg):
        self.btn_analyze.setEnabled(True)
        self.progress_bar.setVisible(False)

        if success:
            self.all_results = analysis_data.get('results', [])
            self.duplicate_summary = analysis_data.get('duplicate_summary', {})
            self._render_results_table(self.all_results)
            self.btn_export_excel.setEnabled(len(self.all_results) > 0)
            self.btn_export_csv.setEnabled(len(self.all_results) > 0)
            self.lbl_status.setText("Análisis completado exitosamente.")
        else:
            self.lbl_status.setText("Error durante el análisis.")
            QMessageBox.critical(self, "Error de Análisis", f"Ocurrió un error procesando la tarea:\n{error_msg}")

    def _render_results_table(self, results):
        self.table.setRowCount(0)

        duplicates_count = sum(1 for r in results if r.get('is_duplicate'))
        corrupted_count = sum(1 for r in results if r.get('is_corrupted'))
        total_count = len(results)

        self.lbl_stats.setText(
            f"Sumario: {total_count} analizados | ⚠️ {duplicates_count} duplicados | 💥 {corrupted_count} dañados/corruptos"
        )

        for row_idx, r in enumerate(results):
            self.table.insertRow(row_idx)

            # Estado Icon / Label
            if r.get('is_corrupted'):
                status_text = "💥 DAÑADO"
            elif r.get('is_duplicate'):
                status_text = "⚠️ DUPLICADO"
            else:
                status_text = "✅ OK"

            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignCenter)

            student_item = QTableWidgetItem(r['student_name'])
            filename_item = QTableWidgetItem(r['filename'])
            ext_item = QTableWidgetItem(r['extension'].upper())

            author_item = QTableWidgetItem(r['author'])
            last_by_item = QTableWidgetItem(r['last_saved_by'])

            created_str = _format_date(r.get('creation_date'))
            date_item = QTableWidgetItem(created_str)

            msg_item = QTableWidgetItem(r['status_msg'])

            # Apply custom row formatting
            if r.get('is_corrupted'):
                bg_color = QColor("#FFF7ED") # Soft orange background
                fg_color = QColor("#C2410C") # Dark orange text
                for item in (status_item, student_item, filename_item, ext_item, author_item, last_by_item, date_item, msg_item):
                    item.setBackground(bg_color)
                    item.setForeground(fg_color)
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
            elif r.get('is_duplicate'):
                bg_color = QColor("#FEF2F2") # Soft red background
                fg_color = QColor("#B91C1C") # Dark red text
                for item in (status_item, student_item, filename_item, ext_item, author_item, last_by_item, date_item, msg_item):
                    item.setBackground(bg_color)
                    item.setForeground(fg_color)
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
            else:
                bg_color = QColor("#F0FDF4") # Soft green background
                fg_color = QColor("#15803D") # Dark green text
                for item in (status_item, student_item, filename_item, ext_item, author_item, last_by_item, date_item, msg_item):
                    item.setBackground(bg_color)
                    item.setForeground(fg_color)

            self.table.setItem(row_idx, 0, status_item)
            self.table.setItem(row_idx, 1, student_item)
            self.table.setItem(row_idx, 2, filename_item)
            self.table.setItem(row_idx, 3, ext_item)
            self.table.setItem(row_idx, 4, author_item)
            self.table.setItem(row_idx, 5, last_by_item)
            self.table.setItem(row_idx, 6, date_item)
            self.table.setItem(row_idx, 7, msg_item)

    def _apply_filters(self):
        query = self.search_box.text().lower().strip()
        duplicates_only = self.chk_duplicates_only.isChecked()
        corrupted_only = self.chk_corrupted_only.isChecked()

        filtered = []
        for r in self.all_results:
            if duplicates_only and not r.get('is_duplicate'):
                continue
            if corrupted_only and not r.get('is_corrupted'):
                continue

            if query:
                search_target = f"{r['student_name']} {r['filename']} {r['author']} {r['last_saved_by']} {r['status_msg']}".lower()
                if query not in search_target:
                    continue

            filtered.append(r)

        self._render_results_table(filtered)

    def _export_to_excel(self):
        if not self.all_results:
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Guardar reporte Excel", "reporte_solidchecker.xlsx", "Excel Files (*.xlsx)")
        if not file_path:
            return

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Metadatos SolidWorks"

        headers = [
            "Estado", "Alumno (Classroom)", "Pieza / Archivo", "Tipo",
            "Autor Registrado (SolidWorks)", "Último Guardado Por", "Fecha Creación", "Detalles / Diagnóstico"
        ]
        ws.append(headers)

        for r in self.all_results:
            created_str = _format_date(r.get('creation_date'))
            if r.get('is_corrupted'):
                st = "DAÑADO / CORRUPTO"
            elif r.get('is_duplicate'):
                st = "DUPLICADO"
            else:
                st = "OK"

            ws.append([
                st,
                r['student_name'],
                r['filename'],
                r['extension'].upper(),
                r['author'],
                r['last_saved_by'],
                created_str,
                r['status_msg']
            ])

        try:
            wb.save(file_path)
            QMessageBox.information(self, "Éxito", f"Reporte exportado correctamente a:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar", f"No se pudo guardar el archivo Excel:\n{e}")

    def _export_to_csv(self):
        if not self.all_results:
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Guardar reporte CSV", "reporte_solidchecker.csv", "CSV Files (*.csv)")
        if not file_path:
            return

        try:
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Estado", "Alumno", "Archivo", "Tipo",
                    "Autor_SolidWorks", "Ultimo_Guardado_Por", "Fecha_Creacion", "Detalles"
                ])
                for r in self.all_results:
                    created_str = _format_date(r.get('creation_date'))
                    if r.get('is_corrupted'):
                        st = "DAÑADO / CORRUPTO"
                    elif r.get('is_duplicate'):
                        st = "DUPLICADO"
                    else:
                        st = "OK"

                    writer.writerow([
                        st,
                        r['student_name'],
                        r['filename'],
                        r['extension'].upper(),
                        r['author'],
                        r['last_saved_by'],
                        created_str,
                        r['status_msg']
                    ])
            QMessageBox.information(self, "Éxito", f"Reporte CSV exportado correctamente a:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar", f"No se pudo guardar el archivo CSV:\n{e}")

if __name__ == "__main__":
    from main import main
    main()

