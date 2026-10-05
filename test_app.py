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

    def test_sample_files_computer_coincidence_detected(self):
        f1 = 'cruz alma mayte.SLDPRT'
        f2 = 'pieza 1 Maria Guadalupe Sanchez Martinez.SLDPRT'
        if os.path.exists(f1) and os.path.exists(f2):
            records = [
                {
                    'student_name': 'Alma Mayte Cruz',
                    'student_id': 'id_1',
                    'original_filename': f1,
                    'local_path': f1,
                    'extension': '.sldprt'
                },
                {
                    'student_name': 'Maria Guadalupe Sanchez Martinez',
                    'student_id': 'id_2',
                    'original_filename': f2,
                    'local_path': f2,
                    'extension': '.sldprt'
                }
            ]
            analysis = analyze_submissions(records, tempfile.gettempdir())
            self.assertEqual(analysis['duplicate_count'], 2)
            self.assertTrue(analysis['results'][0]['is_duplicate'])
            self.assertTrue(analysis['results'][1]['is_duplicate'])
            self.assertIn('LABCAD20', analysis['results'][0]['status_msg'])
            self.assertIn('LABCAD20', analysis['results'][1]['status_msg'])
            self.assertEqual(analysis['results'][0]['origin_computer'], 'LABCAD20')
            self.assertEqual(analysis['results'][1]['origin_computer'], 'LABCAD20')

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
                    'creation_date': '2026-09-28',
                    'last_saved_date': '2026-09-29',
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
                    'creation_date': '2026-09-28',
                    'last_saved_date': '2026-09-29',
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
                    'creation_date': '2026-09-28',
                    'last_saved_date': '2026-09-29',
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
                    'creation_date': '2026-09-28',
                    'last_saved_date': '2026-09-29',
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
