"""Utils for node interfaces modules."""

import glog
import io
import json
import logging
import os
import re
import sh
import sys
import unicodedata
import inspect


SIMULATE_PROCESS_SECONDS = 1
EXTERNAL_SCRIPTS_DIR = 'external_scripts'
LOGS_DIRECTORY = 'logs/node_logs'
PREFLIGHT_REPORT_PATH = 'logs/preflight-report.txt'
DRYRUN_OUTFILE_PATH = 'logs/dryrun.log'


def check_name(ctx, param, value):
    """Parse json and check for the name value."""
    json_object = {}
    try:
        json_object = json.loads(value)
    except Exception as e:
        print(f"Error processing JSON. {e}")
        ctx.exit(1)

    if 'name' in json_object:
        return value
    print("Error: Missing name value in json argument.")
    ctx.exit(1)


def get_log_path(service_name, node_type='', node_action=''):
    log_path = os.path.join(LOGS_DIRECTORY, node_type)
    os.makedirs(log_path, exist_ok=True)
    if node_action:
        log_file_name = slugify(service_name) + f'-{node_action}.log'
    else:
        log_file_name = slugify(service_name) + '.log'
    return os.path.join(log_path, log_file_name)


def slugify(value):
    """
    Normalizes string, converts to lowercase, removes non-alpha characters,
    and converts spaces to underscores.
    """
    value = unicodedata.normalize('NFKD', value)
    value = re.sub(r'[^\w\s-]', '', value).strip().lower()
    value = re.sub(r'[\s_]+', '_', value)
    return value


def get_logger(service_name, node_type='', node_action=''):
    """Get glog logger and add a file handler if there is no one."""
    log = glog.logger
    exists_file_handler_in_logger = any(map(
        lambda handler: isinstance(handler, logging.FileHandler),
        log.handlers
    ))
    if not exists_file_handler_in_logger:
        file_path = get_log_path(service_name, node_type, node_action)
        file_handler = logging.FileHandler(file_path)
        log.addHandler(file_handler)
    return log


def execute_bash(cmd_path, *params, node_type='', service_name='run', timeout=None, delayoutput=None):
    """Execute and log command.
    cmd_path: string full command path.
    params: list of strings.
    node_type: string interface type.
    service_name: string node name.
    """
    # Get name of calling function for 'node_action'
    frame = inspect.stack()[1].function
    log = get_logger(service_name=service_name, node_type=node_type, node_action=frame)
    try:
        bash = sh.bash.bake(cmd_path, params)
        bash = bash(_err_to_out=False, _iter=True, _out_bufsize=1, _timeout=timeout)
        if delayoutput:
            log.info(bash)
        else:
            for line in bash:
                log.info(line)
        return bash
    except (sh.ErrorReturnCode, sh.ErrorReturnCode_2) as error:
        log.error(error.stderr.decode('utf-8'))
        sys.exit(error.exit_code)


def execute_command(cmd_path, *params, cwd=None, env=None, node_type='',
                    service_name='run', output: io.StringIO = None,
                    dont_exit=True):
    """Execute and log command.
    cmd_path: string full command path.
    params: list of strings.
    cwd: optional string for current work directory.
    env: optional dict for environment.
    node_type: string node type.
    service_name: string service name.
    """
    err_output = io.StringIO()
    log = get_logger(service_name=service_name, node_type=node_type)
    try:
        cmd = sh.Command(cmd_path)
        cmd = cmd.bake(params, _iter=True, _out_bufsize=1,
                       _cwd=cwd, _env=env, _err=err_output)
        for line in cmd():
            log.info(line)
            if output:
                output.write(line)
    except (sh.ErrorReturnCode, sh.ErrorReturnCode_2) as error:
        log.error(error.stderr.decode('utf-8'))
        log.error(err_output.getvalue())
        if not dont_exit:
            sys.exit(error.exit_code)
    return err_output


def find_team_parents(json_obj):
    """Get strings for teams and parents from the node's json."""
    parents = ','.join(json_obj['parents'].keys())
    teams = (os.path.basename(os.path.dirname(parent['file']))
             for parent in json_obj['parents'].values())
    teams = ','.join(teams)
    return parents, teams
