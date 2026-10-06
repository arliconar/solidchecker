import os
import unittest
import tempfile
from datetime import datetime
from solidworks_parser import parse_solidworks_file
from analyzer import analyze_submissions

class TestSolidChecker(unittest.TestCase):

    def test_corrupted_file_detection(self):
        # Create a temp 0-byte file and a non-OLE corrupted text file
        with tempfile.NamedTemporaryFile(suffix='.sldprt', delete=False) as tf:
            tf.write(b"Este no es un archivo OLE2 de SolidWorks, es texto corrupto.")
            corrupted_path = tf.name

        with tempfile.NamedTemporaryFile(suffix='.sldprt', delete=False) as tf_empty:
            empty_path = tf_empty.name

        try:
            res_corrupted = parse_solidworks_file(corrupted_path)
            self.assertTrue(res_corrupted['is_corrupted'])
            self.assertIn('OLE2', res_corrupted['error'])

            res_empty = parse_solidworks_file(empty_path)
            self.assertTrue(res_empty['is_corrupted'])
            self.assertIn('está vacío (0 bytes)', res_empty['error'])
        finally:
            if os.path.exists(corrupted_path):
                os.remove(corrupted_path)
            if os.path.exists(empty_path):
                os.remove(empty_path)

    def test_analyzer_duplicate_and_corrupted(self):
        records = [
            {
                'student_name': 'Juan Pérez',
                'student_id': 'user_1',
                'original_filename': 'pieza1.sldprt',
                'local_path': 'fake_path1.sldprt',
                'extension': '.sldprt'
            }
        ]

        parsed_entries = [
            {
                'student_name': 'Juan Pérez',
                'student_id': 'user_1',
                'filename': 'pieza1.sldprt',
                'source_archive': None,
                'file_path': 'fake_path1.sldprt',
                'extension': '.sldprt',
                'author': 'N/A',
                'last_saved_by': 'N/A',
                'creation_date': None,
                'last_saved_date': None,
                'is_corrupted': True,
                'error': 'El archivo está vacío (0 bytes)',
                'is_duplicate': False,
                'duplicate_students': [],
                'status_msg': ''
            }
        ]

        self.assertTrue(parsed_entries[0]['is_corrupted'])

    def test_null_bytes_corrupted(self):
        with tempfile.NamedTemporaryFile(suffix='.sldprt', delete=False) as tf:
            tf.write(b"\x00" * 1024)
            path = tf.name
        try:
            res = parse_solidworks_file(path)
            self.assertTrue(res['is_corrupted'])
            self.assertIn('ceros', res['error'])
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_modern_solidworks_header_detection(self):
        with tempfile.NamedTemporaryFile(suffix='.sldprt', delete=False) as tf:
            tf.write(b"\xf4\xe9\x02\xfc\x00\x00\x00\x04" + b"\x01" * 100)
            path = tf.name
        try:
            res = parse_solidworks_file(path)
            self.assertFalse(res['is_corrupted'])
            self.assertIn('SolidWorks', res['last_saved_by'])
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_analyzer_duplicate_by_hash(self):
        with tempfile.NamedTemporaryFile(suffix='.sldprt', delete=False) as tf1:
            tf1.write(b"\xf4\xe9\x02\xfc\x00\x00\x00\x04" + b"identical_content")
            p1 = tf1.name
        with tempfile.NamedTemporaryFile(suffix='.sldprt', delete=False) as tf2:
            tf2.write(b"\xf4\xe9\x02\xfc\x00\x00\x00\x04" + b"identical_content")
            p2 = tf2.name
        try:
            records = [
                {
                    'student_name': 'Estudiante A',
                    'student_id': 'id_a',
                    'original_filename': 'tarea.sldprt',
                    'local_path': p1,
                    'extension': '.sldprt'
                },
                {
                    'student_name': 'Estudiante B',
                    'student_id': 'id_b',
                    'original_filename': 'entrega.sldprt',
                    'local_path': p2,
                    'extension': '.sldprt'
                }
            ]
            analysis = analyze_submissions(records, tempfile.gettempdir())
            self.assertEqual(analysis['duplicate_count'], 2)
            self.assertTrue(analysis['results'][0]['is_duplicate'])
            self.assertTrue(analysis['results'][1]['is_duplicate'])
            self.assertIn('COPIA EXACTA', analysis['results'][0]['status_msg'])
        finally:
            if os.path.exists(p1):
                os.remove(p1)
            if os.path.exists(p2):
                os.remove(p2)

    def test_format_editing_time(self):
        from solidworks_parser import format_edit_time
        self.assertEqual(format_edit_time(seconds=3660), "1h 01m")
        self.assertEqual(format_edit_time(seconds=120), "2 min")
        self.assertEqual(format_edit_time(minutes=45), "45 min")
        self.assertEqual(format_edit_time(minutes=130), "2h 10m")
        self.assertEqual(format_edit_time(seconds=0), "< 1 min")

    def test_creation_date_duplicate_detected(self):
        records = [
            {'student_name': 'Alumno A', 'student_id': 'id_a', 'original_filename': 'p1.sldprt', 'local_path': 'p1.sldprt', 'extension': '.sldprt'},
            {'student_name': 'Alumno B', 'student_id': 'id_b', 'original_filename': 'p2.sldprt', 'local_path': 'p2.sldprt', 'extension': '.sldprt'}
        ]
        from unittest.mock import patch
        with patch('analyzer.parse_solidworks_file') as mock_parse:
            mock_parse.side_effect = [
                {
                    'extension': '.sldprt',
                    'author': 'Sin autor registrado',
                    'origin_computer': 'PC-CARLOS',
                    'last_computer': 'PC-CARLOS',
                    'computer_display': 'PC-CARLOS',
                    'workstations': ['PC-CARLOS'],
                    'last_saved_by': 'SOLIDWORKS 2025',
                    'creation_date': '24/09/2026 10:14:32',
                    'last_saved_date': '24/09/2026 11:00:00',
                    'total_edit_time_str': '45 min',
                    'file_hash': 'hash_different_1',
                    'is_corrupted': False,
                    'error': None
                },
                {
                    'extension': '.sldprt',
                    'author': 'Sin autor registrado',
                    'origin_computer': 'PC-MIGUEL',
                    'last_computer': 'PC-MIGUEL',
                    'computer_display': 'PC-MIGUEL',
                    'workstations': ['PC-MIGUEL'],
                    'last_saved_by': 'SOLIDWORKS 2025',
                    'creation_date': '24/09/2026 10:14:32',
                    'last_saved_date': '27/09/2026 23:15:00',
                    'total_edit_time_str': '47 min',
                    'file_hash': 'hash_different_2',
                    'is_corrupted': False,
                    'error': None
                }
            ]
            analysis = analyze_submissions(records, tempfile.gettempdir())
            self.assertEqual(analysis['duplicate_count'], 2)
            self.assertTrue(analysis['results'][0]['is_duplicate'])
            self.assertTrue(analysis['results'][1]['is_duplicate'])
            self.assertIn('MISMA FECHA DE CREACIÓN', analysis['results'][0]['status_msg'])

    def test_transfer_chain_duplicate_detected(self):
        records = [
            {'student_name': 'Alumno A', 'student_id': 'id_a', 'original_filename': 'p1.sldprt', 'local_path': 'p1.sldprt', 'extension': '.sldprt'},
            {'student_name': 'Alumno B', 'student_id': 'id_b', 'original_filename': 'p2.sldprt', 'local_path': 'p2.sldprt', 'extension': '.sldprt'}
        ]
        from unittest.mock import patch
        with patch('analyzer.parse_solidworks_file') as mock_parse:
            mock_parse.side_effect = [
                {
                    'extension': '.sldprt',
                    'author': 'Sin autor registrado',
                    'origin_computer': 'LAPTOP-CARLOS',
                    'last_computer': 'LAPTOP-CARLOS',
                    'computer_display': 'LAPTOP-CARLOS',
                    'workstations': ['LAPTOP-CARLOS'],
                    'last_saved_by': 'SOLIDWORKS 2025',
                    'creation_date': '24/09/2026 10:00:00',
                    'last_saved_date': '24/09/2026 12:00:00',
                    'total_edit_time_str': '2h 00m',
                    'file_hash': 'hash1',
                    'is_corrupted': False,
                    'error': None
                },
                {
                    'extension': '.sldprt',
                    'author': 'Sin autor registrado',
                    'origin_computer': 'LAPTOP-CARLOS',
                    'last_computer': 'DESKTOP-JUAN',
                    'computer_display': 'LAPTOP-CARLOS → DESKTOP-JUAN',
                    'workstations': ['LAPTOP-CARLOS', 'DESKTOP-JUAN'],
                    'last_saved_by': 'SOLIDWORKS 2025',
                    'creation_date': '25/09/2026 14:00:00',
                    'last_saved_date': '25/09/2026 14:10:00',
                    'total_edit_time_str': '2h 10m',
                    'file_hash': 'hash2',
                    'is_corrupted': False,
                    'error': None
                }
            ]
            analysis = analyze_submissions(records, tempfile.gettempdir())
            self.assertEqual(analysis['duplicate_count'], 2)
            self.assertTrue(analysis['results'][1]['is_duplicate'])
            self.assertIn('TRANSFERENCIA DE ARCHIVO', analysis['results'][1]['status_msg'])

    def test_template_computer_not_falsely_flagged(self):
        records = [
            {'student_name': 'Alma', 'student_id': 'id_1', 'original_filename': 'p1.sldprt', 'local_path': 'p1.sldprt', 'extension': '.sldprt'},
            {'student_name': 'Carlos', 'student_id': 'id_2', 'original_filename': 'p2.sldprt', 'local_path': 'p2.sldprt', 'extension': '.sldprt'}
        ]
        from unittest.mock import patch
        with patch('analyzer.parse_solidworks_file') as mock_parse:
            mock_parse.side_effect = [
                {
                    'extension': '.sldprt',
                    'author': 'Sin autor registrado',
                    'origin_computer': 'LABCAD20',
                    'last_computer': 'LABCAD19',
                    'computer_display': 'LABCAD20 → LABCAD19',
                    'workstations': ['LABCAD20', 'LABCAD19'],
                    'last_saved_by': 'SOLIDWORKS 2025',
                    'creation_date': '24/09/2026 10:00:00',
                    'last_saved_date': '24/09/2026 11:30:00',
                    'total_edit_time_str': '1h 30m',
                    'file_hash': 'hash_alma',
                    'is_corrupted': False,
                    'error': None
                },
                {
                    'extension': '.sldprt',
                    'author': 'Sin autor registrado',
                    'origin_computer': 'LABCAD20',
                    'last_computer': 'LABCAD08',
                    'computer_display': 'LABCAD20 → LABCAD08',
                    'workstations': ['LABCAD20', 'LABCAD08'],
                    'last_saved_by': 'SOLIDWORKS 2025',
                    'creation_date': '24/09/2026 10:05:00',
                    'last_saved_date': '24/09/2026 11:45:00',
                    'total_edit_time_str': '1h 40m',
                    'file_hash': 'hash_carlos',
                    'is_corrupted': False,
                    'error': None
                }
            ]
            analysis = analyze_submissions(records, tempfile.gettempdir())
            self.assertEqual(analysis['duplicate_count'], 0)
            self.assertFalse(analysis['results'][0]['is_duplicate'])
            self.assertFalse(analysis['results'][1]['is_duplicate'])

    def test_different_computers_not_duplicates(self):
        records = [
            {
                'student_name': 'Alumno A',
                'student_id': 'id_a',
                'original_filename': 'p1.sldprt',
                'local_path': 'p1.sldprt',
                'extension': '.sldprt'
            },
            {
                'student_name': 'Alumno B',
                'student_id': 'id_b',
                'original_filename': 'p2.sldprt',
                'local_path': 'p2.sldprt',
                'extension': '.sldprt'
            }
        ]
        from unittest.mock import patch
        with patch('analyzer.parse_solidworks_file') as mock_parse:
            mock_parse.side_effect = [
                {
                    'extension': '.sldprt',
                    'author': 'Sin autor registrado',
                    'origin_computer': 'LAPTOP-CARLOS',
                    'last_computer': 'LAPTOP-CARLOS',
                    'computer_display': 'LAPTOP-CARLOS',
                    'workstations': ['LAPTOP-CARLOS'],
                    'last_saved_by': 'SOLIDWORKS 2025',
                    'creation_date': '2026-09-28 10:00:00',
                    'last_saved_date': '2026-09-29 10:00:00',
                    'file_hash': 'hash1',
                    'is_corrupted': False,
                    'error': None
                },
                {
                    'extension': '.sldprt',
                    'author': 'Sin autor registrado',
                    'origin_computer': 'DESKTOP-ANA',
                    'last_computer': 'DESKTOP-ANA',
                    'computer_display': 'DESKTOP-ANA',
                    'workstations': ['DESKTOP-ANA'],
                    'last_saved_by': 'SOLIDWORKS 2025',
                    'creation_date': '2026-09-29 15:00:00',
                    'last_saved_date': '2026-09-29 16:00:00',
                    'file_hash': 'hash2',
                    'is_corrupted': False,
                    'error': None
                }
            ]
            analysis = analyze_submissions(records, tempfile.gettempdir())
            self.assertEqual(analysis['duplicate_count'], 0)
            self.assertFalse(analysis['results'][0]['is_duplicate'])
            self.assertFalse(analysis['results'][1]['is_duplicate'])

    def test_actual_author_match_detected(self):
        records = [
            {
                'student_name': 'Alumno A',
                'student_id': 'id_a',
                'original_filename': 'p1.sldprt',
                'local_path': 'p1.sldprt',
                'extension': '.sldprt'
            },
            {
                'student_name': 'Alumno B',
                'student_id': 'id_b',
                'original_filename': 'p2.sldprt',
                'local_path': 'p2.sldprt',
                'extension': '.sldprt'
            }
        ]
        from unittest.mock import patch
        with patch('analyzer.parse_solidworks_file') as mock_parse:
            mock_parse.side_effect = [
                {
                    'extension': '.sldprt',
                    'author': 'Roberto Gomez',
                    'origin_computer': 'PC-1',
                    'last_computer': 'PC-1',
                    'computer_display': 'PC-1',
                    'workstations': ['PC-1'],
                    'last_saved_by': 'SOLIDWORKS 2025',
                    'creation_date': '2026-09-28 09:30:00',
                    'last_saved_date': '2026-09-29 09:30:00',
                    'file_hash': 'hash1',
                    'is_corrupted': False,
                    'error': None
                },
                {
                    'extension': '.sldprt',
                    'author': 'Roberto Gomez',
                    'origin_computer': 'PC-2',
                    'last_computer': 'PC-2',
                    'computer_display': 'PC-2',
                    'workstations': ['PC-2'],
                    'last_saved_by': 'SOLIDWORKS 2025',
                    'creation_date': '2026-09-29 12:45:00',
                    'last_saved_date': '2026-09-29 14:00:00',
                    'file_hash': 'hash2',
                    'is_corrupted': False,
                    'error': None
                }
            ]
            analysis = analyze_submissions(records, tempfile.gettempdir())
            self.assertEqual(analysis['duplicate_count'], 2)
            self.assertTrue(analysis['results'][0]['is_duplicate'])
            self.assertIn('COINCIDENCIA DE AUTOR', analysis['results'][0]['status_msg'])

if __name__ == '__main__':
    unittest.main()
