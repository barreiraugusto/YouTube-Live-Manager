from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
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
            is_start = (item['type'] == 'start')

            # Recrear el trigger de APScheduler
            trigger = CronTrigger(
                day_of_week=item['day'],
                hour=item['hour'],
                minute=item['minute'],
                timezone=self.timezone
            )

            next_run = trigger.get_next_fire_time(None, datetime.now(self.timezone))

            # Volver a agregar la tarea al scheduler
            if is_start:
                job = self.scheduler.add_job(
                    func=self._start_live_stream,
                    trigger=trigger,
                    id=job_id,
                    # Le pasamos el broadcast_id que guardamos previamente
                    args=[item['title'], item.get('description', ''), item.get('privacy', 'unlisted'), job_id,
                          item['program_id'], item.get('broadcast_id')],
                    replace_existing=True
                )
            else:
                job = self.scheduler.add_job(
                    func=self._end_live_stream,
                    trigger=trigger,
                    id=job_id,
                    args=[item['program_id']],
                    replace_existing=True
                )

            # Reconstruir el diccionario en memoria
            self.scheduled_jobs[job_id] = {
                'job': job,
                'title': item['title'],
                'description': item.get('description', ''),
                'day': item['day'],
                'hour': item['hour'],
                'minute': item['minute'],
                'privacy': item.get('privacy', 'unlisted'),
                'type': item['type'],
                'program_id': item['program_id'],
                'broadcast_id': item.get('broadcast_id'),
                'group_key': item['group_key'],
                'next_run': next_run
            }
        print(f"✅ Programaciones restauradas correctamente.")

    def _save_schedules(self):
        """Guarda el estado actual de las programaciones en un archivo JSON"""
        # Extraemos solo los datos de texto (ignoramos el objeto 'job' de APScheduler que no se puede guardar)
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
                'group_key': info['group_key']
            })

        try:
            with open(self.schedules_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Error guardando schedules.json: {e}")

    def schedule_live(self, job_id, day_of_week, hour, minute,
                      title, description, privacy_status='unlisted',
                      is_start=True, program_id=None, made_for_kids=False):

        trigger = CronTrigger(
            day_of_week=day_of_week,
            hour=hour,
            minute=minute,
            timezone=self.timezone
        )

        if job_id in self.scheduled_jobs:
            self.remove_job(job_id)

        print(f"\n📝 Programando tarea: {job_id}")
        print(f"   Título: {title}")
        print(f"   Día: {self._get_day_name(day_of_week)} ({day_of_week})")
        print(f"   Hora: {hour:02d}:{minute:02d}")
        print(f"   Tipo: {'INICIO' if is_start else 'FIN'}")
        print(f"   Programa: {program_id}")

        next_run = trigger.get_next_fire_time(None, datetime.now(self.timezone))

        # CREAR EL BROADCAST AHORA cuando se programa (solo para inicio)
        broadcast_id = None
        if is_start and next_run:
            print(f"📡 Creando broadcast programado en YouTube...")
            result = self.youtube.create_scheduled_live(
                title=title,
                description=description,
                start_time=next_run,  # Usar la hora de próxima ejecución
                privacy_status=privacy_status,
                program_id=program_id,
                is_immediate=False,
                made_for_kids=made_for_kids
            )

            if result.get('success'):
                broadcast_id = result['broadcast_id']
                print(f"✅ Broadcast creado: {broadcast_id}")
            else:
                print(f"❌ Error creando broadcast: {result.get('error')}")
                return None

        if is_start:
            job = self.scheduler.add_job(
                func=self._start_live_stream,
                trigger=trigger,
                id=job_id,
                args=[title, description, privacy_status, job_id, program_id, broadcast_id],  # ← AGREGAR broadcast_id
                replace_existing=True
            )
            self.scheduled_jobs[job_id] = {
                'job': job,
                'title': title,
                'description': description,
                'day': day_of_week,
                'hour': hour,
                'minute': minute,
                'privacy': privacy_status,
                'type': 'start',
                'program_id': program_id,
                'broadcast_id': broadcast_id,  # ← GUARDAR broadcast_id
                'group_key': f"{program_id}|{title}",
                'next_run': next_run
            }
        else:
            job = self.scheduler.add_job(
                func=self._end_live_stream,
                trigger=trigger,
                id=job_id,
                args=[program_id],
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
                'next_run': next_run
            }

        print(f"✅ Tarea programada correctamente")
        self._save_schedules()
        print(f"✅ Tarea programada y guardada correctamente")
        return job

    def _start_live_stream(self, title, description, privacy_status, job_id, program_id, broadcast_id):
        """Ejecutar la tarea programada: iniciar el live"""
        try:
            now = datetime.now(self.timezone)
            print(f"\n{'=' * 70}")
            print(f"🔔 ¡INICIANDO LIVE PROGRAMADO!")
            print(f"📅 Hora actual: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"📺 Título: {title}")
            print(f"{'=' * 70}\n")

            if not broadcast_id:
                print("❌ No se proporcionó broadcast_id")
                return None

            print(f"📡 Usando broadcast: {broadcast_id}")

            # Configurar OBS
            program = self.youtube.get_program(program_id)
            stream_key = program.get('stream_key')
            stream_id = program.get('stream_id')  # 🔧 NECESARIO PARA VERIFICAR EL ESTADO

            print("🎬 Configurando OBS...")
            if stream_key and self.youtube.set_stream_key(stream_key):
                print("✅ Stream key configurada")

            if program and program.get('obs_scene'):
                self.youtube.change_scene(program['obs_scene'])

            # 1. INICIAR OBS
            print("🎥 Iniciando transmisión en OBS...")
            if not self.youtube.start_obs_stream():
                print("❌ No se pudo iniciar OBS")
                return None
            print("✅ OBS está transmitiendo")

            # 2. 🔍 ESPERAR A QUE YOUTUBE DETECTE EL STREAM COMO "ACTIVE"
            print("⏳ Esperando a que YouTube detecte la señal de OBS...")
            import time
            stream_is_active = False

            # Intentar durante 30 segundos (15 intentos * 2 segundos)
            for attempt in range(15):
                try:
                    stream_resp = self.youtube.service.liveStreams().list(
                        part='status',
                        id=stream_id
                    ).execute()

                    if stream_resp.get('items'):
                        stream_status = stream_resp['items'][0]['status']['streamStatus']
                        print(f"   🔍 Estado del stream en YouTube: {stream_status} (intento {attempt + 1}/15)")

                        if stream_status == 'active':
                            stream_is_active = True
                            print("✅ ¡YouTube está recibiendo la señal correctamente!")
                            break
                except Exception as e:
                    print(f"   ⚠️ Error consultando stream: {e}")

                time.sleep(2)

            if not stream_is_active:
                print("❌ ERROR: YouTube no detectó el stream como 'active' a tiempo.")
                print("💡 ASEGÚRATE DE TENER LOS KEYFRAMES EN 2s EN OBS (Ajustes > Salida > Streaming).")
                self.youtube.stop_obs_stream()
                return None

            # 3. 🔄 TRANSICIONES DEL BROADCAST (Paso a paso y seguro)
            try:
                # Obtener el estado actual del broadcast
                broadcast_resp = self.youtube.service.liveBroadcasts().list(
                    part='status',
                    id=broadcast_id
                ).execute()

                current_status = broadcast_resp['items'][0]['status']['lifeCycleStatus']
                print(f"📺 Estado actual del broadcast: {current_status}")

                # Si está en 'ready', pasarlo a 'testing'
                if current_status == 'ready':
                    print("🔄 Transicionando a 'testing'...")
                    self.youtube.service.liveBroadcasts().transition(
                        part='status',
                        id=broadcast_id,
                        broadcastStatus='testing'
                    ).execute()
                    print("✅ Broadcast en modo testing")
                    time.sleep(3)  # Esperar a que YouTube procese el cambio
                    current_status = 'testing'

                # Si está en 'testing', pasarlo a 'live'
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
                elif current_status == 'complete':
                    print("⚠️ El broadcast ya había finalizado.")

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

    def _end_live_stream(self, program_id):
        """Finalizar transmisión y cambiar a escena Tanda"""
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

                    # Verificar que pertenece a este programa
                    if stream_info.get('program_id') == program_id:
                        try:
                            print(f"🔄 Finalizando broadcast: {broadcast_id}")
                            self.youtube.service.liveBroadcasts().transition(
                                part='status',
                                id=broadcast_id,
                                broadcastStatus='complete'
                            ).execute()
                            del self.active_streams[broadcast_id]
                            print(f"✅ Transmisión finalizada: {broadcast_id}")
                        except Exception as e:
                            print(f"⚠️ Error finalizando broadcast: {e}")

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
                    'next_run': None
                }

            day_name = self._get_day_name(info.get('day', 0))
            time_str = f"{info.get('hour', 0):02d}:{info.get('minute', 0):02d}"

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
