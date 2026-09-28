# 🛠️ SolidChecker - Analizador de Autores SolidWorks para Google Classroom

**SolidChecker** es una aplicación de escritorio desarrollada en **Python (PySide6)** que automatiza la revisión de tareas de **Google Classroom** compuestas por piezas, ensamblajes o dibujos de **SolidWorks** (`.sldprt`, `.sldasm`, `.slddrw` o dentro de archivos `.zip`).

La aplicación descarga de forma temporal las entregas de los alumnos, analiza la metadatos interna grabada por **SolidWorks** (propiedades OLE2 *SummaryInformation* como Creador u Autor y Último Guardado Por) **sin necesidad de tener SolidWorks instalado**, e identifica coincidencias o duplicados entre alumnos para detectar plagios o entregas compartidas.

---

## 🚀 Características Principales

1. **Autenticación Automática con Google OAuth 2.0**:
   - Detecta si el token de sesión (`token.json`) existe y es válido.
   - Si caducó, se autorrefresca automáticamente.
   - Si no existe, abre el navegador para iniciar sesión en Google Classroom.
2. **Selección Dinámica de Clase y Tarea**:
   - Carga la lista de clases activas del profesor.
   - Carga las tareas de la clase seleccionada.
3. **Análisis de Metadatos OLE de SolidWorks**:
   - Extrae el **Autor/Creador interno** grabado por SolidWorks (no el del sistema operativo Windows).
   - Extrae la persona que **guardó por última vez** la pieza.
   - Extrae la **fecha de creación** del archivo.
   - Soporta archivos `.zip` extrayendo piezas de forma transparente.
   - **No requiere tener instalado SolidWorks en la computadora**.
4. **Detección de Duplicados / Coincidencias**:
   - Compara los autores registrados en las piezas entre diferentes alumnos.
   - Resalta en **rojo/rosado** en la tabla los archivos donde 2 o más alumnos entregaron piezas creadas bajo el mismo nombre de autor en SolidWorks.
5. **Filtros y Exportación**:
   - Búsqueda en tiempo real por alumno, archivo o autor.
   - Checkbox para filtrar y mostrar **únicamente las coincidencias sospechosas**.
   - Exportación de resultados a **Excel (`.xlsx`)** y **CSV (`.csv`)**.

---

## 🛠️ Requisitos e Instalación

### 1. Requisitos del Sistema
- **Windows 10 / 11**
- **Python 3.10+** (si se ejecuta desde código fuente)

### 2. Instalación de Dependencias

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

## 🔑 Configuración de Credenciales de Google Cloud (`credentials.json`)

Para conectar la app con Google Classroom y Drive, necesitas un archivo `credentials.json` tipo **Desktop App**:

1. Ve a [Google Cloud Console](https://console.cloud.google.com/).
2. Crea un proyecto nuevo (ej. `SolidChecker`).
3. En la barra de búsqueda, habilita las siguientes APIs:
   - **Google Classroom API**
   - **Google Drive API**
4. En **Pantalla de consentimiento de OAuth**:
   - Configura como **Externo** o **Interno** (según tu dominio escolar/institucional).
   - Añade tu correo como usuario de prueba si usas modo prueba.
5. En **Credenciales** -> **Crear Credenciales** -> **ID de cliente OAuth**:
   - Tipo de aplicación: **Aplicación de escritorio** (Desktop App).
   - Nombre: `SolidChecker Desktop`.
6. Haz clic en **Descargar JSON** y guarda ese archivo con el nombre **`credentials.json`** en la misma carpeta raíz del proyecto.

---

## 💻 Ejecución de la Aplicación

Ejecuta el archivo principal:

```bash
python main.py
```

Al abrir la app:
1. Si ya estás autenticado, verás tu correo en la esquina superior derecha.
2. Si es la primera vez, presiona **"🔑 Iniciar Sesión con Google"**.
3. Selecciona tu **Clase** y la **Tarea**.
4. Presiona **"📥 Descargar y Analizar"**.
5. Revisa la tabla de resultados. Los archivos con autores repetidos entre distintos alumnos aparecerán destacados en **rojo** con una advertencia `⚠️ COINCIDENCIA DETECTADA`.

---

## 📦 Crear Ejecutable `.exe` (para distribuir sin Python)

Puedes empaquetar toda la aplicación en un archivo `.exe` ejecutable mediante `PyInstaller`:

```bash
pip install pyinstaller
pyinstaller --noconfirm --onedir --windowed --name "SolidChecker" main.py
```

El ejecutable se generará en la carpeta `dist/SolidChecker/SolidChecker.exe`. Recuerda colocar el archivo `credentials.json` en esa misma carpeta.

---

## 📂 Estructura del Proyecto

```
solidchecker/
├── main.py                # Punto de entrada de la app
├── gui.py                 # Interfaz gráfica en PySide6
├── classroom_api.py       # Conexión OAuth2, Google Classroom y Drive API
├── solidworks_parser.py   # Extracción de metadatos OLE de .sldprt/.sldasm/.slddrw
├── analyzer.py            # Comparación de autores y detección de duplicados
├── requirements.txt       # Librerías de Python requeridas
└── README.md              # Documentación del proyecto
```
