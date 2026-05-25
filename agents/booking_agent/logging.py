import logging
import sys

def setup_logger(name: str = "booking_agent") -> logging.Logger:
    """Configures and returns a logger with custom format for the booking agent."""
    logger = logging.getLogger(name)
    
    # If logger already has handlers, do not add duplicates
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.INFO)
    
    # Create console handler and set level to info
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )
    handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(handler)
    
    return logger

# Initialize logger
logger = setup_logger()
