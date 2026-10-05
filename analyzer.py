import os
import tempfile
from solidworks_parser import parse_solidworks_file, extract_solidworks_from_zip

def analyze_submissions(downloaded_records, temp_dir):
    """
    Processes all downloaded files (including unzipping .zip archives if present),
    parses SolidWorks metadata, flags duplicate authors across different students,
    and detects damaged or corrupted files.
    """
    parsed_entries = []
    sw_extensions = {'.sldprt', '.sldasm', '.slddrw'}

    for record in downloaded_records:
        student_name = record['student_name']
        local_path = record['local_path']
        ext = record['extension']
        orig_filename = record['original_filename']

        if ext == '.zip':
            zip_out_dir = os.path.join(temp_dir, f"zip_out_{record['student_id']}")
            os.makedirs(zip_out_dir, exist_ok=True)
            extracted_paths = extract_solidworks_from_zip(local_path, zip_out_dir)

            if not extracted_paths:
                # Zip didn't contain any valid SolidWorks files or zip was corrupted
                parsed_entries.append({
                    'student_name': student_name,
                    'student_id': record['student_id'],
                    'filename': orig_filename,
                    'source_archive': None,
                    'file_path': local_path,
                    'extension': '.zip',
                    'author': 'N/A',
                    'last_saved_by': 'N/A',
                    'creation_date': None,
                    'last_saved_date': None,
                    'is_corrupted': True,
                    'error': 'El archivo ZIP no contiene piezas de SolidWorks (.sldprt, .sldasm, .slddrw) o está dañado.',
                    'is_duplicate': False,
                    'duplicate_students': [],
                    'status_msg': ''
                })

            for ex_path in extracted_paths:
                sw_data = parse_solidworks_file(ex_path)
                parsed_entries.append({
                    'student_name': student_name,
                    'student_id': record['student_id'],
                    'filename': os.path.basename(ex_path),
                    'source_archive': orig_filename,
                    'file_path': ex_path,
                    'extension': sw_data['extension'],
                    'author': sw_data['author'],
                    'last_saved_by': sw_data['last_saved_by'],
                    'creation_date': sw_data['creation_date'],
                    'last_saved_date': sw_data['last_saved_date'],
                    'file_hash': sw_data.get('file_hash'),
                    'is_corrupted': sw_data['is_corrupted'],
                    'error': sw_data['error'],
                    'is_duplicate': False,
                    'duplicate_students': [],
                    'status_msg': ''
                })
        elif ext in sw_extensions:
            sw_data = parse_solidworks_file(local_path)
            parsed_entries.append({
                'student_name': student_name,
                'student_id': record['student_id'],
                'filename': orig_filename,
                'source_archive': None,
                'file_path': local_path,
                'extension': sw_data['extension'],
                'author': sw_data['author'],
                'last_saved_by': sw_data['last_saved_by'],
                'creation_date': sw_data['creation_date'],
                'last_saved_date': sw_data['last_saved_date'],
                'file_hash': sw_data.get('file_hash'),
                'is_corrupted': sw_data['is_corrupted'],
                'error': sw_data['error'],
                'is_duplicate': False,
                'duplicate_students': [],
                'status_msg': ''
            })

    # Group by author and by file hash to detect duplicates across DIFFERENT students
    generic_authors = {
        'desconocido', 'unknown', 'solidworks', 'user', 'usuario',
        'administrator', 'admin', '', 'n/a', 'sin autor registrado',
        'no especificado', 'sin autor'
    }
    author_student_map = {}
    hash_student_map = {}

    for entry in parsed_entries:
        if entry['is_corrupted']:
            continue

        author = entry['author'].strip()
        norm_author = author.lower()
        if norm_author and norm_author not in generic_authors:
            if norm_author not in author_student_map:
                author_student_map[norm_author] = set()
            author_student_map[norm_author].add(entry['student_name'])

        fhash = entry.get('file_hash')
        if fhash:
            if fhash not in hash_student_map:
                hash_student_map[fhash] = set()
            hash_student_map[fhash].add(entry['student_name'])

    duplicate_authors = {auth for auth, students in author_student_map.items() if len(students) > 1}
    duplicate_hashes = {h for h, students in hash_student_map.items() if len(students) > 1}

    corrupted_count = 0
    duplicate_count = 0

    for entry in parsed_entries:
        author = entry['author'].strip()
        norm_author = author.lower()
        fhash = entry.get('file_hash')

        if entry['is_corrupted']:
            corrupted_count += 1
            entry['status_msg'] = f"💥 ARCHIVO DAÑADO / CORRUPTO: {entry['error']}"
        elif fhash in duplicate_hashes:
            duplicate_count += 1
            all_students = sorted(list(hash_student_map[fhash]))
            other_students = [s for s in all_students if s != entry['student_name']]
            entry['is_duplicate'] = True
            entry['duplicate_students'] = other_students
            entry['status_msg'] = f"⚠️ COPIA EXACTA: Archivo binario idéntico al de {', '.join(other_students)}"
        elif norm_author in duplicate_authors:
            duplicate_count += 1
            all_students = sorted(list(author_student_map[norm_author]))
            other_students = [s for s in all_students if s != entry['student_name']]
            entry['is_duplicate'] = True
            entry['duplicate_students'] = other_students
            entry['status_msg'] = f"⚠️ COINCIDENCIA DE AUTOR: '{author}' también en entrega de {', '.join(other_students)}"
        else:
            ver = entry.get('last_saved_by') or 'SolidWorks'
            entry['status_msg'] = f"✅ OK ({ver})"

    return {
        'results': parsed_entries,
        'total_count': len(parsed_entries),
        'corrupted_count': corrupted_count,
        'duplicate_count': duplicate_count,
        'duplicate_summary': {
            auth: sorted(list(students))
            for auth, students in author_student_map.items()
            if len(students) > 1
        }
    }
