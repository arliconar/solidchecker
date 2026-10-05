import os
import zipfile
import tempfile
import datetime
import hashlib
import olefile
import re
import zlib

GENERIC_NAMES = {
    'default', 'predeterminado', 'normal', 'solidworks', 'user', 'usuario',
    'administrator', 'admin', 'system', 'none', 'null', 'n/a', 'pieza', 'pieza1',
    'part', 'part1', 'created', 'modified', 'anotaciones', 'alzado', 'planta',
    'origen', 'comentarios', 'material', 'vistas', 'sensores', 'favoritos',
    'historial', 'ecuaciones', 'marcas', 'cuaderno', 'luces', 'camaras', 'solidos',
    'superficies', 'conjuntos', 'predeterminada', 'solidworks (versión moderna)'
}

def _is_valid_name(val):
    if not val:
        return False
    v = str(val).strip().lower()
    return len(v) >= 2 and v not in GENERIC_NAMES

def _convert_sw_timestamp(ts_str):
    try:
        ts = int(ts_str)
        if ts > 0:
            return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime('%d/%m/%Y %H:%M:%S')
    except Exception:
        pass
    return None

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
        'title': '',
        'comments': '',
        'user_path': None,
        'sw_version': None
    }

    try:
        with open(file_path, 'rb') as f:
            data = f.read()

        file_size = len(data)
        found_xml_texts = []

        # Fast scan for zlib and DEFLATE compressed XML & header streams across full file
        for i in range(0, file_size - 10, 2):
            is_zlib_hdr = data[i:i+2] in (b'\x78\x9c', b'\x78\x01', b'\x78\xda', b'\x78\x5e')
            if not is_zlib_hdr and (i % 4 != 0):
                continue

            for wbits in (15, -15, 31):
                try:
                    decomp = zlib.decompress(data[i:i+32768], wbits)
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
                            if not props['author'] and _is_valid_name(s_clean):
                                props['author'] = s_clean

                    # 2. Text & XML Property Matching
                    if b'Properties' in decomp or b'swFile' in decomp or b'coreProperties' in decomp or b'lastModifiedBy' in decomp:
                        txt = decomp.decode('utf-8', errors='ignore')
                        found_xml_texts.append(txt)
                        break
                except Exception:
                    pass

        for txt in found_xml_texts:
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

            # Version
            if not props['sw_version']:
                m_ver = re.search(r'swVersion="(\d+)"', txt)
                if m_ver:
                    ver_num = int(m_ver.group(1))
                    year = 1992 + (ver_num // 1000)
                    props['sw_version'] = f"SolidWorks {year} (v{ver_num})"

        # Fallbacks for author and last_saved_by
        if not _is_valid_name(props['author']):
            if _is_valid_name(props['last_saved_by']):
                props['author'] = props['last_saved_by']
            elif _is_valid_name(props['user_path']):
                props['author'] = props['user_path']

        if not _is_valid_name(props['last_saved_by']):
            if _is_valid_name(props['author']):
                props['last_saved_by'] = props['author']
            elif _is_valid_name(props['user_path']):
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

        pStore = ctypes.c_void_p()
        hr = shell32.SHGetPropertyStoreFromParsingName(
            file_path, None, 0, ctypes.byref(IID_IPropertyStore), ctypes.byref(pStore)
        )
        if hr == 0 and pStore.value:
            vtable = ctypes.cast(pStore.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            GetCountFunc = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD))(vtable[3])
            GetAtFunc = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(PROPERTYKEY))(vtable[4])
            GetValueFunc = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY), ctypes.c_void_p)(vtable[5])

            count = wintypes.DWORD()
            GetCountFunc(pStore, ctypes.byref(count))

            PSGetNameFromPropertyKey = propsys.PSGetNameFromPropertyKey
            PSGetNameFromPropertyKey.argtypes = [ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(ctypes.c_wchar_p)]
            PSGetNameFromPropertyKey.restype = ctypes.HRESULT

            PSFormatForDisplayAlloc = propsys.PSFormatForDisplayAlloc
            PSFormatForDisplayAlloc.argtypes = [ctypes.POINTER(PROPERTYKEY), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_wchar_p)]
            PSFormatForDisplayAlloc.restype = ctypes.HRESULT

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
    if not _is_valid_name(props['last_saved_by']) and _is_valid_name(xml_props['user_path']):
        props['last_saved_by'] = xml_props['user_path']
    if not props['creation_date'] and xml_props['creation_date']:
        props['creation_date'] = xml_props['creation_date']
    if not _is_valid_name(props['last_saved_by']) and xml_props['sw_version']:
        props['last_saved_by'] = xml_props['sw_version']

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
        'last_saved_by': 'SolidWorks',
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
            elif _is_valid_name(last_saved):
                result['author'] = last_saved

            if _is_valid_name(last_saved):
                result['last_saved_by'] = last_saved

            if meta.create_time:
                result['creation_date'] = meta.create_time.strftime('%d/%m/%Y %H:%M:%S') if hasattr(meta.create_time, 'strftime') else str(meta.create_time)

            if meta.last_saved_time:
                result['last_saved_date'] = meta.last_saved_time.strftime('%d/%m/%Y %H:%M:%S') if hasattr(meta.last_saved_time, 'strftime') else str(meta.last_saved_time)

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
        elif _is_valid_name(modern_props['last_saved_by']):
            result['author'] = modern_props['last_saved_by']

        if _is_valid_name(modern_props['last_saved_by']):
            result['last_saved_by'] = modern_props['last_saved_by']
        elif _is_valid_name(modern_props['author']):
            result['last_saved_by'] = modern_props['author']

        if modern_props['creation_date']:
            result['creation_date'] = modern_props['creation_date']
        if modern_props['last_saved_date']:
            result['last_saved_date'] = modern_props['last_saved_date']
        if modern_props['title']:
            result['title'] = modern_props['title']
        if modern_props['comments']:
            result['comments'] = modern_props['comments']

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
