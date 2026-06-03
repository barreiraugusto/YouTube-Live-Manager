from flask import Flask, render_template, request, jsonify, flash
from youtube_api import YouTubeLiveManager
from scheduler import LiveScheduler
from datetime import datetime
import warnings
import logging
import os

warnings.filterwarnings('ignore', category=FutureWarning)

# Configuración de logging estructurado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# 🔒 CORRECCIÓN: Usar variable de entorno para secret_key
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24).hex())

youtube = YouTubeLiveManager()
scheduler = LiveScheduler(youtube)

DAYS = {
    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
    'friday': 4, 'saturday': 5, 'sunday': 6
}

DAY_NAMES = {
    'monday': 'Lunes', 'tuesday': 'Martes', 'wednesday': 'Miércoles',
    'thursday': 'Jueves', 'friday': 'Viernes', 'saturday': 'Sábado', 'sunday': 'Domingo'
}

cache_broadcasts = {'data': [], 'timestamp': None, 'ttl': 300}
cache_playlists = {'data': [], 'timestamp': None, 'ttl': 300}


def get_cached_or_fetch(cache_dict, fetch_function, force_refresh=False):
    ahora = datetime.now()
    if (force_refresh or cache_dict['timestamp'] is None or
            (ahora - cache_dict['timestamp']).seconds > cache_dict['ttl']):
        try:
            cache_dict['data'] = fetch_function()
            cache_dict['timestamp'] = ahora
            logger.info("Cache actualizado correctamente")
        except Exception as e:
            logger.error(f"Error al obtener datos: {e}", exc_info=True)
            if not cache_dict['data']:
                cache_dict['data'] = []
    return cache_dict['data']


@app.route('/')
def dashboard():
    def fetch_broadcasts():
        return youtube.get_my_live_broadcasts()

    live_broadcasts = get_cached_or_fetch(cache_broadcasts, fetch_broadcasts)

    def fetch_playlists():
        return youtube.list_playlists()

    playlists = get_cached_or_fetch(cache_playlists, fetch_playlists)

    scheduled = scheduler.get_scheduled_jobs()
    active_streams = scheduler.get_active_streams()
    programs = youtube.get_all_programs()

    return render_template('dashboard.html',
                           broadcasts=live_broadcasts,
                           scheduled=scheduled,
                           active_streams=active_streams,
                           playlists=playlists,
                           programs=programs,
                           days=DAYS,
                           day_names=DAY_NAMES,
                           now=datetime.now())


# ==================== RUTAS PARA PROGRAMAS ====================

@app.route('/api/programs', methods=['GET'])
def api_get_programs():
    """Obtener lista de programas"""
    return jsonify(youtube.get_all_programs())


@app.route('/api/programs', methods=['POST'])
def api_create_program():
    """Crear un nuevo programa"""
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': 'Datos inválidos'}), 400
    
    program_id = data.get('id', '').strip().lower().replace(' ', '_')
    name = data.get('name', '').strip()
    obs_scene = data.get('obs_scene', name)

    # Validación de inputs
    if not program_id or not name:
        logger.warning("Intento de crear programa sin ID o nombre")
        return jsonify({'success': False, 'error': 'ID y nombre son requeridos'}), 400

    result = youtube.create_program(program_id, name, obs_scene)
    if result.get('success'):
        logger.info(f"Programa creado: {program_id}")
    else:
        logger.error(f"Error al crear programa: {result.get('error')}")
    return jsonify(result)


@app.route('/api/programs/<program_id>', methods=['DELETE'])
def api_delete_program(program_id):
    """Eliminar un programa"""
    result = youtube.delete_program(program_id)
    return jsonify(result)


@app.route('/api/programs/<program_id>', methods=['PUT'])
def api_update_program(program_id):
    """Actualizar un programa"""
    data = request.json
    result = youtube.update_program(program_id, data.get('name'), data.get('obs_scene'))
    return jsonify(result)


# ==================== RUTAS PARA PROGRAMACIONES ====================

@app.route('/api/schedule', methods=['POST'])
def schedule_live():
    data = request.json
    made_for_kids = data.get('made_for_kids', False)
    thumbnail_url = data.get('thumbnail_url')
    delete_after = data.get('delete_after', 'never')
    
    if 'selected_days' not in data or not data['selected_days']:
        return jsonify({'success': False, 'error': 'Selecciona al menos un día'})
    if 'program_id' not in data or not data['program_id']:
        return jsonify({'success': False, 'error': 'Selecciona un programa'})

    base_job_id = f"live_{datetime.now().timestamp()}"
    scheduled_days = []

    for day_key in data['selected_days']:
        if day_key not in DAYS:
            continue
        job_id = f"{base_job_id}_{day_key}"

        scheduler.schedule_live(
            job_id=f"{job_id}_start",
            day_of_week=DAYS[day_key],
            hour=int(data['start_hour']),
            minute=int(data['start_minute']),
            title=data['title'],
            description=data.get('description', ''),
            privacy_status=data.get('privacy', 'unlisted'),
            is_start=True,
            program_id=data['program_id'],
            made_for_kids=made_for_kids,
            thumbnail_url=thumbnail_url,
            delete_after=delete_after
        )

        scheduler.schedule_live(
            job_id=f"{job_id}_end",
            day_of_week=DAYS[day_key],
            hour=int(data['end_hour']),
            minute=int(data['end_minute']),
            title=data['title'],
            description=data.get('description', ''),
            privacy_status=data.get('privacy', 'unlisted'),
            is_start=False,
            program_id=data['program_id'],
            made_for_kids=made_for_kids,
            thumbnail_url=thumbnail_url,
            delete_after=delete_after
        )

        scheduled_days.append(day_key)

    if not scheduler.scheduler.running and scheduled_days:
        scheduler.start()

    if scheduled_days:
        flash(f'✅ Programado para {len(scheduled_days)} día(s)', 'success')
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'No se pudo programar'})


@app.route('/api/unschedule-group', methods=['POST'])
def unschedule_group():
    data = request.json
    if not data or not data.get('group_key'):
        return jsonify({'success': False, 'error': 'group_key requerido'}), 400
    
    removed_count = scheduler.remove_group(data.get('group_key'))
    if removed_count > 0:
        logger.info(f"Se eliminaron {removed_count} programaciones")
        flash(f'✅ Eliminadas {removed_count} programaciones', 'success')
        return jsonify({'success': True, 'removed_count': removed_count})
    return jsonify({'success': False, 'error': 'No encontrado'})


@app.route('/api/update-schedule', methods=['POST'])
def update_schedule():
    """Actualizar programación existente"""
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': 'Datos inválidos'}), 400

    group_key = data.get('group_key')
    title = data.get('title')
    description = data.get('description', '')
    privacy = data.get('privacy', 'unlisted')
    thumbnail_url = data.get('thumbnail_url')
    made_for_kids = data.get('made_for_kids', False)
    delete_after = data.get('delete_after', 'never')
    start_hour = data.get('start_hour')
    start_minute = data.get('start_minute')
    end_hour = data.get('end_hour')
    end_minute = data.get('end_minute')
    selected_days = data.get('selected_days', [])

    # Validación de inputs requeridos
    if not all([group_key, title, start_hour, start_minute, end_hour, end_minute, selected_days]):
        logger.warning("Intento de actualizar programación con datos incompletos")
        return jsonify({'success': False, 'error': 'Faltan datos requeridos'}), 400

    result = scheduler.update_schedule_group(
        group_key=group_key,
        new_title=title,
        new_description=description,
        new_privacy=privacy,
        new_thumbnail_url=thumbnail_url,
        new_made_for_kids=made_for_kids,
        new_delete_after=delete_after,
        new_start_hour=start_hour,
        new_start_minute=start_minute,
        new_end_hour=end_hour,
        new_end_minute=end_minute,
        new_selected_days=selected_days
    )

    if result.get('success'):
        logger.info(f"Programación actualizada: {result['new_count']} tareas creadas")
        flash(f'✅ Programación actualizada: {result["new_count"]} tareas creadas', 'success')
        return jsonify(result)
    else:
        logger.error(f"Error al actualizar programación: {result.get('error')}")
        return jsonify(result)


@app.route('/api/start-now', methods=['POST'])
def start_live_now():
    data = request.json
    if not data or not data.get('title'):
        return jsonify({'success': False, 'error': 'Título requerido'}), 400
    
    # Si se proporciona group_id, obtener la configuración de la programación
    thumbnail_url = data.get('thumbnail_url')
    delete_after = data.get('delete_after', 'never')
    
    result = youtube.create_scheduled_live(
        title=data['title'],
        description=data.get('description', ''),
        start_time=None,  # No pasar start_time para inmediato
        privacy_status=data.get('privacy', 'unlisted'),
        program_id=data.get('program_id'),
        is_immediate=True,
        made_for_kids=data.get('made_for_kids', False),
        thumbnail_url=thumbnail_url,
        delete_after=delete_after
    )

    if result.get('success'):
        logger.info(f"Iniciando live inmediato: {data['title']}")
        # Configurar OBS
        youtube.set_stream_key(result['stream_key'])
        scene = youtube.get_program(data.get('program_id')) if data.get('program_id') else None
        if scene and scene.get('obs_scene'):
            youtube.change_scene(scene['obs_scene'])

        # Transicionar a testing y luego a live
        try:
            youtube.service.liveBroadcasts().transition(
                part='status',
                id=result['broadcast_id'],
                broadcastStatus='testing'
            ).execute()
            import time
            time.sleep(2)
            youtube.service.liveBroadcasts().transition(
                part='status',
                id=result['broadcast_id'],
                broadcastStatus='live'
            ).execute()
            logger.info("✅ Broadcast en vivo")
        except Exception as e:
            logger.error(f"⚠️ Error en transición: {e}", exc_info=True)

        youtube.start_obs_stream()

        flash(f'✅ Live "{data["title"]}" iniciado', 'success')
        return jsonify({'success': True, 'broadcast_id': result['broadcast_id']})
    logger.error(f"Error al iniciar live: {result.get('error')}")
    return jsonify({'success': False, 'error': result.get('error')})


@app.route('/api/stop-now/<broadcast_id>', methods=['POST'])
def stop_live_now(broadcast_id):
    try:
        youtube.service.liveBroadcasts().transition(
            part='status', id=broadcast_id, broadcastStatus='complete'
        ).execute()
        youtube.stop_obs_stream()
        logger.info(f"Transmisión detenida: {broadcast_id}")
        flash('✅ Transmisión detenida', 'success')
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error al detener transmisión: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/update-broadcast/<broadcast_id>', methods=['PUT'])
def update_broadcast(broadcast_id):
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': 'Datos inválidos'}), 400
    try:
        youtube.update_live_metadata(broadcast_id, data.get('title'), data.get('description'))
        cache_broadcasts['timestamp'] = None
        logger.info(f"Broadcast actualizado: {broadcast_id}")
        flash('✅ Transmisión actualizada', 'success')
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error al actualizar broadcast: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/delete-broadcast/<broadcast_id>', methods=['DELETE'])
def delete_broadcast(broadcast_id):
    if youtube.delete_broadcast(broadcast_id):
        cache_broadcasts['timestamp'] = None
        logger.info(f"Broadcast eliminado: {broadcast_id}")
        flash('✅ Eliminada', 'success')
        return jsonify({'success': True})
    logger.warning(f"No se pudo eliminar broadcast: {broadcast_id}")
    return jsonify({'success': False}), 404


@app.route('/api/refresh', methods=['POST'])
def refresh_cache():
    global cache_broadcasts, cache_playlists
    cache_broadcasts['timestamp'] = None
    cache_playlists['timestamp'] = None
    return jsonify({'success': True})


@app.route('/api/scheduler-status', methods=['GET'])
def scheduler_status():
    """Verificar estado del scheduler"""
    jobs_info = []
    for job_id, info in scheduler.scheduled_jobs.items():
        jobs_info.append({
            'id': job_id,
            'title': info.get('title'),
            'type': info.get('type'),
            'program_id': info.get('program_id'),
            'next_run': info.get('next_run').strftime('%Y-%m-%d %H:%M:%S') if info.get('next_run') else None
        })

    return jsonify({
        'scheduler_running': scheduler.scheduler.running,
        'jobs_count': len(scheduler.scheduled_jobs),
        'active_streams': len(scheduler.active_streams),
        'timezone': str(scheduler.timezone),
        'current_time': datetime.now(scheduler.timezone).strftime('%Y-%m-%d %H:%M:%S'),
        'jobs': jobs_info
    })


if __name__ == '__main__':
    try:
        scheduler.start()
        print("🚀 Servidor iniciado en http://localhost:5000")
        app.run(debug=True, port=5000, use_reloader=False)
    except KeyboardInterrupt:
        scheduler.shutdown()
