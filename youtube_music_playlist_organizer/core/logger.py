import os
import logging
from datetime import datetime

def setup_logger(playlist_id):
    import re
    # Cria a pasta logs se não existir
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    today = datetime.now().strftime('%d-%m')
    
    # Encontrar o maior número de sequência nos logs existentes
    max_num = 36 # Começa em 36 conforme solicitado pelo usuário
    if os.path.exists('logs'):
        for f in os.listdir('logs'):
            if f.endswith('.log'):
                # Tenta extrair números do final do nome ou do padrão DD-MM-NUM
                # Padrões: 14-05-LM-34.log ou 14-05-35.log
                numbers = re.findall(r'(\d+)', f)
                if numbers:
                    # Pega o último grupo de números que costuma ser a sequência
                    last_num = int(numbers[-1])
                    # Ignora números que pareçam ser o dia ou mês (se houver apenas 2 grupos)
                    if len(numbers) > 2:
                        max_num = max(max_num, last_num)
                    elif len(numbers) == 1: # Caso seja apenas o numero.log
                        max_num = max(max_num, last_num)

    next_num = max_num + 1
    filename = f"{today}-{next_num}.log"
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
