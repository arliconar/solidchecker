import os
import zipfile
import tempfile
import datetime
import olefile

def parse_solidworks_file(file_path):
    """
    Parses a SolidWorks file (.sldprt, .sldasm, .slddrw) using olefile
    to extract standard OLE SummaryInformation metadata (Author, Last Saved By, Creation Date, etc.).
    Does NOT require SolidWorks to be installed.
    Detects if the file is damaged, corrupted, zero-byte, or unreadable.
    """
    result = {
        'file_name': os.path.basename(file_path),
        'file_path': file_path,
        'file_size': os.path.getsize(file_path) if os.path.exists(file_path) else 0,
        'extension': os.path.splitext(file_path)[1].lower(),
        'author': 'Desconocido',
        'last_saved_by': 'Desconocido',
        'creation_date': None,
        'last_saved_date': None,
        'title': '',
        'comments': '',
        'is_corrupted': False,
        'error': None
    }

    if not os.path.exists(file_path):
        result['is_corrupted'] = True
        result['error'] = 'El archivo no existe o no se pudo acceder en el sistema.'
        return result

    if result['file_size'] == 0:
        result['is_corrupted'] = True
        result['error'] = 'El archivo está vacío (0 bytes). Posible corrupción al subir o guardar.'
        return result

    if not olefile.isOleFile(file_path):
        result['is_corrupted'] = True
        result['error'] = 'El archivo no tiene una estructura OLE2 válida (archivo dañado, alterado o en formato incompatible).'
        return result

    try:
        ole = olefile.OleFileIO(file_path)
        meta = ole.get_metadata()

        if meta.author:
            if isinstance(meta.author, bytes):
                result['author'] = meta.author.decode('utf-8', errors='ignore').strip()
            else:
                result['author'] = str(meta.author).strip()

        if meta.last_saved_by:
            if isinstance(meta.last_saved_by, bytes):
                result['last_saved_by'] = meta.last_saved_by.decode('utf-8', errors='ignore').strip()
            else:
                result['last_saved_by'] = str(meta.last_saved_by).strip()

        if meta.create_time:
            result['creation_date'] = meta.create_time

        if meta.last_saved_time:
            result['last_saved_date'] = meta.last_saved_time

        if meta.title:
            result['title'] = str(meta.title).strip()

        if meta.comments:
            result['comments'] = str(meta.comments).strip()

        ole.close()

    except Exception as e:
        result['is_corrupted'] = True
        result['error'] = f"Error al abrir la estructura interna del archivo (posible corrupción binaria): {str(e)}"

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
