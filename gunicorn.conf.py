import multiprocessing
import os


bind = os.getenv('BIND', '0.0.0.0:8000')
workers = int(os.getenv('WEB_CONCURRENCY', str(min(multiprocessing.cpu_count() * 2 + 1, 5))))
threads = int(os.getenv('WEB_THREADS', '2'))
worker_class = 'gthread'
timeout = int(os.getenv('WEB_TIMEOUT', '60'))
graceful_timeout = 30
keepalive = 5
max_requests = 1500
max_requests_jitter = 150
accesslog = '-'
errorlog = '-'
capture_output = True

