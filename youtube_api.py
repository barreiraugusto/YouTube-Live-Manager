import os
import pickle
import json
import logging
from datetime import datetime, timedelta
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# Configuración de logging
logger = logging.getLogger(__name__)

# Importaciones para OBS
try:
    from obswebsocket import obsws, requests as obs_requests

    OBS_AVAILABLE = True
except ImportError:
    OBS_AVAILABLE = False
    logger.warning("obs-websocket-py no instalado. Instalar con: pip install obs-websocket-py")

SCOPES = [
    'https://www.googleapis.com/auth/youtube.force-ssl',
    'https://www.googleapis.com/auth/youtube.upload'
]


class YouTubeLiveManager:
    def __init__(self, credentials_file='client_secrets.json'):
        self.credentials_file = credentials_file
        self.cache = {}
        self.cache_time = {}
        self.service = self.authenticate()

        # Configuración OBS
        self.obs_ws = None
        self.obs_host = "localhost"
        self.obs_port = 4455
        self.obs_password = ""

        # Archivo donde se guardan los programas
        self.programs_file = 'programs.json'
        self.programs = self._load_programs()

        # Conexión OBS
        self.connect_obs()

    # ==================== CONEXIÓN OBS ====================

    def connect_obs(self):
        """Conectar a OBS Studio vía WebSocket (v5)"""
        if not OBS_AVAILABLE:
            return False
        try:
            # Asegúrate de que el puerto 4455 es el correcto en tus ajustes de OBS
            self.obs_ws = obsws(self.obs_host, self.obs_port, self.obs_password)
            self.obs_ws.connect()
            logger.info("✅ Conectado a OBS Studio (API v5)")
            return True
        except Exception as e:
            logger.warning(f"No se pudo conectar a OBS: {e}")
            return False

    def disconnect_obs(self):
        if self.obs_ws:
            try:
                self.obs_ws.disconnect()
                logger.info("🔌 Desconectado de OBS")
            except:
                pass
            self.obs_ws = None

    def set_stream_key(self, stream_key):
        """Configurar Stream Key en OBS (v5)"""
        if not self.obs_ws:
            self.connect_obs()
        if not self.obs_ws:
            return False
        try:
            self.obs_ws.call(obs_requests.SetStreamServiceSettings(
                streamServiceType="rtmp_custom",
                streamServiceSettings={
                    "server": "rtmp://a.rtmp.youtube.com/live2",
                    "key": stream_key
                }
            ))
            logger.info("✅ Stream key configurada en OBS")
            return True
        except Exception as e:
            logger.error(f"Error configurando stream key: {e}")
            return False

    def _is_obs_streaming(self, status):
        """Función auxiliar robusta para verificar si OBS está transmitiendo"""
        # 1. Forma nativa de obs-websocket-py v1.0 (API v5)
        if hasattr(status, 'getOutputActive'):
            return status.getOutputActive()
        # 2. Si los datos están en un método .data()
        elif hasattr(status, 'data') and callable(status.data):
            return status.data().get('outputActive', False)
        # 3. Si los datos están en un diccionario .data
        elif hasattr(status, 'data') and isinstance(status.data, dict):
            return status.data.get('outputActive', False)
        # 4. Si es un atributo directo
        elif hasattr(status, 'outputActive'):
            return status.outputActive
        return False

    def start_obs_stream(self):
        """Iniciar transmisión en OBS (v5)"""
        if not self.obs_ws:
            self.connect_obs()
        if not self.obs_ws:
            return False
        try:
            status = self.obs_ws.call(obs_requests.GetStreamStatus())
            if self._is_obs_streaming(status):
                logger.info("ℹ️ OBS ya estaba transmitiendo")
                return True

            self.obs_ws.call(obs_requests.StartStream())
            logger.info("▶️ OBS: Orden de inicio enviada")

            import time
            time.sleep(3)  # Esperar a que OBS inicie el encoder

            status = self.obs_ws.call(obs_requests.GetStreamStatus())
            if self._is_obs_streaming(status):
                logger.info("✅ OBS está transmitiendo correctamente")
                return True
            else:
                logger.warning("⚠️ OBS recibió la orden pero el estado no es activo")
                return False
        except Exception as e:
            logger.error(f"Error iniciando OBS: {e}")
            return False

    def stop_obs_stream(self):
        """Detener transmisión en OBS (v5)"""
        if not self.obs_ws:
            self.connect_obs()
        if not self.obs_ws:
            return False
        try:
            status = self.obs_ws.call(obs_requests.GetStreamStatus())
            if self._is_obs_streaming(status):
                self.obs_ws.call(obs_requests.StopStream())
                logger.info("⏹️ OBS: Streaming detenido")
            else:
                logger.info("ℹ️ OBS no estaba transmitiendo")
            return True
        except Exception as e:
            logger.error(f"Error deteniendo OBS: {e}")
            return False

    def change_scene(self, scene_name):
        """Cambiar escena en OBS (v5)"""
        if not self.obs_ws:
            self.connect_obs()
        if not self.obs_ws:
            return False
        try:
            # En v5 el parámetro es sceneName
            self.obs_ws.call(obs_requests.SetCurrentProgramScene(sceneName=scene_name))
            logger.info(f"Escena cambiada a: {scene_name}")
            return True
        except Exception as e:
            logger.error(f"Error cambiando escena: {e}")
            return False

    # ==================== GESTIÓN DE PROGRAMAS ====================

    def _load_programs(self):
        """Cargar programas desde archivo JSON"""
        if os.path.exists(self.programs_file):
            try:
                with open(self.programs_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error cargando programas: {e}")
        return {}

    def _save_programs(self):
        """Guardar programas en archivo JSON"""
        try:
            with open(self.programs_file, 'w', encoding='utf-8') as f:
                json.dump(self.programs, f, indent=2, ensure_ascii=False)
            logger.info("Programas guardados")
            return True
        except Exception as e:
            logger.error(f"Error guardando programas: {e}")
            return False

    def create_program(self, program_id, name, obs_scene=None):
        """Crear un nuevo programa con su propio stream persistente"""
        if program_id in self.programs:
            return {'success': False, 'error': 'Ya existe un programa con ese ID'}

        try:
            # Crear stream persistente en YouTube
            stream_body = {
                'snippet': {'title': f"Stream para {name}"},
                'cdn': {
                    'format': '1080p',
                    'ingestionType': 'rtmp',
                    'frameRate': '30fps',
                    'resolution': '1080p'
                }
            }

            logger.info(f"Creando stream para: {name}")
            stream = self.service.liveStreams().insert(
                part='snippet,cdn',
                body=stream_body
            ).execute()

            program_data = {
                'id': program_id,
                'name': name,
                'stream_id': stream['id'],
                'stream_key': stream['cdn']['ingestionInfo']['streamName'],
                'stream_url': stream['cdn']['ingestionInfo']['ingestionAddress'],
                'obs_scene': obs_scene or name,
                'created_at': datetime.now().isoformat()
            }

            self.programs[program_id] = program_data
            self._save_programs()

            logger.info(f"Programa creado: {name}")

            return {'success': True, 'program': program_data}

        except HttpError as e:
            error_msg = str(e)
            if 'resolution' in error_msg:
                return {'success': False, 'error': 'Error de resolución. Intenta crear el stream manualmente.'}
            return {'success': False, 'error': error_msg}

    def get_program(self, program_id):
        """Obtener un programa por su ID"""
        return self.programs.get(program_id)

    def get_all_programs(self):
        """Obtener todos los programas"""
        return list(self.programs.values())

    def delete_program(self, program_id):
        """Eliminar un programa y su stream asociado"""
        if program_id not in self.programs:
            return {'success': False, 'error': 'Programa no encontrado'}

        program = self.programs[program_id]
        stream_id = program.get('stream_id')

        try:
            # Eliminar el stream de YouTube
            if stream_id:
                self.service.liveStreams().delete(id=stream_id).execute()
                logger.info(f"Stream eliminado: {stream_id}")

            del self.programs[program_id]
            self._save_programs()

            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def update_program(self, program_id, name=None, obs_scene=None):
        """Actualizar un programa existente"""
        if program_id not in self.programs:
            return {'success': False, 'error': 'Programa no encontrado'}

        if name:
            self.programs[program_id]['name'] = name
        if obs_scene:
            self.programs[program_id]['obs_scene'] = obs_scene

        self._save_programs()
        return {'success': True, 'program': self.programs[program_id]}

    # ==================== MÉTODOS PRINCIPALES ====================

    def _get_from_cache(self, key, ttl_seconds=300):
        if key in self.cache and key in self.cache_time:
            if datetime.now() < self.cache_time[key]:
                return self.cache[key]
        return None

    def _set_cache(self, key, value, ttl_seconds=300):
        self.cache[key] = value
        self.cache_time[key] = datetime.now() + timedelta(seconds=ttl_seconds)

    def _clear_cache(self, key=None):
        if key:
            self.cache.pop(key, None)
            self.cache_time.pop(key, None)
        else:
            self.cache.clear()
            self.cache_time.clear()

    def authenticate(self):
        credentials = None
        token_file = 'token.pickle'
        if os.path.exists(token_file):
            try:
                with open(token_file, 'rb') as token:
                    credentials = pickle.load(token)
                logger.info("Credenciales cargadas")
            except Exception as e:
                logger.warning(f"Error: {e}")
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                    logger.info("Credenciales refrescadas")
                except Exception as e:
                    credentials = None
            if not credentials or not credentials.valid:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
                credentials = flow.run_local_server(port=5000, open_browser=True, timeout=120)
        if credentials and credentials.valid:
            with open(token_file, 'wb') as token:
                pickle.dump(credentials, token)
        return build('youtube', 'v3', credentials=credentials)

    def create_scheduled_live(self, title, description, start_time, privacy_status='unlisted', program_id=None,
                              is_immediate=False, made_for_kids=False, thumbnail_url=None, delete_after='never'):
        try:
            if not program_id or program_id not in self.programs:
                return {'success': False, 'error': 'Programa no válido'}

            program = self.programs[program_id]
            stream_id = program.get('stream_id')
            stream_key = program.get('stream_key')
            stream_url = program.get('stream_url')

            if not stream_id:
                return {'success': False, 'error': 'El programa no tiene un stream asociado'}

            broadcast_body = {
                'snippet': {
                    'title': title,
                    'description': description
                },
                'status': {
                    'privacyStatus': privacy_status,
                    'selfDeclaredMadeForKids': bool(made_for_kids)
                },
                'contentDetails': {
                    'enableAutoStop': True,
                    'latencyPreference': 'ultraLow',
                    'enableDvr': True,
                    'recordFromStart': True
                }
            }

            # Si es inmediato, no incluir scheduledStartTime
            if not is_immediate and start_time:
                if isinstance(start_time, datetime):
                    import pytz
                    # 1. Si no tiene zona horaria, asumimos que es local o la que sea, y la pasamos a UTC
                    if start_time.tzinfo is None:
                        start_time = pytz.UTC.localize(start_time)
                    else:
                        # 🔧 CORRECCIÓN CLAVE: Convertir explícitamente a UTC
                        start_time = start_time.astimezone(pytz.UTC)

                    # 2. Ahora sí formateamos el string con la hora UTC real
                    formatted_start_time = start_time.strftime('%Y-%m-%dT%H:%M:%S.000Z')
                else:
                    formatted_start_time = start_time

                broadcast_body['snippet']['scheduledStartTime'] = formatted_start_time
                broadcast_body['contentDetails']['enableAutoStart'] = False
                logger.info(f"Broadcast programado: {formatted_start_time}")
            else:
                # Para inicio inmediato
                broadcast_body['contentDetails']['enableAutoStart'] = True
                logger.info("Broadcast de inicio inmediato")

            broadcast = self.service.liveBroadcasts().insert(
                part='snippet,status,contentDetails',
                body=broadcast_body
            ).execute()

            logger.info(f"✅ Broadcast creado: {broadcast['id']}")

            # Vincular broadcast con el stream
            self.service.liveBroadcasts().bind(
                part='id,contentDetails',
                id=broadcast['id'],
                streamId=stream_id
            ).execute()

            logger.info(f"Broadcast vinculado al stream: {stream_id}")

            # Subir miniatura si se proporciona
            thumbnail_uploaded = False
            if thumbnail_url and thumbnail_url.startswith('data:image'):
                try:
                    thumbnail_uploaded = self._upload_thumbnail(broadcast['id'], thumbnail_url)
                    logger.info(f"Miniatura {'subida' if thumbnail_uploaded else 'falló'} para broadcast: {broadcast['id']}")
                except Exception as e:
                    logger.error(f"Error subiendo miniatura: {e}")

            # Configurar eliminación automática si corresponde
            if delete_after and delete_after != 'never':
                try:
                    self._schedule_video_deletion(broadcast['id'], delete_after)
                    logger.info(f"Eliminación programada para {delete_after} en broadcast: {broadcast['id']}")
                except Exception as e:
                    logger.error(f"Error programando eliminación: {e}")

            self._clear_cache('live_broadcasts')

            return {
                'success': True,
                'broadcast_id': broadcast['id'],
                'stream_key': stream_key,
                'stream_url': stream_url,
                'title': title,
                'start_time': formatted_start_time if not is_immediate else datetime.now().isoformat(),
                'thumbnail_uploaded': thumbnail_uploaded,
                'delete_after': delete_after
            }
        except HttpError as e:
            error_msg = str(e)
            logger.error(f"Error en create_scheduled_live: {error_msg}")
            return {'success': False, 'error': error_msg}

    def update_live_metadata(self, broadcast_id, title=None, description=None):
        try:
            broadcast = self.service.liveBroadcasts().list(part='snippet', id=broadcast_id).execute()
            if not broadcast['items']:
                raise Exception('Broadcast no encontrado')
            broadcast_info = broadcast['items'][0]
            if title:
                broadcast_info['snippet']['title'] = title
            if description:
                broadcast_info['snippet']['description'] = description
            updated = self.service.liveBroadcasts().update(part='snippet', body=broadcast_info).execute()
            self._clear_cache('live_broadcasts')
            return updated
        except HttpError as e:
            logger.error(f"Error: {e}")
            raise

    def delete_broadcast(self, broadcast_id):
        try:
            self.service.liveBroadcasts().delete(id=broadcast_id).execute()
            self._clear_cache('live_broadcasts')
            return True
        except HttpError as e:
            logger.error(f"Error: {e}")
            return False

    def update_privacy_status(self, video_id, privacy_status):
        try:
            video = self.service.videos().list(part='status', id=video_id).execute()
            if video['items']:
                video_info = video['items'][0]
                video_info['status']['privacyStatus'] = privacy_status
                self.service.videos().update(part='status', body=video_info).execute()
                self._clear_cache('live_broadcasts')
                return True
            return False
        except HttpError as e:
            logger.error(f"Error: {e}")
            return False

    def list_playlists(self, use_cache=True):
        cache_key = 'playlists'
        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached:
                return cached
        try:
            playlists = self.service.playlists().list(part='snippet', mine=True, maxResults=50).execute()
            result = [{'id': p['id'], 'title': p['snippet']['title']} for p in playlists.get('items', [])]
            if use_cache:
                self._set_cache(cache_key, result)
            return result
        except HttpError as e:
            logger.error(f"Error: {e}")
            return []

    def get_my_live_broadcasts(self, use_cache=True):
        cache_key = 'live_broadcasts'
        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached:
                return cached
        try:
            broadcasts = self.service.liveBroadcasts().list(part='snippet,status', mine=True, maxResults=50).execute()
            result = broadcasts.get('items', [])
            if use_cache:
                self._set_cache(cache_key, result)
            return result
        except HttpError as e:
            if e.resp.status == 403 and 'quotaExceeded' in str(e):
                cached = self._get_from_cache(cache_key)
                if cached:
                    return cached
            logger.error(f"Error: {e}")
            raise

    def _upload_thumbnail(self, broadcast_id, thumbnail_data_url):
        """Subir miniatura desde Data URL (Base64) a YouTube"""
        try:
            import base64
            import io
            from PIL import Image
            
            # Extraer datos Base64 de la URL
            header, encoded = thumbnail_data_url.split(',', 1)
            image_data = base64.b64decode(encoded)
            
            # Crear archivo temporal para la imagen
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                # Convertir y guardar imagen (asegurar formato JPG)
                img = Image.open(io.BytesIO(image_data))
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                img.save(tmp_file.name, 'JPEG', quality=95)
                tmp_path = tmp_file.name
            
            try:
                # Subir miniatura usando API de YouTube
                upload = MediaFileUpload(tmp_path, mimetype='image/jpeg', resumable=True)
                self.service.thumbnails().set(
                    videoId=broadcast_id,
                    media_body=upload
                ).execute()
                
                return True
            finally:
                # Limpiar archivo temporal
                import os
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    
        except Exception as e:
            logger.error(f"Error subiendo miniatura: {e}")
            return False

    def _schedule_video_deletion(self, broadcast_id, delete_after):
        """Programar eliminación del video después de X tiempo post-transmisión"""
        try:
            # Obtener información del broadcast para encontrar el video asociado
            broadcast = self.service.liveBroadcasts().list(
                part='snippet,contentDetails,status',
                id=broadcast_id
            ).execute()
            
            if not broadcast.get('items'):
                logger.warning(f"No se encontró broadcast con ID {broadcast_id}")
                return False
            
            broadcast_info = broadcast['items'][0]
            
            # Nota: La eliminación automática requiere lógica adicional post-transmisión
            # Aquí solo registramos la intención. La ejecución real debería hacerse
            # vía scheduler o webhook cuando termine el live.
            logger.info(f"Eliminación programada: {delete_after} para broadcast {broadcast_id}")
            
            # Guardar metadatos de eliminación en archivo local para procesamiento posterior
            deletion_config_file = 'deletion_schedule.json'
            deletion_jobs = {}
            
            if os.path.exists(deletion_config_file):
                try:
                    with open(deletion_config_file, 'r', encoding='utf-8') as f:
                        deletion_jobs = json.load(f)
                except:
                    deletion_jobs = {}
            
            deletion_jobs[broadcast_id] = {
                'delete_after': delete_after,
                'scheduled_at': datetime.now().isoformat(),
                'status': 'pending'
            }
            
            with open(deletion_config_file, 'w', encoding='utf-8') as f:
                json.dump(deletion_jobs, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            logger.error(f"Error programando eliminación: {e}")
            return False
