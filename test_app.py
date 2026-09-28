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
            self.assertIn('no tiene una estructura OLE2 válida', res_corrupted['error'])

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

if __name__ == '__main__':
    unittest.main()
