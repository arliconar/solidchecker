import os
import zipfile
import tempfile
import datetime
import hashlib
import olefile
import re
import zlib
import struct

_STREAM_CACHE = {}

def _swap_nibbles(b):
    return bytes(((x << 4) & 0xF0) | (x >> 4) for x in b)

def get_decompressed_streams(data):
    """
    Returns the list of decompressed internal streams of a modern SolidWorks file (2015+).

    Each section in the container has the layout:
        u32 compressed_size | u32 uncompressed_size | u32 name_len | name (nibble-swapped) | raw DEFLATE data
    Sections can start at ANY byte offset (not aligned), so we look for that header
    structure explicitly and validate it by decompressing to the declared size.
    Falls back to a full byte-by-byte DEFLATE scan if no valid sections are found.
    """
    key = hashlib.md5(data).hexdigest()
    if key in _STREAM_CACHE:
        return _STREAM_CACHE[key]

    streams = []
    n = len(data)
    i = 8
    while i < n - 12:
        csize, usize, nlen = struct.unpack_from('<III', data, i - 8)
        if 0 < nlen <= 255 and 0 < csize <= n and 0 < usize <= 64 * 1024 * 1024:
            start = i + 4 + nlen
            if start + csize <= n:
                name = _swap_nibbles(data[i + 4:start])
                if all(32 <= c < 127 for c in name):
                    try:
                        dec = zlib.decompress(data[start:start + csize], -15)
                        if len(dec) == usize:
                            streams.append((name.decode('ascii', 'ignore'), dec))
                            i = start + csize + 8
                            continue
                    except Exception:
                        pass
        i += 1

    if not streams:
        # Fallback: brute-force scan at every byte offset
        seen = set()
        for j in range(n - 10):
            try:
                d = zlib.decompressobj(-15)
                dec = d.decompress(data[j:j + 1048576])
                if len(dec) >= 40 and d.eof:
                    h = hash(dec[:256])
                    if h not in seen:
                        seen.add(h)
                        streams.append(('', dec))
            except Exception:
                pass

    _STREAM_CACHE[key] = streams
    return streams

def _read_cstring(buf, pos):
    """Reads an MFC CString (ff fe ff <len> utf16...) at pos. Returns (string, new_pos) or (None, pos)."""
    if buf[pos:pos + 3] != b'\xff\xfe\xff':
        return None, pos
    pos += 3
    ln = buf[pos]
    pos += 1
    if ln == 0xFF:
        ln = struct.unpack_from('<H', buf, pos)[0]
        pos += 2
    s = buf[pos:pos + ln * 2].decode('utf-16le', errors='ignore')
    return s, pos + ln * 2

def _parse_header_cstring_array(dec):
    """Parses moHeader_c -> su_CStringArray (list of Windows user/computer names that saved the file)."""
    idx = dec.find(b'moHeader_c')
    if idx == -1:
        return []
    idx = dec.find(b'su_CStringArray', idx)
    if idx == -1:
        return []
    pos = idx + len(b'su_CStringArray')
    try:
        count = struct.unpack_from('<H', dec, pos)[0]
        pos += 2
        names = []
        for _ in range(min(count, 64)):
            s, pos = _read_cstring(dec, pos)
            if s is None:
                break
            s = s.strip()
            if s and s not in names:
                names.append(s)
        return names
    except Exception:
        return []

def sw_internal_version_to_name(v):
    """SolidWorks internal version number → product year. (9000=2016, 14000=2021, 18000=2025, 19000=2026...)"""
    try:
        v = int(v)
    except Exception:
        return None
    if v >= 9000:
        return f"SolidWorks {2007 + v // 1000}"
    return f"SolidWorks (v{v})"

def extract_sw_version_info(data):
    """
    Returns the SolidWorks version the file was last saved with, plus the history of
    versions it went through (e.g. created in 2021 template, saved in 2025).
    Sources: stream names '_MO_VERSION_<N>/...' and the 'moVersionHistory_c' record.
    """
    info = {'sw_version': None, 'sw_version_history': [], 'sw_version_display': 'Desconocida'}
    try:
        streams = get_decompressed_streams(data)
        current = None
        hist_nums = []
        for name, dec in streams:
            m = re.match(r'_MO_VERSION_(\d+)/', name or '')
            if m:
                current = max(current or 0, int(m.group(1)))
                if name.endswith('/History'):
                    # Each history entry ends with an empty CString (ff fe ff 00) followed by u32 version
                    for mm in re.finditer(rb'\xff\xfe\xff\x00(.{4})', dec, re.S):
                        val = struct.unpack('<I', mm.group(1))[0]
                        if 1000 <= val <= 99000 and val % 1000 == 0 and val not in hist_nums:
                            hist_nums.append(val)
        if current and current not in hist_nums:
            hist_nums.append(current)
        hist_nums.sort()
        if current:
            info['sw_version'] = sw_internal_version_to_name(current)
        info['sw_version_history'] = [sw_internal_version_to_name(v) for v in hist_nums]
        if len(info['sw_version_history']) > 1:
            info['sw_version_display'] = ' → '.join(info['sw_version_history'])
        elif info['sw_version']:
            info['sw_version_display'] = info['sw_version']
    except Exception:
        pass
    return info

GENERIC_NAMES = {
    'default', 'predeterminado', 'normal', 'solidworks', 'user', 'usuario',
    'administrator', 'admin', 'system', 'none', 'null', 'n/a', 'pieza', 'pieza1',
    'part', 'part1', 'created', 'modified', 'anotaciones', 'alzado', 'planta',
    'origen', 'comentarios', 'material', 'vistas', 'sensores', 'favoritos',
    'historial', 'ecuaciones', 'marcas', 'cuaderno', 'luces', 'camaras', 'solidos',
    'superficies', 'conjuntos', 'predeterminada', 'solidworks (versión moderna)',
    'alumno', 'alumnos', 'estudiante', 'estudiantes', 'docente', 'profesor',
    'sin autor', 'sin autor registrado', 'desconocido', 'unknown', 'no especificado',
    'guest', 'invitado', 'public', 'publico'
}

def is_machine_or_generic_name(val):
    if not val:
        return True
    v = str(val).strip().lower()
    if len(v) < 2 or v in GENERIC_NAMES:
        return True
    # Detect computer lab machines and generic hostnames (e.g. LABCAD20, PC-01, LAB-02, DESKTOP-XYZ)
    if re.match(r'^(lab|labcad|aula|taller|compu|pc|equipo|maquina|ws|workstation)[-_0-9a-z]*$', v):
        return True
    if re.match(r'^(desktop|laptop|win)-[a-z0-9]+$', v):
        return True
    if 'solidworks' in v:
        return True
    return False

def _is_valid_name(val):
    return not is_machine_or_generic_name(val)

def format_edit_time(seconds=None, minutes=None, raw_str=None):
    """Formats accumulated editing time into human-friendly format (e.g. 2h 15m, 45 min)."""
    if raw_str and any(c in str(raw_str) for c in ('h', 'm', 's', ':')):
        return str(raw_str).strip()
    if minutes is not None:
        try:
            m = int(minutes)
            if m <= 0:
                return "< 1 min"
            h = m // 60
            rem_m = m % 60
            if h > 0:
                return f"{h}h {rem_m:02d}m"
            return f"{m} min"
        except Exception:
            pass
    if seconds is not None:
        try:
            s = int(seconds)
            if s <= 0:
                return "< 1 min"
            h = s // 3600
            rem_m = (s % 3600) // 60
            rem_s = s % 60
            if h > 0:
                return f"{h}h {rem_m:02d}m"
            if rem_m > 0:
                return f"{rem_m} min"
            return f"{rem_s} seg"
        except Exception:
            pass
    return "Desconocido"

def _convert_sw_timestamp(ts_str):
    try:
        ts = int(ts_str)
        if ts > 0:
            return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime('%d/%m/%Y %H:%M:%S')
    except Exception:
        pass
    return None

def extract_workstation_history(file_path, data=None):
    """
    Extracts the list of computer workstation names (hostnames) that have
    created, edited, or saved the SolidWorks document from moHeader_c / su_CStringArray
    and XML properties.
    """
    machines = []
    try:
        if data is None and os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                data = f.read()

        if data:
            xml_comps = []
            # Read every internal stream exactly (sections may start at any byte offset)
            for _name, decomp in get_decompressed_streams(data):
                if not machines and b'moHeader_c' in decomp and b'su_CStringArray' in decomp:
                    found = _parse_header_cstring_array(decomp)
                    if found:
                        machines = found

                if b'SW-Last Saved By' in decomp or b'lastModifiedBy' in decomp:
                    txt = decomp.decode('utf-8', errors='ignore')
                    m1 = re.search(r'<property[^>]*name="SW-Last Saved By"[^>]*>\s*<vt:lpstr>([^<]+)</vt:lpstr>', txt)
                    if m1 and m1.group(1).strip():
                        c = m1.group(1).strip()
                        if c not in xml_comps:
                            xml_comps.append(c)
                    m2 = re.search(r'<(?:dc:)?lastModifiedBy>([^<]+)</', txt)
                    if m2 and m2.group(1).strip():
                        c = m2.group(1).strip()
                        if c not in xml_comps:
                            xml_comps.append(c)


            for c in xml_comps:
                if c not in machines and not c.lower().startswith('solidworks'):
                    machines.append(c)

    except Exception:
        pass

    origin = machines[0] if machines else 'Desconocido'
    last = machines[-1] if machines else 'Desconocido'
    if len(machines) > 1:
        history_str = ' → '.join(machines)
    elif machines:
        history_str = machines[0]
    else:
        history_str = 'Desconocido'

    return {
        'workstations': machines,
        'origin_computer': origin,
        'last_computer': last,
        'computer_display': history_str,
        'computer_name': origin
    }

def _extract_modern_sw_xml_props(file_path):
    """
    Directly extracts metadata (Author, Last Saved By, Creation Date, User Path, SW Version)
    from modern SolidWorks files (2015-2026+) by scanning internal DEFLATE/zlib compressed
    XML streams and moHeader_c structures without requiring SolidWorks or Windows Shell handlers.
    """
    props = {
        'author': None,
        'last_saved_by': None,
        'creation_date': None,
        'last_saved_date': None,
        'total_edit_time': None,
        'total_edit_time_str': 'Desconocido',
        'title': '',
        'comments': '',
        'user_path': None,
        'sw_version': None
    }

    try:
        with open(file_path, 'rb') as f:
            data = f.read()

        found_xml_texts = []

        # Read every internal compressed stream exactly
        for _name, decomp in get_decompressed_streams(data):
            if len(decomp) < 30:
                continue

            # 1. moHeader_c (SolidWorks model header stream present in all versions)
            if b'moHeader_c' in decomp:
                u16_strs = [s.decode('utf-16le', errors='ignore') for s in re.findall(b'(?:[\x20-\x7e]\x00){2,}', decomp)]
                for s in u16_strs:
                    s_clean = s.strip()
                    m_u = re.search(r'[C-Z]:\\Users\\([^\\]+)\\', s_clean, re.IGNORECASE)
                    if m_u and _is_valid_name(m_u.group(1)):
                        if not props['user_path']:
                            props['user_path'] = m_u.group(1).strip()
                        break

            # 2. Text & XML Property Matching
            if b'Properties' in decomp or b'swFile' in decomp or b'coreProperties' in decomp or b'lastModifiedBy' in decomp:
                found_xml_texts.append(decomp.decode('utf-8', errors='ignore'))

        for txt in found_xml_texts:
            # Total Editing Time
            if not props['total_edit_time']:
                m_tt = re.search(r'<(?:app:)?TotalTime>(\d+)</(?:app:)?TotalTime>', txt, re.IGNORECASE)
                if m_tt:
                    mins = int(m_tt.group(1))
                    props['total_edit_time'] = mins * 60
                    props['total_edit_time_str'] = format_edit_time(minutes=mins)
                else:
                    m_sw_tt = re.search(r'swTotalEditingTime="(\d+)"', txt, re.IGNORECASE)
                    if m_sw_tt:
                        secs = int(m_sw_tt.group(1))
                        props['total_edit_time'] = secs
                        props['total_edit_time_str'] = format_edit_time(seconds=secs)

            # OpenXML core properties (dc:lastModifiedBy / dc:creator)
            if not _is_valid_name(props['last_saved_by']):
                m_dc_last = re.search(r'<(?:dc:)?lastModifiedBy>([^<]+)</', txt, re.IGNORECASE)
                if m_dc_last and _is_valid_name(m_dc_last.group(1)):
                    props['last_saved_by'] = m_dc_last.group(1).strip()

            if not _is_valid_name(props['author']):
                m_dc_creator = re.search(r'<(?:dc:)?creator>([^<]+)</', txt, re.IGNORECASE)
                if m_dc_creator and _is_valid_name(m_dc_creator.group(1)):
                    props['author'] = m_dc_creator.group(1).strip()

            # SW specific property tags
            if not _is_valid_name(props['author']):
                m_sw_auth = re.search(r'<property[^>]*name="SW-Author"[^>]*>\s*<vt:lpstr>([^<]+)</vt:lpstr>', txt)
                if m_sw_auth and _is_valid_name(m_sw_auth.group(1)):
                    props['author'] = m_sw_auth.group(1).strip()

            if not _is_valid_name(props['last_saved_by']):
                m_sw_last = re.search(r'<property[^>]*name="SW-Last Saved By"[^>]*>\s*<vt:lpstr>([^<]+)</vt:lpstr>', txt)
                if m_sw_last and _is_valid_name(m_sw_last.group(1)):
                    props['last_saved_by'] = m_sw_last.group(1).strip()

            # Folder path property (SW- Nombre de la carpeta)
            if not _is_valid_name(props['user_path']):
                m_folder = re.search(r'C:\\Users\\([^\\]+)\\', txt, re.IGNORECASE)
                if m_folder and _is_valid_name(m_folder.group(1)):
                    props['user_path'] = m_folder.group(1).strip()

            # swPath property
            if not _is_valid_name(props['user_path']):
                m_path = re.search(r'swPath="([^"]+)"', txt)
                if m_path:
                    sw_path = m_path.group(1)
                    m_user = re.search(r'[C-Z]:\\Users\\([^\\]+)\\', sw_path, re.IGNORECASE)
                    if m_user and _is_valid_name(m_user.group(1)):
                        props['user_path'] = m_user.group(1).strip()

            # Dates
            if not props['creation_date']:
                m_ts = re.search(r'swCreationTime="(\d+)"', txt)
                if m_ts:
                    dt_str = _convert_sw_timestamp(m_ts.group(1))
                    if dt_str:
                        props['creation_date'] = dt_str

            if not props['creation_date']:
                m_cdate = re.search(r'name="SW-\s*Fecha de creaci[^"]*"[^>]*>\s*<vt:lpstr>([^<]+)</vt:lpstr>', txt)
                if m_cdate and m_cdate.group(1).strip():
                    props['creation_date'] = m_cdate.group(1).strip()

            if not props['creation_date']:
                m_ox_c = re.search(r'<(?:dcterms:)?created[^>]*>([^<]+)</', txt, re.IGNORECASE)
                if m_ox_c and m_ox_c.group(1).strip():
                    raw_dt = m_ox_c.group(1).strip()
                    try:
                        clean_dt = raw_dt.replace('Z', '+00:00')
                        parsed_dt = datetime.datetime.fromisoformat(clean_dt)
                        props['creation_date'] = parsed_dt.strftime('%d/%m/%Y %H:%M:%S')
                    except Exception:
                        props['creation_date'] = raw_dt

            # Version
            if not props['sw_version']:
                m_ver = re.search(r'swVersion="(\d+)"', txt)
                if m_ver:
                    ver_num = int(m_ver.group(1))
                    year = 1992 + (ver_num // 1000)
                    props['sw_version'] = f"SolidWorks {year} (v{ver_num})"

        # Fallbacks for author and last_saved_by (from user folder path)
        if not _is_valid_name(props['author']):
            if _is_valid_name(props['user_path']):
                props['author'] = props['user_path']

        if not _is_valid_name(props['last_saved_by']):
            if _is_valid_name(props['user_path']):
                props['last_saved_by'] = props['user_path']

    except Exception:
        pass

    return props

def _extract_modern_solidworks_props(file_path):
    """
    Attempts to extract properties from modern SolidWorks files (2015-2026+)
    using the Windows Shell Property Store (IPropertyStore) via ctypes
    and falls back to direct XML stream parsing.
    """
    props = {
        'author': None,
        'last_saved_by': None,
        'creation_date': None,
        'last_saved_date': None,
        'title': '',
        'comments': ''
    }

    if not os.path.exists(file_path) or os.path.getsize(file_path) < 1024:
        return _extract_modern_sw_xml_props(file_path)

    try:
        import ctypes
        from ctypes import wintypes
        shell32 = ctypes.windll.shell32
        propsys = ctypes.windll.propsys
        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)

        class PROPERTYKEY(ctypes.Structure):
            _fields_ = [('fmtid', ctypes.c_byte * 16), ('pid', wintypes.DWORD)]

        IID_IPropertyStore = (ctypes.c_byte * 16)(
            0xeb, 0x8e, 0x6d, 0x88, 0xf2, 0x8c, 0x46, 0x44, 0x8d, 0x02, 0xcd, 0xba, 0x1d, 0xbd, 0xcf, 0x99
        )

        abs_path = os.path.abspath(file_path)
        pStore = ctypes.c_void_p()
        hr = shell32.SHGetPropertyStoreFromParsingName(
            abs_path, None, 0, ctypes.byref(IID_IPropertyStore), ctypes.byref(pStore)
        )
        if hr == 0 and pStore.value:
            vtable = ctypes.cast(pStore.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            GetCountFunc = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD))(vtable[3])
            GetAtFunc = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(PROPERTYKEY))(vtable[4])
            GetValueFunc = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY), ctypes.c_void_p)(vtable[5])

            count = wintypes.DWORD()
            GetCountFunc(pStore, ctypes.byref(count))

            PSGetNameFromPropertyKey = propsys.PSGetNameFromPropertyKey
            PSGetNameFromPropertyKey.argtypes = [ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(ctypes.c_wchar_p)]
            PSGetNameFromPropertyKey.restype = ctypes.c_long

            PSFormatForDisplayAlloc = propsys.PSFormatForDisplayAlloc
            PSFormatForDisplayAlloc.argtypes = [ctypes.POINTER(PROPERTYKEY), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_wchar_p)]
            PSFormatForDisplayAlloc.restype = ctypes.c_long

            raw_props = {}
            for i in range(count.value):
                key = PROPERTYKEY()
                GetAtFunc(pStore, i, ctypes.byref(key))
                name_ptr = ctypes.c_wchar_p()
                try:
                    hr_name = PSGetNameFromPropertyKey(ctypes.byref(key), ctypes.byref(name_ptr))
                    prop_name = name_ptr.value if hr_name == 0 else f'K_{key.pid}'
                except Exception:
                    prop_name = f'K_{key.pid}'

                propvar = (ctypes.c_byte * 24)()
                GetValueFunc(pStore, ctypes.byref(key), ctypes.byref(propvar))
                val_ptr = ctypes.c_wchar_p()
                hr_val = PSFormatForDisplayAlloc(ctypes.byref(key), ctypes.byref(propvar), 0, ctypes.byref(val_ptr))
                val_str = (val_ptr.value or '').replace('\u200e', '').replace('\u200f', '').strip() if hr_val == 0 else ''
                ole32.PropVariantClear(ctypes.byref(propvar))
                if val_str:
                    raw_props[prop_name] = val_str

            sw_ver = raw_props.get('Solidworks.Document.LastSavedWith')
            if sw_ver:
                props['last_saved_by'] = sw_ver

            author = raw_props.get('System.Author') or raw_props.get('System.Document.Author') or raw_props.get('System.ItemAuthors')
            if _is_valid_name(author):
                props['author'] = author

            created = raw_props.get('System.Document.DateCreated') or raw_props.get('System.DateCreated')
            if created:
                props['creation_date'] = created

            saved = raw_props.get('System.Document.DateSaved') or raw_props.get('System.DateModified')
            if saved:
                props['last_saved_date'] = saved

            title = raw_props.get('System.Title')
            if title:
                props['title'] = title

            comment = raw_props.get('System.Comment')
            if comment:
                props['comments'] = comment

            edit_time = raw_props.get('System.Document.TotalEditingTime')
            if edit_time:
                props['total_edit_time_str'] = edit_time

    except Exception:
        pass

    # Direct XML & moHeader_c stream fallback
    xml_props = _extract_modern_sw_xml_props(file_path)
    if not _is_valid_name(props['author']) and _is_valid_name(xml_props['author']):
        props['author'] = xml_props['author']
    if not _is_valid_name(props['last_saved_by']) and _is_valid_name(xml_props['last_saved_by']):
        props['last_saved_by'] = xml_props['last_saved_by']
    if not _is_valid_name(props['author']) and _is_valid_name(xml_props['user_path']):
        props['author'] = xml_props['user_path']
    if xml_props.get('creation_date'):
        props['creation_date'] = xml_props['creation_date']
    if not props['last_saved_by'] and xml_props.get('last_saved_by'):
        props['last_saved_by'] = xml_props['last_saved_by']
    if not props['last_saved_by'] and xml_props.get('sw_version'):
        props['last_saved_by'] = xml_props['sw_version']
    if xml_props.get('total_edit_time'):
        props['total_edit_time'] = xml_props['total_edit_time']
    if xml_props.get('total_edit_time_str') and (not props.get('total_edit_time_str') or props.get('total_edit_time_str') == 'Desconocido'):
        props['total_edit_time_str'] = xml_props['total_edit_time_str']
    if xml_props.get('user_path'):
        props['user_path'] = xml_props['user_path']

    return props

def parse_solidworks_file(file_path):
    """
    Parses a SolidWorks file (.sldprt, .sldasm, .slddrw) supporting:
    - Legacy OLE2 files (SolidWorks 2014 and older)
    - Modern SolidWorks files (SolidWorks 2015 to 2026+)
    Detects if the file is genuinely damaged, corrupted, zero-byte, or composed of null bytes.
    """
    result = {
        'file_name': os.path.basename(file_path),
        'file_path': file_path,
        'file_size': os.path.getsize(file_path) if os.path.exists(file_path) else 0,
        'extension': os.path.splitext(file_path)[1].lower(),
        'author': 'Sin autor registrado',
        'origin_computer': 'Desconocido',
        'last_computer': 'Desconocido',
        'computer_display': 'Desconocido',
        'computer_name': 'Desconocido',
        'workstations': [],
        'user_path': None,
        'total_edit_time': None,
        'total_edit_time_str': 'Desconocido',
        'last_saved_by': 'SolidWorks',
        'sw_version': None,
        'sw_version_history': [],
        'sw_version_display': 'Desconocida',
        'creation_date': None,
        'last_saved_date': None,
        'title': '',
        'comments': '',
        'is_corrupted': False,
        'error': None,
        'file_hash': None
    }

    if not os.path.exists(file_path):
        result['is_corrupted'] = True
        result['error'] = 'El archivo no existe o no se pudo acceder en el sistema.'
        return result

    if result['file_size'] == 0:
        result['is_corrupted'] = True
        result['error'] = 'El archivo está vacío (0 bytes). Posible error de subida del alumno.'
        return result

    try:
        with open(file_path, 'rb') as f:
            data = f.read()
    except Exception as e:
        result['is_corrupted'] = True
        result['error'] = f'No se pudo leer el archivo binario: {e}'
        return result

    result['file_hash'] = hashlib.md5(data).hexdigest()

    # Detect files damaged with only null (0x00) bytes
    if not any(data):
        result['is_corrupted'] = True
        result['error'] = 'El archivo está dañado (compuesto exclusivamente de ceros/bytes nulos).'
        return result

    # Extract workstation computer names from internal structures
    comp_info = extract_workstation_history(file_path, data)
    result['workstations'] = comp_info['workstations']
    result['origin_computer'] = comp_info['origin_computer']
    result['last_computer'] = comp_info['last_computer']
    result['computer_display'] = comp_info['computer_display']
    result['computer_name'] = comp_info['computer_name']

    # Real SolidWorks version (from _MO_VERSION_<N> streams), independent of user names
    ver_info = extract_sw_version_info(data)
    result.update(ver_info)

    # 1. Legacy OLE2 structured storage (SolidWorks 2014 and older)
    if olefile.isOleFile(file_path):
        try:
            ole = olefile.OleFileIO(file_path)
            meta = ole.get_metadata()

            author = None
            if meta.author:
                author = meta.author.decode('utf-8', errors='ignore').strip() if isinstance(meta.author, bytes) else str(meta.author).strip()

            last_saved = None
            if meta.last_saved_by:
                last_saved = meta.last_saved_by.decode('utf-8', errors='ignore').strip() if isinstance(meta.last_saved_by, bytes) else str(meta.last_saved_by).strip()

            if _is_valid_name(author):
                result['author'] = author
            else:
                result['author'] = 'Sin autor registrado'

            if _is_valid_name(last_saved):
                result['last_saved_by'] = last_saved

            if not result['workstations'] and last_saved and len(last_saved) >= 2:
                result['origin_computer'] = last_saved
                result['last_computer'] = last_saved
                result['computer_display'] = last_saved
                result['computer_name'] = last_saved
                result['workstations'] = [last_saved]

            if meta.create_time:
                result['creation_date'] = meta.create_time.strftime('%d/%m/%Y %H:%M:%S') if hasattr(meta.create_time, 'strftime') else str(meta.create_time)

            if meta.last_saved_time:
                result['last_saved_date'] = meta.last_saved_time.strftime('%d/%m/%Y %H:%M:%S') if hasattr(meta.last_saved_time, 'strftime') else str(meta.last_saved_time)

            if hasattr(meta, 'total_edit_time') and meta.total_edit_time is not None:
                tet = meta.total_edit_time
                if hasattr(tet, 'total_seconds'):
                    secs = int(tet.total_seconds())
                    result['total_edit_time'] = secs
                    result['total_edit_time_str'] = format_edit_time(seconds=secs)
                elif isinstance(tet, (int, float)):
                    val = int(tet)
                    if val > 10_000_000:
                        val = val // 10_000_000
                    result['total_edit_time'] = val
                    result['total_edit_time_str'] = format_edit_time(seconds=val)

            if meta.title:
                result['title'] = str(meta.title).strip()

            if meta.comments:
                result['comments'] = str(meta.comments).strip()

            ole.close()
            return result
        except Exception as e:
            result['is_corrupted'] = True
            result['error'] = f"Error en estructura interna OLE2: {e}"
            return result

    # 2. Modern SolidWorks proprietary container (SolidWorks 2015 to 2026+)
    # Bytes 4..8 == 0x00000004
    is_modern_sw_signature = len(data) >= 8 and data[4:8] == b'\x00\x00\x00\x04'

    if is_modern_sw_signature:
        result['last_saved_by'] = 'SolidWorks (Versión moderna)'
        modern_props = _extract_modern_solidworks_props(file_path)

        if _is_valid_name(modern_props['author']):
            result['author'] = modern_props['author']
        else:
            result['author'] = 'Sin autor registrado'

        if modern_props.get('last_saved_by'):
            result['last_saved_by'] = modern_props['last_saved_by']
        elif modern_props.get('sw_version'):
            result['last_saved_by'] = modern_props['sw_version']
        else:
            result['last_saved_by'] = 'SolidWorks (Versión moderna)'

        if modern_props['creation_date']:
            result['creation_date'] = modern_props['creation_date']
        if modern_props['last_saved_date']:
            result['last_saved_date'] = modern_props['last_saved_date']
        if modern_props['title']:
            result['title'] = modern_props['title']
        if modern_props['comments']:
            result['comments'] = modern_props['comments']
        if modern_props.get('total_edit_time'):
            result['total_edit_time'] = modern_props['total_edit_time']
        if modern_props.get('total_edit_time_str'):
            result['total_edit_time_str'] = modern_props['total_edit_time_str']
        if modern_props.get('user_path'):
            result['user_path'] = modern_props['user_path']

        return result

    # 3. Neither recognized container
    result['is_corrupted'] = True
    result['error'] = 'El archivo no tiene una estructura de SolidWorks válida ni formato OLE2 reconocido.'
    return result

def extract_solidworks_from_zip(zip_path, extract_dir):
    """
    Extracts any .sldprt, .sldasm, .slddrw files from a zip file into extract_dir.
    Returns a list of extracted file paths.
    """
    extracted_files = []
    sw_extensions = {'.sldprt', '.sldasm', '.slddrw'}

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.infolist():
                ext = os.path.splitext(member.filename)[1].lower()
                if ext in sw_extensions:
                    filename = os.path.basename(member.filename)
                    if filename:
                        target_path = os.path.join(extract_dir, filename)
                        with zip_ref.open(member) as source, open(target_path, "wb") as target:
                            target.write(source.read())
                        extracted_files.append(target_path)
    except Exception as e:
        print(f"Error extrayendo ZIP {zip_path}: {e}")

    return extracted_files
