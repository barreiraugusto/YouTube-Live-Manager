# test_scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import time
import pytz

def test_function():
    print(f"✅ FUNCIÓN EJECUTADA a las {datetime.now()}")

scheduler = BackgroundScheduler()
trigger = CronTrigger(second=30, timezone=pytz.timezone('America/Santiago'))
scheduler.add_job(test_function, trigger=trigger, id='test_job')
scheduler.start()

print("⏰ Scheduler iniciado. Esperando ejecución en el próximo minuto 30...")
print("Presiona Ctrl+C para detener")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    scheduler.shutdown()