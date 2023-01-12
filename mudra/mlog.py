import logging
import logging.config
import os
import glog as log
import google.cloud.logging
import subprocess
# import shutil
import sys

HANDLERS = dict()

def execute_bash_subprocess(parameters):
    try:
        return subprocess.check_output(parameters)
    except Exception as e:
        logging.error(e)
        logging.error('Error getting project name')


class Mlog:

    def __init__(self):
        logprojectname = None
        input_sys = sys.argv
        for inputs in input_sys:
            if 'logprojectname=' in inputs:
                logprojectname = inputs[inputs.index('=')+1:]
                break
            elif 'logprojectname' in inputs:
                logprojectname = input_sys[input_sys.index(inputs)+1]
                break
        if logprojectname:
            try:
                project_name = execute_bash_subprocess(['gcloud', 'config', 'list',
                                                        '--format', 'value(core.project)']).decode("utf-8").strip() if logprojectname == 'default' \
                    else logprojectname
                credentials, _ = google.auth.default()
                client = google.cloud.logging.Client(
                    project=project_name, credentials=credentials)
                handler = client.get_default_handler()
                log.logger.addHandler(handler)
                logger = logging.getLogger('cloudLogger')
                formatter = logging.Formatter(
                    '%(asctime)s  %(levelname)s   %(message)s')
                handler.setFormatter(formatter)
                logger.addHandler(handler)
                logger.setLevel(logging.INFO)
            except Exception as e:
                logging.error(f"Error with cloud logging Client: {e}")

        os.makedirs('logs', exist_ok=True)
        self.log = log
        log.setLevel("INFO")
        log.logger.addHandler(logging.FileHandler('logs/mudra.log'))
        log.info("Logging started.")


class ThreadLogFilter(logging.Filter):
    """
    This filter only show log entries for specified thread name
    """

    def __init__(self, thread_name, *args, **kwargs):
        logging.Filter.__init__(self, *args, **kwargs)
        self.thread_name = thread_name

    def filter(self, record):
        return record.threadName == self.thread_name


def start_thread_logging(current_phase, thread_name, thread_log_path, loglevel):
    """
    Add a log handler to separate file for current thread
    """
    log_handler = HANDLERS.get((current_phase, thread_name, loglevel))
    if log_handler:
        return log_handler
    log_file = os.getcwd() + \
        '/{}/ThreadLogging-{}-phase{}.log'.format(
            thread_log_path, thread_name, current_phase)
    log_handler = logging.FileHandler(log_file)
    HANDLERS[(current_phase, thread_name, loglevel)] = log_handler

    # Set logging.LEVEL based on loglevel
    if loglevel == 'DEBUG':
        log_level = logging.DEBUG
    elif loglevel == 'INFO':
        log_level = logging.INFO
    elif loglevel == 'WARNING':
        log_level = logging.WARNING
    elif loglevel == 'ERROR':
        log_level = logging.ERROR
    elif loglevel == 'CRITICAL':
        log_level = logging.CRITICAL
    else:
        log_level = logging.INFO

    log_handler.setLevel(log_level)

    formatter = logging.Formatter(
        "%(asctime)-15s"
        "| %(threadName)-11s"
        "| %(levelname)-5s"
        "| %(message)s")
    log_handler.setFormatter(formatter)
    logger = logging.getLogger()
    logger.addHandler(log_handler)
    return log_handler


def stop_thread_logging(log_handler):
    # Remove thread log handler from root logger
    logging.getLogger().removeHandler(log_handler)
    # Close the thread log handler so that the lock on log file can be released
    log_handler.close()


# def config_root_logger():
#     base_log_folder = os.getcwd() + '/logs/parallel_actions/'
#     if os.path.exists(base_log_folder):
#         shutil.rmtree(base_log_folder)
#     os.makedirs(base_log_folder, exist_ok=True)
#     log_file = base_log_folder + 'ThreadLogging.log'
#     formatter = "%(asctime)-15s" \
#                 "| %(threadName)-11s" \
#                 "| %(levelname)-5s" \
#                 "| %(message)s"

#     logging.config.dictConfig({
#         'version': 1,
#         'formatters': {
#             'root_formatter': {
#                 'format': formatter
#             }
#         },
#         'handlers': {
#             'console': {
#                 'level': 'INFO',
#                 'class': 'logging.StreamHandler',
#                 'formatter': 'root_formatter'
#             },
#             'log_file': {
#                 'class': 'logging.FileHandler',
#                 'level': 'DEBUG',
#                 'filename': log_file,
#                 'formatter': 'root_formatter',
#             }
#         },
#         'loggers': {
#             '': {
#                 'handlers': [
#                     'console',
#                     'log_file',
#                 ],
#                 'level': 'DEBUG',
#                 'propagate': True
#             }
#         }
#     })
