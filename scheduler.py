from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import pytz
import json
import os

DAYS = {
    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
    'friday': 4, 'saturday': 5, 'sunday': 6
}


class LiveScheduler:
    def __init__(self, youtube_manager):
        self.scheduler = BackgroundScheduler()
        self.youtube = youtube_manager
        self.scheduled_jobs = {}
        self.active_streams = {}
        self.timezone = pytz.timezone('America/Buenos_Aires')

        # 🔧 NUEVO: Archivo para guardar las programaciones
        self.schedules_file = 'schedules.json'

        # 🔧 NUEVO: Cargar programaciones al iniciar
        self._load_schedules()

        print(f"⏰ Zona horaria configurada: {self.timezone}")

    def _load_schedules(self):
        """Carga las programaciones desde el archivo JSON y las registra en APScheduler"""
        if not os.path.exists(self.schedules_file):
            return

        try:
            with open(self.schedules_file, 'r', encoding='utf-8') as f:
                saved_schedules = json.load(f)
        except Exception as e:
            print(f"⚠️ Error cargando schedules.json: {e}")
            return

        print(f"📂 Cargando {len(saved_schedules)} programaciones guardadas...")

        for item in saved_schedules:
            job_id = item['job_id']
            job_type = item.get('type')  # Puede ser 'create', 'start' o 'end'

            # Recrear el trigger (el reloj) de APScheduler
            trigger = CronTrigger(
                day_of_week=int(item['day']),
                hour=int(item['hour']),
                minute=int(item['minute']),
                timezone=self.timezone
            )

            next_run = trigger.get_next_fire_time(None, datetime.now(self.timezone))

            # ==========================================
            # 1. CARGAR TAREA DE CREACIÓN DE BROADCAST
            # ==========================================
            if job_type == 'create':
                create_before_minutes = 5  # Default al recargar
                job = self.scheduler.add_job(
                    func=self._create_broadcast_before_stream,
                    trigger=trigger,
                    id=job_id,
                    args=[
                        item['title'],
                        item.get('description', ''),
                        item.get('privacy', 'unlisted'),
                        job_id.replace('_create', ''),
                        item['program_id'],
                        False,  # made_for_kids
                        create_before_minutes,
                        item.get('thumbnail_path')
                    ],
                    replace_existing=True
                )
                self.scheduled_jobs[job_id] = {
                    'job': job,
                    'title': item['title'],
                    'description': item.get('description', ''),
                    'day': int(item['day']),
                    'hour': int(item['hour']),
                    'minute': int(item['minute']),
                    'privacy': item.get('privacy', 'unlisted'),
                    'type': 'create',
                    'program_id': item['program_id'],
                    'group_key': item['group_key'],
                    'thumbnail_path': item.get('thumbnail_path'),
                    'thumbnail_url': item.get('thumbnail_url'),  # 🔧 NUEVO: Cargar URL
                    'next_run': next_run
                }
                print(f"   📡 Restaurada tarea de CREACIÓN: {job_id}")

            # ==========================================
            # 2. CARGAR TAREA DE INICIO
            # ==========================================
            elif job_type == 'start':
                job = self.scheduler.add_job(
                    func=self._start_live_stream,
                    trigger=trigger,
                    id=job_id,
                    args=[
                        item['title'],
                        item.get('description', ''),
                        item.get('privacy', 'unlisted'),
                        job_id,
                        item['program_id'],
                        item.get('broadcast_id')
                    ],
                    replace_existing=True
                )
                self.scheduled_jobs[job_id] = {
                    'job': job,
                    'title': item['title'],
                    'description': item.get('description', ''),
                    'day': int(item['day']),
                    'hour': int(item['hour']),
                    'minute': int(item['minute']),
                    'privacy': item.get('privacy', 'unlisted'),
                    'type': 'start',
                    'program_id': item['program_id'],
                    'broadcast_id': item.get('broadcast_id'),
                    'group_key': item['group_key'],
                    'thumbnail_path': item.get('thumbnail_path'),
                    'thumbnail_url': item.get('thumbnail_url'),  # 🔧 NUEVO: Cargar URL
                    'next_run': next_run
                }
                print(f"   ▶️ Restaurada tarea de INICIO: {job_id}")

            # ==========================================
            # 3. CARGAR TAREA DE FIN
            # ==========================================
            elif job_type == 'end':
                job = self.scheduler.add_job(
                    func=self._end_live_stream,
                    trigger=trigger,
                    id=job_id,
                    args=[
                        item['program_id'],
                        item.get('post_stream_action', 'none')  # 🔧 NUEVO: Pasar la acción a la función
                    ],
                    replace_existing=True
                )
                self.scheduled_jobs[job_id] = {
                    'job': job,
                    'title': item['title'],
                    'day': int(item['day']),
                    'hour': int(item['hour']),
                    'minute': int(item['minute']),
                    'type': 'end',
                    'program_id': item['program_id'],
                    'group_key': item['group_key'],
                    'post_stream_action': item.get('post_stream_action', 'none'),  # 🔧 NUEVO: Guardar en memoria
                    'next_run': next_run
                }
                print(f"   ⏹️ Restaurada tarea de FIN: {job_id}")

        print(f"✅ Programaciones restauradas correctamente.")

    def _save_schedules(self):
        """Guarda el estado actual de las programaciones en un archivo JSON"""
        data_to_save = []
        for job_id, info in self.scheduled_jobs.items():
            data_to_save.append({
                'job_id': job_id,
                'title': info['title'],
                'description': info.get('description', ''),
                'day': info['day'],
                'hour': info['hour'],
                'minute': info['minute'],
                'privacy': info.get('privacy', 'unlisted'),
                'type': info['type'],
                'program_id': info['program_id'],
                'broadcast_id': info.get('broadcast_id'),
                'group_key': info['group_key'],
                'thumbnail_path': info.get('thumbnail_path'), # 🔧 AGREGAR
                'thumbnail_url': info.get('thumbnail_url'),
                'post_stream_action': info.get('post_stream_action', 'none')
            })

        try:
            with open(self.schedules_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Error guardando schedules.json: {e}")

    def schedule_live(self, job_id, day_of_week, hour, minute,
                      title, description, privacy_status='unlisted',
                      is_start=True, program_id=None, made_for_kids=False,
                      create_before_minutes=5, thumbnail_path=None,
                      thumbnail_url=None, post_stream_action='none'):
        """Programa una tarea sin crear el broadcast inmediatamente"""

        trigger = CronTrigger(
            day_of_week=day_of_week,
            hour=hour,
            minute=minute,
            timezone=self.timezone
        )

        if job_id in self.scheduled_jobs:
            self.remove_job(job_id, save_to_disk=False)

        print(f"\n📝 Programando tarea: {job_id}")
        print(f"   Título: {title}")
        print(f"   Día: {self._get_day_name(day_of_week)} ({day_of_week})")
        print(f"   Hora: {hour:02d}:{minute:02d}")
        print(f"   Tipo: {'INICIO' if is_start else 'FIN'}")
        print(f"   Programa: {program_id}")

        next_run = trigger.get_next_fire_time(None, datetime.now(self.timezone))

        # NO creamos el broadcast aquí, solo programamos la tarea
        if is_start:
            # Programar creación del broadcast X minutos antes
            # Programar creación del broadcast X minutos antes
            if create_before_minutes > 0:
                create_job_id = f"{job_id}_create"

                # 🔧 CORRECCIÓN: Calcular hora y minuto restando minutos con timedelta
                dummy_time = datetime(2000, 1, 1, hour, minute)
                create_time = dummy_time - timedelta(minutes=create_before_minutes)
                create_hour = create_time.hour
                create_minute = create_time.minute

                # Ajustar día de la semana si al restar cruzamos la medianoche
                create_day_of_week = day_of_week
                if create_time.day < dummy_time.day:
                    create_day_of_week = (day_of_week - 1) % 7

                create_trigger = CronTrigger(
                    day_of_week=create_day_of_week,
                    hour=create_hour,
                    minute=create_minute,
                    timezone=self.timezone
                )

                create_job = self.scheduler.add_job(
                    func=self._create_broadcast_before_stream,
                    trigger=create_trigger,
                    id=create_job_id,
                    # 🔧 AGREGAR thumbnail_path al final
                    args=[title, description, privacy_status, job_id, program_id, made_for_kids, create_before_minutes,
                          thumbnail_path],
                    replace_existing=True
                )

                self.scheduled_jobs[create_job_id] = {
                    'job': create_job,
                    'title': title,
                    'description': description,
                    'thumbnail_url': thumbnail_url,
                    'day': create_day_of_week,
                    'hour': create_hour,
                    'minute': create_minute,
                    'privacy': privacy_status,
                    'type': 'create',
                    'program_id': program_id,
                    'group_key': f"{program_id}|{title}",
                    'thumbnail_path': thumbnail_path,  # 🔧 GUARDAR EN MEMORIA
                    'next_run': create_trigger.get_next_fire_time(None, datetime.now(self.timezone))
                }
                print(
                    f"   📡 Broadcast se creará {create_before_minutes} min antes ({create_hour:02d}:{create_minute:02d})")

            # Programar inicio del stream
            job = self.scheduler.add_job(
                func=self._start_live_stream,
                trigger=trigger,
                id=job_id,
                args=[title, description, privacy_status, job_id, program_id, None],  # broadcast_id será None
                replace_existing=True
            )
            self.scheduled_jobs[job_id] = {
                'job': job,
                'title': title,
                'description': description,
                'thumbnail_url': thumbnail_url,
                'day': day_of_week,
                'hour': hour,
                'minute': minute,
                'privacy': privacy_status,
                'type': 'start',
                'program_id': program_id,
                'broadcast_id': None,
                'group_key': f"{program_id}|{title}",
                'next_run': next_run
            }
        else:
            job = self.scheduler.add_job(
                func=self._end_live_stream,
                trigger=trigger,
                id=job_id,
                args=[program_id, post_stream_action],
                replace_existing=True
            )
            self.scheduled_jobs[job_id] = {
                'job': job,
                'title': title,
                'day': day_of_week,
                'hour': hour,
                'minute': minute,
                'type': 'end',
                'program_id': program_id,
                'group_key': f"{program_id}|{title}",
                'post_stream_action': post_stream_action,
                'next_run': next_run
            }

        self._save_schedules()
        print(f"✅ Tarea programada correctamente")
        return job

    def _create_broadcast_before_stream(self, title, description, privacy_status, job_id,
                                        program_id, made_for_kids, create_before_minutes=5,
                                        thumbnail_path=None):
        """Crea el broadcast X minutos antes de iniciar"""
        try:
            now = datetime.now(self.timezone)
            print(f"\n{'=' * 70}")
            print(f"📡 CREANDO BROADCAST PROGRAMADO")
            print(f"📅 Hora actual: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"📺 Título: {title}")
            if thumbnail_path:
                print(f"🖼️ Thumbnail: {thumbnail_path}")
            print(f"{'=' * 70}\n")

            start_time = now + timedelta(minutes=create_before_minutes)

            result = self.youtube.create_scheduled_live(
                title=title,
                description=description,
                start_time=start_time,
                privacy_status=privacy_status,
                program_id=program_id,
                is_immediate=False,
                made_for_kids=made_for_kids,
                thumbnail_path=thumbnail_path  # 🔧 PASAR A YOUTUBE API
            )

            if result.get('success'):
                broadcast_id = result['broadcast_id']
                print(f"✅ Broadcast creado: {broadcast_id}")

                start_job_id = job_id.replace('_create', '')
                if start_job_id in self.scheduled_jobs:
                    self.scheduled_jobs[start_job_id]['broadcast_id'] = broadcast_id
                    print(f"✅ broadcast_id actualizado en tarea de inicio")
                    self._save_schedules()
                else:
                    print(f"⚠️ No se encontró la tarea de inicio")

            else:
                print(f"❌ Error creando broadcast: {result.get('error')}")

        except Exception as e:
            print(f"❌ ERROR creando broadcast: {e}")
            import traceback
            traceback.print_exc()

    def _start_live_stream(self, title, description, privacy_status, job_id, program_id, broadcast_id):
        """Ejecutar la tarea programada: iniciar el live"""
        try:
            now = datetime.now(self.timezone)
            print(f"\n{'=' * 70}")
            print(f"🔔 ¡INICIANDO LIVE PROGRAMADO!")
            print(f"📅 Hora actual: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"📺 Título: {title}")
            print(f"🔍 job_id recibido: {job_id}")
            print(f"🔍 broadcast_id recibido: {broadcast_id}")
            print(f"{'=' * 70}\n")

            # 1. Intentar obtenerlo de la memoria
            if not broadcast_id:
                print(f"🔍 Buscando broadcast_id en memoria para job_id: {job_id}")
                broadcast_id = self.scheduled_jobs.get(job_id, {}).get('broadcast_id')
                print(f"   Resultado en memoria: {broadcast_id}")

            # 2. 🔧 FALLBACK: Si aún no lo tenemos, buscarlo en YouTube
            if not broadcast_id:
                print(f"🔍 broadcast_id no encontrado en memoria. Buscando en YouTube...")
                broadcast_id = self._find_recent_broadcast(title, program_id)
                if broadcast_id:
                    print(f"✅ Broadcast encontrado en YouTube: {broadcast_id}")
                else:
                    print("❌ No se pudo encontrar el broadcast en YouTube. Abortando.")
                    return None

            print(f"📡 Usando broadcast: {broadcast_id}")

            # Configurar OBS
            program = self.youtube.get_program(program_id)
            stream_key = program.get('stream_key')
            stream_id = program.get('stream_id')

            print("🎬 Configurando OBS...")
            if stream_key and self.youtube.set_stream_key(stream_key):
                print("✅ Stream key configurada")

            if program and program.get('obs_scene'):
                self.youtube.change_scene(program['obs_scene'])

            # INICIAR OBS
            print("🎥 Iniciando transmisión en OBS...")
            if not self.youtube.start_obs_stream():
                print("❌ No se pudo iniciar OBS")
                return None
            print("✅ OBS está transmitiendo")

            # ESPERAR A QUE YOUTUBE DETECTE EL STREAM
            print("⏳ Esperando a que YouTube detecte la señal de OBS...")
            import time
            stream_is_active = False

            for attempt in range(15):
                try:
                    stream_resp = self.youtube.service.liveStreams().list(
                        part='status',
                        id=stream_id
                    ).execute()

                    if stream_resp.get('items'):
                        stream_status = stream_resp['items'][0]['status']['streamStatus']
                        print(f"   🔍 Estado del stream: {stream_status} (intento {attempt + 1}/15)")

                        if stream_status == 'active':
                            stream_is_active = True
                            print("✅ ¡YouTube está recibiendo la señal correctamente!")
                            break
                except Exception as e:
                    print(f"   ⚠️ Error consultando stream: {e}")

                time.sleep(2)

            if not stream_is_active:
                print("❌ ERROR: YouTube no detectó el stream como 'active' a tiempo.")
                self.youtube.stop_obs_stream()
                return None

            # TRANSICIONES DEL BROADCAST
            try:
                broadcast_resp = self.youtube.service.liveBroadcasts().list(
                    part='status',
                    id=broadcast_id
                ).execute()

                current_status = broadcast_resp['items'][0]['status']['lifeCycleStatus']
                print(f"📺 Estado actual del broadcast: {current_status}")

                if current_status == 'ready':
                    print("🔄 Transicionando a 'testing'...")
                    self.youtube.service.liveBroadcasts().transition(
                        part='status',
                        id=broadcast_id,
                        broadcastStatus='testing'
                    ).execute()
                    print("✅ Broadcast en modo testing")
                    time.sleep(3)
                    current_status = 'testing'

                if current_status == 'testing':
                    print("🔄 Transicionando a 'live' (EN VIVO)...")
                    self.youtube.service.liveBroadcasts().transition(
                        part='status',
                        id=broadcast_id,
                        broadcastStatus='live'
                    ).execute()
                    print("✅ ¡Broadcast ahora EN VIVO para el público!")
                elif current_status == 'live':
                    print("ℹ️ El broadcast ya estaba EN VIVO.")

            except Exception as e:
                print(f"❌ Error en transición: {e}")
                self.youtube.stop_obs_stream()
                return None

            self.active_streams[broadcast_id] = {
                'title': title,
                'start_time': now,
                'broadcast_id': broadcast_id,
                'stream_key': stream_key,
                'program_id': program_id
            }

            print(f"\n✅ ¡LIVE INICIADO EXITOSAMENTE!")
            print(f"📺 URL: https://youtube.com/live/{broadcast_id}")
            return {'success': True, 'broadcast_id': broadcast_id}

        except Exception as e:
            print(f"❌ ERROR GENERAL: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _find_recent_broadcast(self, title, program_id):
        """Buscar el broadcast más reciente que coincida con el título (insensible a mayúsculas)"""
        try:
            broadcasts = self.youtube.get_my_live_broadcasts(use_cache=False)
            target_title = title.strip().lower()

            for broadcast in broadcasts:
                snippet = broadcast.get('snippet', {})
                status = broadcast.get('status', {})

                broadcast_title = snippet.get('title', '').strip().lower()
                lifecycle = status.get('lifeCycleStatus')

                # Coincidencia flexible y que esté listo para iniciar
                if (broadcast_title == target_title and
                        lifecycle in ['ready', 'created', 'testing']):
                    return broadcast['id']
            return None
        except Exception as e:
            print(f"Error buscando broadcast en YouTube: {e}")
            return None

    def _start_live_stream(self, title, description, privacy_status, job_id, program_id, broadcast_id_ignored):
        """Ejecutar la tarea programada: iniciar el live"""
        try:
            now = datetime.now(self.timezone)
            print(f"\n{'=' * 70}")
            print(f"🔔 ¡INICIANDO LIVE PROGRAMADO!")
            print(f"📅 Hora actual: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"📺 Título: {title}")
            print(f"🔍 job_id: {job_id}")
            print(f"🔍 program_id: {program_id}")
            print(f"{'=' * 70}\n")

            # 🔧 IGNORAR el argumento broadcast_id_ignored (viene como None de APScheduler)
            # Buscar SIEMPRE en el diccionario de scheduled_jobs
            broadcast_id = None

            # Intento 1: Buscar en scheduled_jobs
            if job_id in self.scheduled_jobs:
                broadcast_id = self.scheduled_jobs[job_id].get('broadcast_id')
                print(f"📋 Buscando en scheduled_jobs['{job_id}']:")
                print(f"   broadcast_id = {broadcast_id}")
            else:
                print(f"⚠️ job_id '{job_id}' NO encontrado en scheduled_jobs")
                print(f"   Claves disponibles: {list(self.scheduled_jobs.keys())}")

            # Intento 2: Buscar por título si no se encontró
            if not broadcast_id:
                print(f"🔍 Buscando broadcast en YouTube por título: '{title}'")
                broadcast_id = self._find_recent_broadcast(title, program_id)
                if broadcast_id:
                    print(f"✅ Broadcast encontrado en YouTube: {broadcast_id}")
                    # Guardarlo para futuras referencias
                    if job_id in self.scheduled_jobs:
                        self.scheduled_jobs[job_id]['broadcast_id'] = broadcast_id
                        self._save_schedules()
                else:
                    print("❌ No se pudo encontrar el broadcast en YouTube")

            if not broadcast_id:
                print("❌ ERROR CRÍTICO: No se pudo obtener broadcast_id de ninguna fuente")
                print("💡 Verifica que _create_broadcast_before_stream se ejecutó correctamente")
                return None

            print(f"📡 Usando broadcast_id: {broadcast_id}")

            # Configurar OBS
            program = self.youtube.get_program(program_id)
            if not program:
                print(f"❌ Programa '{program_id}' no encontrado")
                return None

            stream_key = program.get('stream_key')
            stream_id = program.get('stream_id')

            print("🎬 Configurando OBS...")
            if stream_key and self.youtube.set_stream_key(stream_key):
                print("✅ Stream key configurada")

            if program.get('obs_scene'):
                self.youtube.change_scene(program['obs_scene'])

            # INICIAR OBS
            print("🎥 Iniciando transmisión en OBS...")
            if not self.youtube.start_obs_stream():
                print("❌ No se pudo iniciar OBS")
                return None
            print("✅ OBS está transmitiendo")

            # ESPERAR A QUE YOUTUBE DETECTE EL STREAM
            print("⏳ Esperando a que YouTube detecte la señal de OBS...")
            import time
            stream_is_active = False

            for attempt in range(20):  # Aumentado a 20 intentos (40 segundos)
                try:
                    stream_resp = self.youtube.service.liveStreams().list(
                        part='status',
                        id=stream_id
                    ).execute()

                    if stream_resp.get('items'):
                        stream_status = stream_resp['items'][0]['status']['streamStatus']
                        print(f"   🔍 Estado del stream: {stream_status} (intento {attempt + 1}/20)")

                        if stream_status == 'active':
                            stream_is_active = True
                            print("✅ ¡YouTube está recibiendo la señal correctamente!")
                            break
                except Exception as e:
                    print(f"   ⚠️ Error consultando stream: {e}")

                time.sleep(2)

            if not stream_is_active:
                print("❌ ERROR: YouTube no detectó el stream como 'active' a tiempo")
                print("💡 Verifica:")
                print("   1. OBS está transmitiendo correctamente")
                print("   2. Keyframes configurados a 2 segundos en OBS")
                print("   3. La Stream Key es correcta")
                self.youtube.stop_obs_stream()
                return None

            # TRANSICIONES DEL BROADCAST
            try:
                broadcast_resp = self.youtube.service.liveBroadcasts().list(
                    part='status',
                    id=broadcast_id
                ).execute()

                if not broadcast_resp.get('items'):
                    print(f"❌ Broadcast {broadcast_id} no encontrado en YouTube")
                    return None

                current_status = broadcast_resp['items'][0]['status']['lifeCycleStatus']
                print(f"📺 Estado actual del broadcast: {current_status}")

                if current_status == 'ready':
                    print("🔄 Transicionando a 'testing'...")
                    self.youtube.service.liveBroadcasts().transition(
                        part='status',
                        id=broadcast_id,
                        broadcastStatus='testing'
                    ).execute()
                    print("✅ Broadcast en modo testing")
                    time.sleep(5)
                    current_status = 'testing'

                if current_status == 'testing':
                    print("🔄 Transicionando a 'live' (EN VIVO)...")
                    self.youtube.service.liveBroadcasts().transition(
                        part='status',
                        id=broadcast_id,
                        broadcastStatus='live'
                    ).execute()
                    print("✅ ¡Broadcast ahora EN VIVO para el público!")
                elif current_status == 'live':
                    print("ℹ️ El broadcast ya estaba EN VIVO")
                elif current_status == 'created':
                    print("⚠️ Broadcast aún en estado 'created', intentando forzar transición...")
                    # Intentar pasar directamente a testing
                    self.youtube.service.liveBroadcasts().transition(
                        part='status',
                        id=broadcast_id,
                        broadcastStatus='testing'
                    ).execute()
                    time.sleep(3)
                    self.youtube.service.liveBroadcasts().transition(
                        part='status',
                        id=broadcast_id,
                        broadcastStatus='live'
                    ).execute()
                    print("✅ Broadcast forzado a EN VIVO")

            except Exception as e:
                print(f"❌ Error en transición: {e}")
                import traceback
                traceback.print_exc()
                self.youtube.stop_obs_stream()
                return None

            self.active_streams[broadcast_id] = {
                'title': title,
                'start_time': now,
                'broadcast_id': broadcast_id,
                'stream_key': stream_key,
                'program_id': program_id
            }

            print(f"\n✅ ¡LIVE INICIADO EXITOSAMENTE!")
            print(f"📺 URL: https://youtube.com/live/{broadcast_id}")
            return {'success': True, 'broadcast_id': broadcast_id}

        except Exception as e:
            print(f"❌ ERROR GENERAL: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _find_scheduled_broadcast(self, program_id, title):
        """Buscar broadcast programado existente para este programa"""
        try:
            broadcasts = self.youtube.get_my_live_broadcasts(use_cache=False)
            for broadcast in broadcasts:
                snippet = broadcast.get('snippet', {})
                status = broadcast.get('status', {})
                if (snippet.get('title') == title and
                        status.get('lifeCycleStatus') in ['ready', 'created']):
                    print(f"✅ Broadcast encontrado: {broadcast['id']}")
                    return broadcast['id']
            return None
        except Exception as e:
            print(f"Error buscando broadcast: {e}")
            return None

    def _end_live_stream(self, program_id, post_stream_action='none'):
        """Finalizar transmisión y ejecutar acción post-stream"""
        try:
            now = datetime.now(self.timezone)
            print(f"\n{'=' * 70}")
            print(f"🔔 FINALIZANDO TRANSMISIÓN")
            print(f"📅 Hora: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"📡 Programa: {program_id}")

            # 1. Finalizar todos los broadcasts activos de este programa
            for broadcast_id in list(self.active_streams.keys()):
                if broadcast_id in self.active_streams:
                    stream_info = self.active_streams[broadcast_id]
                    if stream_info.get('program_id') == program_id:
                        try:
                            # Transicionar a complete
                            self.youtube.service.liveBroadcasts().transition(
                                part='status', id=broadcast_id, broadcastStatus='complete'
                            ).execute()
                            del self.active_streams[broadcast_id]
                            print(f"✅ Transmisión finalizada: {broadcast_id}")

                            # 🔧 EJECUTAR ACCIÓN POST-STREAM
                            if post_stream_action == 'private':
                                print(f"🔒 Ocultando video {broadcast_id} (Privado)...")
                                self.youtube.update_privacy_status(broadcast_id, 'private')
                            elif post_stream_action == 'delete':
                                print(f"🗑️ Eliminando broadcast {broadcast_id}...")
                                self.youtube.delete_broadcast(broadcast_id)

                        except Exception as e:
                            print(f"⚠️ Error finalizando: {e}")

            # 2. Detener OBS
            print("⏹️ Deteniendo transmisión en OBS...")
            self.youtube.stop_obs_stream()

            # 3. 🔧 CAMBIAR A ESCENA "TANDA"
            print("🎬 Cambiando a escena 'Tanda'...")
            try:
                if self.youtube.change_scene("Tanda"):
                    print("✅ Escena cambiada a 'Tanda'")
                else:
                    print("⚠️ No se pudo cambiar a 'Tanda'. Verifica que la escena exista en OBS.")
            except Exception as e:
                print(f"⚠️ Error cambiando a 'Tanda': {e}")

            print(f"{'=' * 70}\n")

        except Exception as e:
            print(f"❌ Error finalizando: {e}")
            import traceback
            traceback.print_exc()

    def get_active_streams(self):
        return list(self.active_streams.values())

    def update_schedule_group(self, group_key, new_title, new_description, new_privacy,
                              new_start_hour, new_start_minute, new_end_hour, new_end_minute,
                              new_selected_days):
        """Actualizar todas las programaciones de un grupo"""
        try:
            # 1. Obtener información del grupo existente
            existing_jobs = []
            program_id = None

            for job_id, info in list(self.scheduled_jobs.items()):
                if info.get('group_key') == group_key:
                    existing_jobs.append({
                        'job_id': job_id,
                        'info': info
                    })
                    if not program_id:
                        program_id = info.get('program_id')

            if not existing_jobs:
                return {'success': False, 'error': 'Grupo no encontrado'}

            # 2. Eliminar todas las tareas existentes del grupo
            removed_count = self.remove_group(group_key)
            print(f"🗑️ Eliminadas {removed_count} tareas antiguas del grupo")

            # 3. Crear nuevas tareas con los nuevos parámetros
            base_job_id = f"live_{datetime.now().timestamp()}"
            scheduled_days = []

            for day_key in new_selected_days:
                if day_key not in DAYS:
                    continue

                job_id = f"{base_job_id}_{day_key}"

                # Programar inicio
                self.schedule_live(
                    job_id=f"{job_id}_start",
                    day_of_week=DAYS[day_key],
                    hour=int(new_start_hour),
                    minute=int(new_start_minute),
                    title=new_title,
                    description=new_description,
                    privacy_status=new_privacy,
                    is_start=True,
                    program_id=program_id
                )

                # Programar fin
                self.schedule_live(
                    job_id=f"{job_id}_end",
                    day_of_week=DAYS[day_key],
                    hour=int(new_end_hour),
                    minute=int(new_end_minute),
                    title=new_title,
                    description=new_description,
                    privacy_status=new_privacy,
                    is_start=False,
                    program_id=program_id
                )

                scheduled_days.append(day_key)

            return {
                'success': True,
                'removed_count': removed_count,
                'new_count': len(scheduled_days) * 2,
                'scheduled_days': scheduled_days
            }

        except Exception as e:
            print(f"❌ Error actualizando grupo: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    def remove_job(self, job_id, save_to_disk=True):
        if job_id in self.scheduled_jobs:
            try:
                self.scheduler.remove_job(job_id)
                del self.scheduled_jobs[job_id]
                if save_to_disk:
                    self._save_schedules()  # 🔧 Guardar al borrar
                return True
            except:
                return False
        return False

    def remove_group(self, group_key):
        removed = []
        for job_id, info in list(self.scheduled_jobs.items()):
            if info.get('group_key') == group_key:
                # Pasamos save_to_disk=False para no guardar el archivo en cada iteración del bucle
                if self.remove_job(job_id, save_to_disk=False):
                    removed.append(job_id)

        if removed:
            self._save_schedules()  # 🔧 Guardar una sola vez al terminar de borrar el grupo

        return len(removed)

    def get_scheduled_jobs(self):
        groups = {}
        for job_id, info in self.scheduled_jobs.items():
            group_key = info.get('group_key', job_id)
            if group_key not in groups:
                programs = {p['id']: p['name'] for p in self.youtube.get_all_programs()}
                groups[group_key] = {
                    'id': group_key,
                    'title': info['title'],
                    'program_id': info.get('program_id', ''),
                    'program_name': programs.get(info.get('program_id', ''), 'Sin programa'),
                    'days': [],
                    'start_time': None,
                    'end_time': None,
                    'day_count': 0,
                    'next_run': None,
                    'thumbnail_url': info.get('thumbnail_url'),  # 🔧 AGREGAR
                    'post_stream_action': info.get('post_stream_action', 'none')
                }

            day_name = self._get_day_name(info.get('day', 0))
            time_str = f"{int(info.get('hour', 0)):02d}:{int(info.get('minute', 0)):02d}"

            if info.get('type') == 'start':
                groups[group_key]['start_time'] = time_str
                if day_name not in groups[group_key]['days']:
                    groups[group_key]['days'].append(day_name)
                groups[group_key]['next_run'] = info.get('next_run')
            else:
                groups[group_key]['end_time'] = time_str

            groups[group_key]['day_count'] = len(groups[group_key]['days'])

        result = list(groups.values())
        result.sort(key=lambda x: x['title'])
        return result

    def _get_day_name(self, day_number):
        days = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        return days[day_number] if 0 <= day_number < 7 else 'Desconocido'

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()
            print("⏰ Scheduler iniciado")

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
