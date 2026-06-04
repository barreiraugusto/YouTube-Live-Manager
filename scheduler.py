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
                    # Le pasamos todos los argumentos necesarios incluyendo los nuevos
                    args=[item['title'], item.get('description', ''), item.get('privacy', 'unlisted'), job_id,
                          item['program_id'], item.get('broadcast_id'), item.get('thumbnail_url'),
                          item.get('delete_after', 'never'), item.get('made_for_kids', False),
                          item.get('start_offset_minutes', 0)],
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
                'next_run': next_run,
                'thumbnail_url': item.get('thumbnail_url'),
                'delete_after': item.get('delete_after', 'never'),
                'made_for_kids': item.get('made_for_kids', False),
                'start_offset_minutes': item.get('start_offset_minutes', 0)
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
                'group_key': info['group_key'],
                'thumbnail_url': info.get('thumbnail_url'),
                'delete_after': info.get('delete_after', 'never'),
                'made_for_kids': info.get('made_for_kids', False),
                'start_offset_minutes': info.get('start_offset_minutes', 0)
            })

        try:
            with open(self.schedules_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Error guardando schedules.json: {e}")

    def schedule_live(self, job_id, day_of_week, hour, minute,
                      title, description, privacy_status='unlisted',
                      is_start=True, program_id=None, made_for_kids=False,
                      thumbnail_url=None, delete_after='never', start_offset_minutes=0,
                      existing_broadcast_id=None):

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
        print(f"   Thumbnail: {thumbnail_url or 'No especificada'}")
        print(f"   Eliminar después: {delete_after}")
        print(f"   Anticipar inicio: {start_offset_minutes} minutos")
        if existing_broadcast_id:
            print(f"   🔄 Reutilizando broadcast existente: {existing_broadcast_id}")

        next_run = trigger.get_next_fire_time(None, datetime.now(self.timezone))

        # NO CREAR EL BROADCAST AHORA - Se creará cuando se ejecute la tarea con el offset aplicado
        broadcast_id = existing_broadcast_id if existing_broadcast_id else None
        
        if is_start and existing_broadcast_id:
            # Si estamos reutilizando un broadcast existente (edición), actualizar metadatos
            print(f"♻️ Reutilizando broadcast existente: {existing_broadcast_id}")
            broadcast_id = existing_broadcast_id
            
            # Actualizar miniatura si se proporcionó una nueva
            if thumbnail_url and thumbnail_url.startswith('/uploads/'):
                try:
                    # Extraer el nombre del archivo de la URL
                    filename = thumbnail_url.split('/')[-1]
                    filepath = os.path.join(self.youtube.upload_folder, filename) if hasattr(self.youtube, 'upload_folder') else None
                    
                    if filepath and os.path.exists(filepath):
                        # Leer el archivo y convertirlo a base64 para usar el método existente
                        with open(filepath, 'rb') as f:
                            image_data = f.read()
                        
                        # Convertir a base64
                        import base64
                        base64_data = base64.b64encode(image_data).decode('utf-8')
                        thumbnail_data_url = f"data:image/jpeg;base64,{base64_data}"
                        
                        # Usar el método existente para subir la miniatura
                        self.youtube._upload_thumbnail(broadcast_id, thumbnail_data_url)
                        print(f"✅ Miniatura actualizada en broadcast existente")
                    else:
                        print(f"⚠️ Archivo de miniatura no encontrado: {filepath}")
                except Exception as e:
                    print(f"⚠️ Error actualizando miniatura: {e}")
            
            # Actualizar configuración de eliminación
            if delete_after and delete_after != 'never':
                try:
                    self.youtube._schedule_video_deletion(broadcast_id, delete_after)
                    print(f"✅ Eliminación programada actualizada")
                except Exception as e:
                    print(f"⚠️ Error programando eliminación: {e}")
            
            # Actualizar metadatos (título, descripción)
            if title or description:
                try:
                    self.youtube.update_live_metadata(broadcast_id, title, description)
                    print(f"✅ Metadatos actualizados en broadcast existente")
                except Exception as e:
                    print(f"⚠️ Error actualizando metadatos: {e}")
            
            # Actualizar privacidad
            if privacy_status:
                try:
                    self.youtube.service.liveBroadcasts().update(
                        part='status',
                        body={
                            'id': broadcast_id,
                            'status': {'privacyStatus': privacy_status}
                        }
                    ).execute()
                    print(f"✅ Privacidad actualizada en broadcast existente")
                except Exception as e:
                    print(f"⚠️ Error actualizando privacidad: {e}")

        if is_start:
            job = self.scheduler.add_job(
                func=self._start_live_stream,
                trigger=trigger,
                id=job_id,
                args=[title, description, privacy_status, job_id, program_id, broadcast_id, 
                      thumbnail_url, delete_after, made_for_kids, start_offset_minutes],
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
                'broadcast_id': broadcast_id,  # ← GUARDAR broadcast_id (puede ser None si es nuevo)
                'group_key': f"{program_id}|{title}",
                'next_run': next_run,
                'thumbnail_url': thumbnail_url,  # ← GUARDAR thumbnail_url
                'delete_after': delete_after,
                'made_for_kids': made_for_kids,
                'start_offset_minutes': start_offset_minutes  # ← GUARDAR offset
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
                'next_run': next_run,
                'thumbnail_url': thumbnail_url,  # ← GUARDAR thumbnail_url también en end
                'delete_after': delete_after,
                'made_for_kids': made_for_kids,
                'start_offset_minutes': start_offset_minutes
            }

        print(f"✅ Tarea programada correctamente")
        self._save_schedules()
        print(f"✅ Tarea programada y guardada correctamente")
        return job

    def _start_live_stream(self, title, description, privacy_status, job_id, program_id, broadcast_id,
                           thumbnail_url=None, delete_after='never', made_for_kids=False, start_offset_minutes=0):
        """Ejecutar la tarea programada: iniciar el live"""
        try:
            now = datetime.now(self.timezone)
            print(f"\n{'=' * 70}")
            print(f"🔔 ¡INICIANDO LIVE PROGRAMADO!")
            print(f"📅 Hora actual: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"📺 Título: {title}")
            print(f"{'=' * 70}\n")

            # Si no hay broadcast_id, crear uno nuevo AHORA (en el momento de ejecución con el offset aplicado)
            if not broadcast_id:
                print("📡 Creando broadcast en YouTube en el momento de inicio...")
                
                # Calcular la hora real de inicio aplicando el offset
                actual_start_time = now
                if start_offset_minutes != 0:
                    actual_start_time = now + timedelta(minutes=start_offset_minutes)
                    print(f"   ⏱️ Hora real de inicio (con offset {start_offset_minutes} min): {actual_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # Obtener información del programa para la miniatura
                program = self.youtube.get_program(program_id)
                
                result = self.youtube.create_scheduled_live(
                    title=title,
                    description=description,
                    start_time=actual_start_time,
                    privacy_status=privacy_status,
                    program_id=program_id,
                    is_immediate=True,  # Inmediato porque estamos en el momento de ejecución
                    made_for_kids=made_for_kids,
                    thumbnail_url=thumbnail_url,
                    delete_after=delete_after
                )
                
                if result.get('success'):
                    broadcast_id = result['broadcast_id']
                    print(f"✅ Broadcast creado: {broadcast_id}")
                    
                    # Actualizar el broadcast_id en memoria y guardar en JSON
                    if job_id in self.scheduled_jobs:
                        self.scheduled_jobs[job_id]['broadcast_id'] = broadcast_id
                        self._save_schedules()
                else:
                    print(f"❌ Error creando broadcast: {result.get('error')}")
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
        streams = []
        for stream in self.active_streams.values():
            # Agregar URL de miniatura y stream_url si están disponibles
            broadcast_id = stream.get('broadcast_id', '')
            if broadcast_id:
                stream['thumbnail_url'] = f"https://img.youtube.com/vi/{broadcast_id}/hqdefault.jpg"
                stream['stream_url'] = f"https://www.youtube.com/watch?v={broadcast_id}"
            else:
                stream['thumbnail_url'] = None
                stream['stream_url'] = None
            streams.append(stream)
        return streams

    def update_schedule_group(self, group_key, new_title, new_description, new_privacy,
                              new_start_hour, new_start_minute, new_end_hour, new_end_minute,
                              new_selected_days, new_thumbnail_url=None, new_made_for_kids=False,
                              new_delete_after='never', new_start_offset_minutes=0):
        """Actualizar todas las programaciones de un grupo"""
        try:
            # 1. Obtener información del grupo existente
            existing_jobs = []
            program_id = None
            existing_broadcast_ids = {}  # Diccionario para mapear día -> broadcast_id existente

            for job_id, info in list(self.scheduled_jobs.items()):
                if info.get('group_key') == group_key:
                    existing_jobs.append({
                        'job_id': job_id,
                        'info': info
                    })
                    if not program_id:
                        program_id = info.get('program_id')
                    # Recopilar broadcast_id de las tareas de inicio, mapeados por día
                    if info.get('type') == 'start' and info.get('broadcast_id'):
                        day = info.get('day')
                        if day is not None:
                            existing_broadcast_ids[day] = info.get('broadcast_id')

            if not existing_jobs:
                return {'success': False, 'error': 'Grupo no encontrado'}

            # 2. Eliminar todas las tareas existentes del grupo (pero NO eliminar los broadcasts de YouTube)
            removed_count = self.remove_group(group_key)
            print(f"🗑️ Eliminadas {removed_count} tareas antiguas del grupo")

            # 3. Crear nuevas tareas con los nuevos parámetros
            base_job_id = f"live_{datetime.now().timestamp()}"
            scheduled_days = []

            for day_key in new_selected_days:
                if day_key not in DAYS:
                    continue

                job_id = f"{base_job_id}_{day_key}"
                day_num = DAYS[day_key]

                # Verificar si hay un broadcast existente para este día específico
                reused_broadcast_id = existing_broadcast_ids.get(day_num)

                # Si tenemos un broadcast existente para este día, actualizar sus metadatos en YouTube
                if reused_broadcast_id and (new_title or new_description or new_privacy):
                    print(f"📝 Actualizando metadatos del broadcast existente para {day_key}: {reused_broadcast_id}")
                    try:
                        self.youtube.update_live_metadata(reused_broadcast_id, new_title, new_description)
                        # Actualizar privacidad si es necesario
                        if new_privacy:
                            self.youtube.service.liveBroadcasts().update(
                                part='status',
                                body={
                                    'id': reused_broadcast_id,
                                    'status': {'privacyStatus': new_privacy}
                                }
                            ).execute()
                        print(f"✅ Metadatos actualizados correctamente para {day_key}")
                    except Exception as e:
                        print(f"⚠️ Error actualizando metadatos para {day_key}: {e}")

                # Programar inicio - REUTILIZAR el broadcast_id existente si corresponde a este día
                self.schedule_live(
                    job_id=f"{job_id}_start",
                    day_of_week=DAYS[day_key],
                    hour=int(new_start_hour),
                    minute=int(new_start_minute),
                    title=new_title,
                    description=new_description,
                    privacy_status=new_privacy,
                    is_start=True,
                    program_id=program_id,
                    made_for_kids=new_made_for_kids,
                    thumbnail_url=new_thumbnail_url,
                    delete_after=new_delete_after,
                    start_offset_minutes=new_start_offset_minutes,
                    existing_broadcast_id=reused_broadcast_id  # ← Pasar broadcast existente solo si corresponde a este día
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
                    program_id=program_id,
                    thumbnail_url=new_thumbnail_url,
                    delete_after=new_delete_after,
                    start_offset_minutes=new_start_offset_minutes
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
                    'description': info.get('description', ''),
                    'privacy': info.get('privacy_status', 'unlisted'),
                    'program_id': info.get('program_id', ''),
                    'program_name': programs.get(info.get('program_id', ''), 'Sin programa'),
                    'days': [],
                    'start_time': None,
                    'end_time': None,
                    'day_count': 0,
                    'next_run': None,
                    'thumbnail_url': info.get('thumbnail_url'),  # ← USAR thumbnail_url guardado
                    'broadcast_id': info.get('broadcast_id')  # ← GUARDAR broadcast_id para miniatura real
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

        # Generar URL de miniatura basada en broadcast_id o thumbnail_url guardado
        for group in groups.values():
            # Si hay broadcast_id, usar miniatura real de YouTube
            if group.get('broadcast_id'):
                group['thumbnail_url'] = f"https://img.youtube.com/vi/{group['broadcast_id']}/hqdefault.jpg"
            # Si no hay broadcast_id pero hay thumbnail_url guardado, usar ese
            elif group.get('thumbnail_url'):
                pass  # Ya está asignado
            # Si no hay ninguno, usar placeholder
            else:
                import urllib.parse
                encoded_title = urllib.parse.quote(group['title'])
                group['thumbnail_url'] = f"https://img.youtube.com/vi/search?q={encoded_title}/hqdefault.jpg"

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
