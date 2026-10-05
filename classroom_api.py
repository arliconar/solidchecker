import os
import io
import json
import tempfile
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Allow oauthlib to accept scope changes (e.g. Google injecting 'openid' or selective consent)
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/classroom.courses.readonly',
    'https://www.googleapis.com/auth/classroom.coursework.students.readonly',
    'https://www.googleapis.com/auth/classroom.student-submissions.students.readonly',
    'https://www.googleapis.com/auth/classroom.rosters.readonly',
    'https://www.googleapis.com/auth/drive.readonly'
]

class ClassroomManager:
    def __init__(self, credentials_path='credentials.json', token_path='token.json'):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.creds = None
        self.classroom_service = None
        self.drive_service = None
        self.user_info = None

    def is_credentials_file_present(self):
        return os.path.exists(self.credentials_path)

    def is_authenticated(self):
        if not os.path.exists(self.token_path):
            return False
        try:
            self.creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            if self.creds and self.creds.valid:
                return True
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
                with open(self.token_path, 'w') as token_file:
                    token_file.write(self.creds.to_json())
                return True
        except Exception:
            return False
        return False

    def login(self):
        """
        Runs OAuth2 browser login flow.
        """
        if not os.path.exists(self.credentials_path):
            raise FileNotFoundError(
                f"No se encontró el archivo '{self.credentials_path}'. "
                "Debes descargar las credenciales OAuth 2.0 (Desktop) de Google Cloud Console "
                "y guardar el archivo como 'credentials.json' en la carpeta de la aplicación."
            )

        if self.is_authenticated():
            self._init_services()
            return self.get_user_info()

        flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
        self.creds = flow.run_local_server(port=0)

        with open(self.token_path, 'w') as token_file:
            token_file.write(self.creds.to_json())

        self._init_services()
        return self.get_user_info()

    def logout(self):
        self.creds = None
        self.classroom_service = None
        self.drive_service = None
        self.user_info = None
        if os.path.exists(self.token_path):
            try:
                os.remove(self.token_path)
            except Exception:
                pass

    def _init_services(self):
        if not self.creds:
            if not self.is_authenticated():
                raise PermissionError("Usuario no autenticado.")

        self.classroom_service = build('classroom', 'v1', credentials=self.creds)
        self.drive_service = build('drive', 'v3', credentials=self.creds)

    def get_user_info(self):
        if not self.creds:
            return None
        try:
            oauth_service = build('oauth2', 'v2', credentials=self.creds)
            self.user_info = oauth_service.userinfo().get().execute()
            return self.user_info
        except Exception as e:
            print(f"Error al obtener info de usuario: {e}")
            return None

    def get_courses(self):
        if not self.classroom_service:
            self._init_services()
        
        courses = []
        page_token = None
        while True:
            response = self.classroom_service.courses().list(
                pageToken=page_token,
                courseStates=['ACTIVE']
            ).execute()
            
            for c in response.get('courses', []):
                courses.append({
                    'id': c['id'],
                    'name': c['name'],
                    'section': c.get('section', ''),
                    'descriptionHeading': c.get('descriptionHeading', '')
                })
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        return courses

    def get_coursework(self, course_id):
        if not self.classroom_service:
            self._init_services()

        coursework = []
        page_token = None
        while True:
            response = self.classroom_service.courses().courseWork().list(
                courseId=course_id,
                pageToken=page_token
            ).execute()

            for cw in response.get('courseWork', []):
                coursework.append({
                    'id': cw['id'],
                    'title': cw['title'],
                    'description': cw.get('description', ''),
                    'creationTime': cw.get('creationTime', ''),
                    'dueDate': cw.get('dueDate', {})
                })
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        return coursework

    def get_students_map(self, course_id):
        """
        Returns a map of { userId: Full Name } for a given course.
        """
        if not self.classroom_service:
            self._init_services()

        students_map = {}
        try:
            response = self.classroom_service.courses().students().list(courseId=course_id).execute()
            for s in response.get('students', []):
                profile = s.get('profile', {})
                user_id = s.get('userId')
                name = profile.get('name', {}).get('fullName', profile.get('emailAddress', user_id))
                students_map[user_id] = name
        except Exception as e:
            print(f"Advertencia al listar estudiantes del curso: {e}")
        return students_map

    def fetch_submissions(self, course_id, coursework_id, dest_dir, progress_callback=None):
        """
        Fetches all student submissions for an assignment and downloads any SolidWorks/zip files.
        Yields progress info and returns list of downloaded file records.
        """
        if not self.classroom_service or not self.drive_service:
            self._init_services()

        students_map = self.get_students_map(course_id)

        # Get all student submissions
        submissions = []
        page_token = None
        while True:
            resp = self.classroom_service.courses().courseWork().studentSubmissions().list(
                courseId=course_id,
                courseWorkId=coursework_id,
                pageToken=page_token
            ).execute()
            submissions.extend(resp.get('studentSubmissions', []))
            page_token = resp.get('nextPageToken')
            if not page_token:
                break

        total_submissions = len(submissions)
        downloaded_records = []

        sw_extensions = ('.sldprt', '.sldasm', '.slddrw', '.zip')

        for idx, sub in enumerate(submissions, start=1):
            user_id = sub.get('userId')
            student_name = students_map.get(user_id)

            if not student_name:
                # Try getting profile directly
                try:
                    p = self.classroom_service.userProfiles().get(userId=user_id).execute()
                    student_name = p.get('name', {}).get('fullName', p.get('emailAddress', user_id))
                except Exception:
                    student_name = f"Alumno ({user_id})"

            if progress_callback:
                progress_callback(idx, total_submissions, f"Revisando entregas de {student_name} ({idx}/{total_submissions})...")

            assignment_sub = sub.get('assignmentSubmission', {})
            attachments = assignment_sub.get('attachments', [])

            for att in attachments:
                drive_file = att.get('driveFile')
                if not drive_file:
                    continue

                file_id = drive_file.get('id')
                file_title = drive_file.get('title', 'sin_nombre')
                ext = os.path.splitext(file_title)[1].lower()

                if ext in sw_extensions:
                    if progress_callback:
                        progress_callback(idx, total_submissions, f"Descargando {file_title} de {student_name}...")

                    # Create student-specific subdirectory to avoid filename collisions
                    student_dir = os.path.join(dest_dir, f"{user_id}")
                    os.makedirs(student_dir, exist_ok=True)
                    local_file_path = os.path.join(student_dir, file_title)

                    try:
                        request = self.drive_service.files().get_media(fileId=file_id)
                        with open(local_file_path, 'wb') as fh:
                            downloader = MediaIoBaseDownload(fh, request)
                            done = False
                            while not done:
                                status, done = downloader.next_chunk()

                        downloaded_records.append({
                            'student_id': user_id,
                            'student_name': student_name,
                            'original_filename': file_title,
                            'local_path': local_file_path,
                            'extension': ext,
                            'file_id': file_id
                        })
                    except Exception as e:
                        print(f"Error descargando archivo {file_title} de Drive: {e}")

        return downloaded_records
