import time
import sys
import logging

timing_log = logging.getLogger(__name__)
timing_log.setLevel(logging.DEBUG)
timing_log.addHandler(logging.StreamHandler())

def time_function(func):
    def wrapper(*args, **kwargs):
        log_levels = {'DEBUG':10, 'INFO':20, 'WARNING': 30, 'ERROR': 40, 'CRITICAL': 50}
        if 'log_level' in kwargs:
            log_level = kwargs.pop("log_level")
        else:
            log_level = "INFO"
        
        if log_level not in log_levels:
            logging.critical(f"Logging level: {log_level} does not exist.")
            sys.exit()
        
        if kwargs.pop("skip_timer", False):
            return func(*args, **kwargs)
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()

        timing_log.log(log_levels[log_level], f"Func: {func.__name__} Elapsed time: {round(end_time - start_time, 4)} seconds")

        return result
    return wrapper