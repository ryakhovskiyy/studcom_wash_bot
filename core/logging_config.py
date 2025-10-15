import logging

def setup_logging():
    """Настраивает базовую конфигурацию логирования."""
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logging.getLogger(__name__)