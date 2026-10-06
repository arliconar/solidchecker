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
                    'total_edit_time': None,
                    'total_edit_time_str': 'N/A',
                    'user_path': None,
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
                    'user_path': sw_data.get('user_path'),
                    'total_edit_time': sw_data.get('total_edit_time'),
                    'total_edit_time_str': sw_data.get('total_edit_time_str', 'Desconocido'),
                    'last_saved_by': sw_data['last_saved_by'],
                    'sw_version': sw_data.get('sw_version'),
                    'sw_version_display': sw_data.get('sw_version_display', 'Desconocida'),
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
                'user_path': sw_data.get('user_path'),
                'total_edit_time': sw_data.get('total_edit_time'),
                'total_edit_time_str': sw_data.get('total_edit_time_str', 'Desconocido'),
                'last_saved_by': sw_data['last_saved_by'],
                'sw_version': sw_data.get('sw_version'),
                'sw_version_display': sw_data.get('sw_version_display', 'Desconocida'),
                'creation_date': sw_data['creation_date'],
                'last_saved_date': sw_data['last_saved_date'],
                'file_hash': sw_data.get('file_hash'),
                'is_corrupted': sw_data['is_corrupted'],
                'error': sw_data['error'],
                'is_duplicate': False,
                'duplicate_students': [],
                'status_msg': ''
            })

    # ------------------ DETECCIÓN FORENSE MULTI-CAPA ------------------
    # 1. Identificar computadoras base de plantilla de laboratorio (.prtdot)
    # Si una computadora aparece como origen para varios alumnos cuyas entregas terminaron
    # en computadoras de trabajo distintas, esa máquina es la plantilla del laboratorio/aula.
    template_computers = set()
    origin_to_last_comps = {}
    for entry in parsed_entries:
        if entry['is_corrupted']:
            continue
        orig = (entry.get('origin_computer') or '').strip().lower()
        last = (entry.get('last_computer') or '').strip().lower()
        if orig and orig not in ('desconocido', 'unknown', 'n/a', 'none', ''):
            origin_to_last_comps.setdefault(orig, set()).add(last)

    for orig, last_set in origin_to_last_comps.items():
        # An origin is a template computer if it was never any student's final workstation
        # (e.g. lab template server LABCAD20 -> LABCAD19, LABCAD08) or used by 4+ students.
        if (len(last_set) >= 2 and orig not in last_set) or len(last_set) >= 4:
            template_computers.add(orig)

    # 2. Agrupación por indicadores forenses entre alumnos DISTINTOS
    hash_student_map = {}          # file_hash -> set(student_names)
    creation_date_student_map = {} # creation_date -> set(student_names)
    last_comp_student_map = {}     # last_computer -> set(student_names)
    user_path_student_map = {}     # user_path -> set(student_names)
    author_student_map = {}        # author -> set(student_names)

    for entry in parsed_entries:
        if entry['is_corrupted']:
            continue
        sname = entry['student_name']

        fhash = entry.get('file_hash')
        if fhash:
            hash_student_map.setdefault(fhash, set()).add(sname)

        cdate = entry.get('creation_date')
        if cdate and str(cdate).strip() and str(cdate) != 'None':
            cdate_str = str(cdate).strip()
            creation_date_student_map.setdefault(cdate_str, set()).add(sname)

        last_comp = (entry.get('last_computer') or '').strip()
        norm_last = last_comp.lower()
        if norm_last and norm_last not in ('desconocido', 'unknown', 'n/a', 'none', ''):
            last_comp_student_map.setdefault(norm_last, set()).add(sname)

        upath = (entry.get('user_path') or '').strip()
        norm_upath = upath.lower()
        if norm_upath and not is_machine_or_generic_name(upath):
            user_path_student_map.setdefault(norm_upath, set()).add(sname)

        author = (entry.get('author') or '').strip()
        norm_author = author.lower()
        if not is_machine_or_generic_name(author):
            author_student_map.setdefault(norm_author, set()).add(sname)

    # Detectar computadoras origen transferidas a otros alumnos
    transferred_source_map = {}
    for entry in parsed_entries:
        if entry['is_corrupted']:
            continue
        sname = entry['student_name']
        norm_last = (entry.get('last_computer') or '').strip().lower()
        for ws in entry.get('workstations', []):
            ws_norm = ws.strip().lower()
            if (
                ws_norm in last_comp_student_map and
                ws_norm != norm_last and
                ws_norm not in template_computers
            ):
                source_students = last_comp_student_map[ws_norm] - {sname}
                if source_students:
                    transferred_source_map.setdefault(ws_norm, set()).add(sname)

    # Identificar coincidencias compartidas por más de un alumno
    duplicate_hashes = {h: students for h, students in hash_student_map.items() if len(students) > 1}
    duplicate_last_comps = {c: students for c, students in last_comp_student_map.items() if len(students) > 1}
    duplicate_authors = {a: students for a, students in author_student_map.items() if len(students) > 1}
    duplicate_user_paths = {u: students for u, students in user_path_student_map.items() if len(students) > 1}

    # Fechas de creación idénticas (descartando fechas de plantillas compartidas masivamente por 4+ alumnos)
    duplicate_creation_dates = {
        d: students for d, students in creation_date_student_map.items()
        if 1 < len(students) < 4
    }

    corrupted_count = 0
    duplicate_count = 0

    for entry in parsed_entries:
        if entry['is_corrupted']:
            corrupted_count += 1
            entry['status_msg'] = f"💥 ARCHIVO DAÑADO / CORRUPTO: {entry['error']}"
            continue

        sname = entry['student_name']
        fhash = entry.get('file_hash')
        cdate = str(entry.get('creation_date') or '').strip()
        last_comp = (entry.get('last_computer') or '').strip()
        norm_last = last_comp.lower()
        workstations = entry.get('workstations', [])
        upath = (entry.get('user_path') or '').strip().lower()
        author = (entry.get('author') or '').strip().lower()

        # REGLA 1: Copia Exacta (Mismo Hash MD5)
        if fhash in duplicate_hashes:
            duplicate_count += 1
            others = sorted(list(duplicate_hashes[fhash] - {sname}))
            entry['is_duplicate'] = True
            entry['duplicate_students'] = others
            entry['status_msg'] = f"⚠️ COPIA EXACTA: Archivo binario idéntico al de {', '.join(others)}"

        # REGLA 2: Misma Fecha y Hora de Creación Original al segundo
        elif cdate in duplicate_creation_dates:
            duplicate_count += 1
            others = sorted(list(duplicate_creation_dates[cdate] - {sname}))
            entry['is_duplicate'] = True
            entry['duplicate_students'] = others
            entry['status_msg'] = (
                f"⚠️ MISMA FECHA DE CREACIÓN: Creado exactamente el {cdate} "
                f"(coincide con {', '.join(others)}) → Posible pieza girada/re-guardada"
            )

        # REGLA 3: Transferencia de Archivo / Historial Cruzado entre Alumnos
        elif any(
            ws.strip().lower() in last_comp_student_map and
            ws.strip().lower() != norm_last and
            ws.strip().lower() not in template_computers and
            len(last_comp_student_map[ws.strip().lower()] - {sname}) > 0
            for ws in workstations
        ):
            transferred_ws = [
                ws for ws in workstations
                if ws.strip().lower() in last_comp_student_map and
                ws.strip().lower() != norm_last and
                ws.strip().lower() not in template_computers and
                len(last_comp_student_map[ws.strip().lower()] - {sname}) > 0
            ][0]
            others = sorted(list(last_comp_student_map[transferred_ws.strip().lower()] - {sname}))
            duplicate_count += 1
            entry['is_duplicate'] = True
            entry['duplicate_students'] = others
            entry['status_msg'] = (
                f"⚠️ TRANSFERENCIA DE ARCHIVO: Modelado en '{transferred_ws}' ({', '.join(others)}) "
                f"y re-guardado en '{entry['last_computer']}'"
            )

        # REGLA 3b: Origen de Archivo Transferido a otro alumno
        elif norm_last in transferred_source_map and len(transferred_source_map[norm_last] - {sname}) > 0:
            receivers = sorted(list(transferred_source_map[norm_last] - {sname}))
            duplicate_count += 1
            entry['is_duplicate'] = True
            entry['duplicate_students'] = receivers
            entry['status_msg'] = (
                f"⚠️ ORIGEN DE TRANSFERENCIA: La pieza creada en este equipo ('{last_comp}') "
                f"fue re-guardada y entregada por {', '.join(receivers)}"
            )

        # REGLA 4: Mismo Equipo de Trabajo (Misma Computadora Final)
        elif norm_last in duplicate_last_comps:
            duplicate_count += 1
            others = sorted(list(duplicate_last_comps[norm_last] - {sname}))
            entry['is_duplicate'] = True
            entry['duplicate_students'] = others
            entry['status_msg'] = f"⚠️ MISMO EQUIPO DE TRABAJO: Ambos guardaron desde la máquina '{last_comp}' ({', '.join(others)})"

        # REGLA 5: Rastro de Usuario de Windows
        elif upath in duplicate_user_paths:
            duplicate_count += 1
            others = sorted(list(duplicate_user_paths[upath] - {sname}))
            entry['is_duplicate'] = True
            entry['duplicate_students'] = others
            entry['status_msg'] = f"⚠️ RASTRO DE USUARIO: Rutas del usuario '{entry.get('user_path')}' coinciden con {', '.join(others)}"

        # REGLA 6: Coincidencia de Autor Registrado
        elif author in duplicate_authors:
            duplicate_count += 1
            others = sorted(list(duplicate_authors[author] - {sname}))
            entry['is_duplicate'] = True
            entry['duplicate_students'] = others
            entry['status_msg'] = f"⚠️ COINCIDENCIA DE AUTOR: Autor '{entry.get('author')}' coincide con {', '.join(others)}"

        # ARCHIVO LEGÍTIMO (OK)
        else:
            comp_display = entry.get('computer_display')
            time_str = entry.get('total_edit_time_str')
            time_part = f" | Tiempo: {time_str}" if time_str and time_str != 'Desconocido' else ""
            if comp_display and comp_display != 'Desconocido':
                entry['status_msg'] = f"✅ OK (Equipo: {comp_display}{time_part})"
            else:
                ver = entry.get('sw_version') or 'SolidWorks'
                entry['status_msg'] = f"✅ OK ({ver}{time_part})"

    return {
        'results': parsed_entries,
        'total_count': len(parsed_entries),
        'corrupted_count': corrupted_count,
        'duplicate_count': duplicate_count,
        'duplicate_summary': {
            'hashes': {h: sorted(list(s)) for h, s in duplicate_hashes.items()},
            'creation_dates': {d: sorted(list(s)) for d, s in duplicate_creation_dates.items()},
            'computers': {c: sorted(list(s)) for c, s in duplicate_last_comps.items()},
            'authors': {a: sorted(list(s)) for a, s in duplicate_authors.items()}
        }
    }
