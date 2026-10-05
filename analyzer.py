import os
import tempfile
from solidworks_parser import parse_solidworks_file, extract_solidworks_from_zip, is_machine_or_generic_name

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
                    'origin_computer': 'N/A',
                    'last_computer': 'N/A',
                    'computer_display': 'N/A',
                    'computer_name': 'N/A',
                    'workstations': [],
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
                    'origin_computer': sw_data.get('origin_computer', 'Desconocido'),
                    'last_computer': sw_data.get('last_computer', 'Desconocido'),
                    'computer_display': sw_data.get('computer_display', 'Desconocido'),
                    'computer_name': sw_data.get('origin_computer', 'Desconocido'),
                    'workstations': sw_data.get('workstations', []),
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
                'origin_computer': sw_data.get('origin_computer', 'Desconocido'),
                'last_computer': sw_data.get('last_computer', 'Desconocido'),
                'computer_display': sw_data.get('computer_display', 'Desconocido'),
                'computer_name': sw_data.get('origin_computer', 'Desconocido'),
                'workstations': sw_data.get('workstations', []),
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

    # Group by Computer, File Hash, and Author across DIFFERENT students
    origin_comp_student_map = {}
    all_comp_student_map = {}
    author_student_map = {}
    hash_student_map = {}

    for entry in parsed_entries:
        if entry['is_corrupted']:
            continue

        orig_comp = entry.get('origin_computer', '').strip()
        norm_orig = orig_comp.lower()
        if norm_orig and norm_orig not in ('desconocido', 'unknown', 'n/a', 'none', ''):
            if norm_orig not in origin_comp_student_map:
                origin_comp_student_map[norm_orig] = set()
            origin_comp_student_map[norm_orig].add(entry['student_name'])

        workstations = entry.get('workstations', [])
        for ws in workstations:
            norm_ws = ws.strip().lower()
            if norm_ws and norm_ws not in ('desconocido', 'unknown', 'n/a', 'none', ''):
                if norm_ws not in all_comp_student_map:
                    all_comp_student_map[norm_ws] = set()
                all_comp_student_map[norm_ws].add(entry['student_name'])

        author = entry['author'].strip()
        norm_author = author.lower()
        if not is_machine_or_generic_name(author):
            if norm_author not in author_student_map:
                author_student_map[norm_author] = set()
            author_student_map[norm_author].add(entry['student_name'])

        fhash = entry.get('file_hash')
        if fhash:
            if fhash not in hash_student_map:
                hash_student_map[fhash] = set()
            hash_student_map[fhash].add(entry['student_name'])

    duplicate_origin_comps = {c for c, students in origin_comp_student_map.items() if len(students) > 1}
    duplicate_authors = {auth for auth, students in author_student_map.items() if len(students) > 1}
    duplicate_hashes = {h for h, students in hash_student_map.items() if len(students) > 1}

    corrupted_count = 0
    duplicate_count = 0

    for entry in parsed_entries:
        fhash = entry.get('file_hash')
        orig_comp = entry.get('origin_computer', '').strip()
        norm_orig = orig_comp.lower()
        author = entry['author'].strip()
        norm_author = author.lower()
        workstations = entry.get('workstations', [])

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
        elif norm_orig in duplicate_origin_comps:
            duplicate_count += 1
            all_students = sorted(list(origin_comp_student_map[norm_orig]))
            other_students = [s for s in all_students if s != entry['student_name']]
            entry['is_duplicate'] = True
            entry['duplicate_students'] = other_students
            if len(workstations) > 1:
                entry['status_msg'] = (
                    f"⚠️ MISMO EQUIPO: Creado en '{orig_comp}' (coincide con {', '.join(other_students)}) "
                    f"→ Guardado en '{entry['last_computer']}'"
                )
            else:
                entry['status_msg'] = f"⚠️ MISMA COMPUTADORA: Equipo '{orig_comp}' coincide con entrega de {', '.join(other_students)}"
        elif any(ws.strip().lower() in duplicate_origin_comps for ws in workstations):
            # One of the modification workstations is shared
            shared = [ws for ws in workstations if ws.strip().lower() in duplicate_origin_comps]
            shared_name = shared[0]
            all_students = sorted(list(origin_comp_student_map[shared_name.strip().lower()]))
            other_students = [s for s in all_students if s != entry['student_name']]
            duplicate_count += 1
            entry['is_duplicate'] = True
            entry['duplicate_students'] = other_students
            entry['status_msg'] = f"⚠️ HISTORIAL DE EQUIPO: Pasó por '{shared_name}' (coincide con {', '.join(other_students)})"
        elif norm_author in duplicate_authors:
            duplicate_count += 1
            all_students = sorted(list(author_student_map[norm_author]))
            other_students = [s for s in all_students if s != entry['student_name']]
            entry['is_duplicate'] = True
            entry['duplicate_students'] = other_students
            entry['status_msg'] = f"⚠️ COINCIDENCIA DE AUTOR: '{author}' también en entrega de {', '.join(other_students)}"
        else:
            comp_display = entry.get('computer_display')
            if comp_display and comp_display != 'Desconocido':
                entry['status_msg'] = f"✅ OK (Equipo: {comp_display})"
            else:
                ver = entry.get('last_saved_by') or 'SolidWorks'
                entry['status_msg'] = f"✅ OK ({ver})"

    return {
        'results': parsed_entries,
        'total_count': len(parsed_entries),
        'corrupted_count': corrupted_count,
        'duplicate_count': duplicate_count,
        'duplicate_summary': {
            'computers': {
                comp: sorted(list(students))
                for comp, students in origin_comp_student_map.items()
                if len(students) > 1
            },
            'authors': {
                auth: sorted(list(students))
                for auth, students in author_student_map.items()
                if len(students) > 1
            }
        }
    }
