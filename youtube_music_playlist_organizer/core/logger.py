import os
import logging
from datetime import datetime

def setup_logger(playlist_id):
    # Cria a pasta logs se não existir
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Um arquivo de log por execução, nomeado pelo timestamp (sem colisão e
    # ordenável cronologicamente — ideal para execuções periódicas).
    stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    safe_id = str(playlist_id).replace('/', '_') if playlist_id else 'run'
    filename = f"{stamp}-{safe_id}.log"
    log_path = os.path.join('logs', filename)
    
    # Configura o logger
    logger = logging.getLogger('YTOrganizer')
    # Remove handlers antigos
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    logger.setLevel(logging.DEBUG)
    
    # Handler para arquivo com flush imediato
    class FlushHandler(logging.FileHandler):
        def emit(self, record):
            super().emit(record)
            self.flush()

    file_handler = FlushHandler(log_path, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

def get_logger():
    return logging.getLogger('YTOrganizer')
