#!/usr/bin/env python

"""Database Hook Up.

   Use example:
      python Database.py start "{\"name\": \"planes_db\"}"

   List commands:
      python Database.py --help
"""

import base64
import click
import csv
import concurrent.futures
import json
import kubernetes
import if_utils
import os
import requests
import time
import threading
import yaml
from collections import defaultdict
from dotenv import load_dotenv
from dotenv import dotenv_values
from if_utils import check_name
from jmespath import search as jp


POD_URL = 'http://{host_ip}:8080/tasks/{task_name}/{service_name}'
WAIT_SECS = 10
WAIT_MSG = f'Waiting {WAIT_SECS} seconds until state is completed.'
TMP_MUDRA = '/tmp/mudra'
SCRIPTS_DIRECTORY = if_utils.EXTERNAL_SCRIPTS_DIR + '/Database'
RESULTS_DIRECTORY = 'logs/node_logs/Database/tasks_results'
DRYRUN_OUTFILE_PATH = if_utils.DRYRUN_OUTFILE_PATH
DRUID_SCRIPTS_DIRECTORY = os.path.join('..',
                                       'external_migration_repos',
                                       'druid_repo')


os.makedirs(RESULTS_DIRECTORY, exist_ok=True)


def get_service_name(service_name):
    if service_name.endswith('-db'):
        service_name = service_name[:-3]
    return service_name


@click.group()
def cli():
    """Group of commands."""


def get_task_result(name, action):
    """Retreive previous task results."""
    path = os.path.join(RESULTS_DIRECTORY, f'{name}.json')
    results = dict()
    if os.path.exists(path):
        with open(path, 'r') as j_file:
            results = json.load(j_file)
    return results.get(action)


def save_task_result(name, action, value):
    path = os.path.join(RESULTS_DIRECTORY, f'{name}.json')
    results = dict()
    if os.path.exists(path):
        with open(path, 'r') as j_file:
            results = json.load(j_file)
    results[action] = value
    with open(path, 'w') as j_file:
        json.dump(results, j_file)


def go_for_it(ctx, json_string, action, prev_action=''):
    node_data = json.loads(json_string)
    node_name = node_data['name']
    thread_id = node_data['thread_id']
    log = if_utils.get_logger(node_name, 'Database', node_action=action)
    load_dotenv(f'.meta/{node_name}-thread{thread_id}.env')
    environment = os.getenv('environment')
    if prev_action and (result := get_task_result(node_name, prev_action)) != 'OK':
        log.error(f'Previous action {prev_action} not ok ({result=})')
        ctx.exit(1)
    if environment == 'local':
        log.info(f'{action=}')
        save_task_result(node_name, action, 'OK')
        return ctx.exit(0)
    host_ip = os.getenv('CLOUDSQL_MIGRATION_IP')
    out_dir = os.getenv('CLOUDSQL_OUTPUT_DIR', '/tmp')
    os.makedirs(out_dir, exist_ok=True)
    log.info(f'host_ip:{host_ip} name:{node_name} action:{action}')
    params = dict(host_ip=host_ip,
                  task_name=action,
                  service_name=get_service_name(node_name))
    if os.getenv('DRYRUN'):
        with open(DRYRUN_OUTFILE_PATH, 'a') as report_file:
            report_file.write('Type: cloudsql API\n'
                              f'Name: {node_name}\n'
                              f'Operation: POST {POD_URL.format(**params)}\n')
        return ctx.exit(0)
    response = requests.get(POD_URL.format(**params))
    log.info(f'get:{json.dumps(response.json(), indent=2)}')
    if response.json().get('error') == 'not found':
        response = requests.post(POD_URL.format(**params))
        log.info(response)
        log.info(response.text)
        if 200 <= response.status_code < 300:
            response = requests.get(POD_URL.format(**params))
            log.info(f'get:{json.dumps(response.json(), indent=2)}')
        else:
            try:
                json_obj = response.json()
                log.info(json.dumps(json_obj, indent=2))
            except KeyError:
                print('key error')
            ctx.exit(1)
    state = response.json().get('state')
    while state != 'complete':
        log.info(WAIT_MSG)
        time.sleep(WAIT_SECS)
        response = requests.get(POD_URL.format(**params))
        log.info(f'get:{json.dumps(response.json(), indent=2)}')
        state = response.json().get('state')
    save_task_result(node_name, action,
                     'OK' if response.json().get('ok') else 'FAIL')
    return response, out_dir, log, node_data


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def preflightdryrun(ctx, json_string):
    ctx.forward(preflight)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def preflight(ctx, json_string):
    response, out_dir, log, node_data = go_for_it(
        ctx, json_string, 'preflight')
    node_name = node_data['name']
    out_csv_filename = os.path.join(out_dir, 'db_output.csv')
    j_obj = response.json()
    log.info(f'Output to {out_csv_filename}')
    if not os.path.exists(out_csv_filename):
        with open(out_csv_filename, 'w') as f_out:
            writer = csv.writer(f_out)
            writer.writerow(['service', 'createTime', 'state', 'preflight',
                             'app', 'rdsMaster', 'rdsReplication', 'pass',
                             'team', 'parent', 'messages'])
    teams = ','.join((os.path.basename(os.path.dirname(parent['file']))
                      for parent in node_data['parents'].values()))
    parents = ','.join(list(node_data['parents'].keys()))
    with open(out_csv_filename, 'a') as f_out:
        writer = csv.writer(f_out)
        if not j_obj['value']:
            j_obj['value'] = {}
        writer.writerow([get_service_name(node_name), j_obj['createTime'],
                         j_obj['state'], j_obj['ok'],
                         j_obj['value'].get('app'),
                         j_obj['value'].get('rdsMaster'),
                         j_obj['value'].get('rdsReplication'),
                         j_obj['value'].get('pass'),
                         teams, parents,
                         '\n'.join(('\n'.join(row.split('\n')[-2:])
                                    for row in j_obj['messages'][-2:]))
                         if not j_obj['ok'] else ''])
    if not j_obj['ok']:
        log.error(f'{node_name} preflight complete but not ok.')
        ctx.exit(1)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def cleanupdryrun(ctx, json_string):
    ctx.forward(cleanup)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def cleanup(ctx, json_string):
    response, out_dir, log, node_data = go_for_it(ctx, json_string, 'cleanup')
    node_name = node_data['name']
    if not response.json().get('ok'):
        log.error(f'{node_name} cleanup complete but not ok.')
        ctx.exit(1)


@cli.command()
@click.argument('json_string', callback=check_name)
def get_cleanup(json_string):
    node_name = json.loads(json_string)['name']
    thread_id = json.loads(json_string)['thread_id']
    log = if_utils.get_logger(node_name, 'Database', node_action='get_cleanup')
    load_dotenv(f'.meta/{node_name}-thread{thread_id}.env')
    environment = os.getenv('environment')
    if environment == 'local':
        return
    host_ip = os.getenv('CLOUDSQL_MIGRATION_IP')
    params = dict(host_ip=host_ip,
                  task_name='cleanup',
                  service_name=get_service_name(node_name))
    response = requests.get(POD_URL.format(**params))
    json_obj = response.json()
    log.info(f'Response:\n{json.dumps(json_obj, indent=2)}')


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def swapdryrun(ctx, json_string):
    go_for_it(ctx, json_string, 'swap')


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def swap(ctx, json_string):
    response, out_dir, log, node_data = go_for_it(ctx, json_string, 'swap',
                                                  'preflight')
    node_name = node_data['name']
    if not response.json().get('ok'):
        log.error(f'{node_name} swap complete but not ok.')
        ctx.exit(1)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def check_sync(ctx, json_string):
    node_name = json.loads(json_string)['name']
    thread_id = json.loads(json_string)['thread_id']
    log = if_utils.get_logger(node_name, 'Database', node_action='check_sync')
    load_dotenv(f'.meta/{node_name}-thread{thread_id}.env')
    environment = os.getenv('environment')
    if environment == 'local':
        return
    host_ip = os.getenv('CLOUDSQL_MIGRATION_IP')
    params = dict(host_ip=host_ip,
                  task_name='sync',
                  service_name=get_service_name(node_name))
    response = requests.get(POD_URL.format(**params))
    json_obj = response.json()
    log.info(f'Response:\n{json.dumps(json_obj, indent=2)}')
    if json_obj.get('ok') is not True:
        log.info('Response not ok.')
        ctx.exit(1)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def cutoverdryrun(ctx, json_string):
    go_for_it(ctx, json_string, 'cutover')


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def cutover(ctx, json_string):
    response, out_dir, log, node_data = go_for_it(ctx, json_string, 'cutover',
                                                  'swap')
    node_name = node_data['name']
    if not response.json().get('ok'):
        log.error(f'{node_name} cutover complete but not ok.')
        ctx.exit(1)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def check_cutover(ctx, json_string):
    node_name = json.loads(json_string)['name']
    thread_id = json.loads(json_string)['thread_id']
    log = if_utils.get_logger(node_name, 'Database',
                              node_action='check_cutover')
    load_dotenv(f'.meta/{node_name}-thread{thread_id}.env')
    environment = os.getenv('environment')
    if environment == 'local':
        return
    host_ip = os.getenv('CLOUDSQL_MIGRATION_IP')
    params = dict(host_ip=host_ip,
                  task_name='cutover',
                  service_name=get_service_name(node_name))
    response = requests.get(POD_URL.format(**params))
    json_obj = response.json()
    log.info(f'Response:\n{json.dumps(json_obj, indent=2)}')
    if json_obj.get('ok') is not True:
        log.info('Response not ok.')
        ctx.exit(1)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def get_status(ctx, json_string):
    service_name = json.loads(json_string)['name']
    thread_id = json.loads(json_string)['thread_id']
    log = if_utils.get_logger(service_name, 'Database',
                              node_action='get_status')
    load_dotenv(f'.meta/{service_name}-thread{thread_id}.env')
    environment = os.getenv('environment')
    if environment == 'local':
        return
    host_ip = os.getenv('CLOUDSQL_MIGRATION_IP')
    params = dict(host_ip=host_ip,
                  task_name='cutover',
                  service_name=service_name)
    response = requests.get(POD_URL.format(**params))
    json_obj = response.json()
    log.info(f'Response:\n{json.dumps(json_obj, indent=2)}')


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def unswapdryrun(ctx, json_string):
    ctx.forward(unswap)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def unswap(ctx, json_string):
    response, out_dir, log, node_data = go_for_it(ctx, json_string, 'unswap')
    node_name = node_data['name']
    if not response.json().get('ok'):
        log.error(f'{node_name} unswap complete but not ok.')
        ctx.exit(1)


@cli.command()
@click.argument('host_ip')
def list_tasks(host_ip):
    log = if_utils.get_logger('list_tasks', 'Database')
    log.info(f'host_ip:{host_ip}')
    params = dict(host_ip=host_ip)
    response = requests.get('http://{host_ip}:8080/tasks'.format(**params))
    log.info(f'response:{response}')
    json_obj = response.json()
    log.info(f'Response:\n{json.dumps(json_obj, indent=2)}')


@cli.command()
@click.option('--service-name')
@click.option('--host-ip')
def delete_tasks(host_ip, service_name):
    log = if_utils.get_logger('delete_tasks', 'Database')
    log.info(f'host_ip:{host_ip}')
    for task in ('cutover', 'cleanup', 'sync', 'preflight'):
        params = dict(host_ip=host_ip,
                      task_name=task,
                      service_name=service_name)
        response = requests.delete(POD_URL.format(**params))
        log.info(f'response:{response}')
        json_obj = response.json()
        log.info(f'Response:\n{json.dumps(json_obj, indent=2)}')


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def check(ctx, json_string):
    ctx.forward(check_sync)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def precutoverdryrun(ctx, json_string):
    with open(DRYRUN_OUTFILE_PATH, 'a') as report_file:
        report_file.write('Following will be executed at the end of phase execution:\n')
    go_for_it(ctx, json_string, 'cutover')


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def precutover(ctx, json_string):
    service_name = json.loads(json_string)['name']
    thread_id = json.loads(json_string)['thread_id']
    load_dotenv(f'.meta/{service_name}-thread{thread_id}.env')
    environment = os.getenv('environment')
    if environment == 'local':
        return
    os.makedirs(TMP_MUDRA, exist_ok=True)
    with open(TMP_MUDRA + '/dbs.cutover', 'a') as f:
        f.write(f'{json_string}\n')


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def preswapdryrun(ctx, json_string):
    with open(DRYRUN_OUTFILE_PATH, 'a') as report_file:
        report_file.write('Following will be executed at the end of phase execution:\n')
    go_for_it(ctx, json_string, 'swap')


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def preswap(ctx, json_string):
    service_name = json.loads(json_string)['name']
    thread_id = json.loads(json_string)['thread_id']
    prev_action = 'preflight'
    if get_task_result(service_name, prev_action) != 'OK':
        log = if_utils.get_logger(service_name, 'Database',
                                  node_action='preswap')
        log.error(f'Previous action {prev_action} not ok.')
        ctx.exit(1)
    load_dotenv(f'.meta/{service_name}-thread{thread_id}.env')
    environment = os.getenv('environment')
    if environment == 'local':
        ctx.forward(pretest)
        return
    os.makedirs(TMP_MUDRA, exist_ok=True)
    with open(TMP_MUDRA + '/dbs.swap', 'a') as f:
        f.write(f'{json_string}\n')


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def commitpreswap(ctx, json_string):
    os.makedirs(TMP_MUDRA, exist_ok=True)
    with open(TMP_MUDRA + '/dbs.commit_swap', 'a') as f:
        f.write(f'{json_string}\n')


@cli.command()
@click.argument('json_string', callback=check_name)
def pretest(json_string):
    os.makedirs(TMP_MUDRA, exist_ok=True)
    with open(TMP_MUDRA + '/dbs.test', 'a') as f:
        f.write(f'{json_string}\n')


@cli.command()
@click.argument('json_string', callback=check_name)
def test(json_string):
    node_data = json.loads(json_string)
    node_name = node_data['name']
    thread_id = node_data['thread_id']
    log = if_utils.get_logger(node_name, 'Database', node_action='test')
    load_dotenv(f'.meta/{node_name}-thread{thread_id}.env')
    environment = os.getenv('environment')
    host_ip = os.getenv('CLOUDSQL_MIGRATION_IP')
    out_dir = os.getenv('CLOUDSQL_OUTPUT_DIR', '/tmp')
    os.makedirs(out_dir, exist_ok=True)
    log.info(f'host_ip:{host_ip} env:{environment} action:test')
    time.sleep(15)
    log.info('the end')
    return


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def cutover_dksdryrun(ctx, json_string):
    node = json.loads(json_string)
    thread_id = node['thread_id']
    name = node['name']
    node_env_file = f'{name}-thread{thread_id}'
    bash = (
        f'{SCRIPTS_DIRECTORY}/data-key-service-migration-cutover.sh',
        name,
        '1',
        node_env_file,
        '-c',
    )
    bash = ' '.join(bash)
    with open(DRYRUN_OUTFILE_PATH, 'a') as report_file:
        report_file.write('Type: cloudsql API\n'
                          f'Name: {name}\n'
                          f'Operation: {bash}\n')


class Scale:
    """Scaledown services."""

    def __init__(self, context, log):
        self.time_start = time.time()
        self.replica_count = dict()
        self.context = context
        self.log = log
        kubernetes.config.load_config(context=context)
        self.api = kubernetes.client.AppsV1Api()
        self._lock = threading.Lock()
        self.service_type = dict(StatefulSet=0, Deployment=1)

    def get_replica_count(self, namespace, node_name):
        with self._lock:
            if (namespace not in self.replica_count) or (
                    self.time_start + 5 < time.time()):
                self.log.info(f'Get replicas {namespace=}')
                self.time_start = time.time()
                try:
                    sts = self.api.list_namespaced_stateful_set(namespace)
                except kubernetes.client.exceptions.ApiException as err:
                    self.log.error(str(err))
                    raise
                try:
                    dep = self.api.list_namespaced_deployment(namespace)
                except kubernetes.client.exceptions.ApiException as err:
                    self.log.error(str(err))
                    raise
                self.replica_count[namespace] = (sts, dep)
            result = [(item.status.replicas, item.spec.replicas)
                      for ctrl in self.replica_count[namespace]
                      for item in ctrl.items
                      if item.metadata.name == node_name]
            return result[0]

    def scale_down(self, node_path):
        with open(node_path, 'r') as node_file:
            node = yaml.load(node_file.read(),
                             Loader=yaml.SafeLoader)
        if node['type'] != 'App':
            return
        namespace = node['meta']['K8S_TARGET_NAMESPACE']
        status_replicas = 1
        spec_replicas = 1
        while 0 < status_replicas + spec_replicas:
            status_replicas, spec_replicas = self.get_replica_count(
                namespace, node['name'])
            status_replicas = status_replicas or 0
            spec_replicas = spec_replicas or 0
            self.log.info(f'{node["name"]=} {status_replicas=} '
                          f'{spec_replicas=}')
            if 0 < spec_replicas:
                self.log.info(f'Scaling down {node["name"]=}')
                if self.service_type.get(
                        node['meta'].get('SERVICE_TYPE')) == 0:
                    patch_function = (
                        self.api.patch_namespaced_stateful_set_scale)
                else:
                    patch_function = (
                        self.api.patch_namespaced_deployment_scale)
                patch_function(
                    node['name'], namespace,
                    {'spec': {'replicas': 0}})
            if 0 < status_replicas:
                time.sleep(5)


def scale_down_parents(context, log, parents):
    scale_obj = Scale(context, log)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        tasks = {executor.submit(scale_obj.scale_down, node['file']):
                 node_name for node_name, node in parents.items()}
        for future in concurrent.futures.as_completed(tasks):
            node_name = tasks[future]
            try:
                future.result()
            except requests.exceptions.ConnectionError:
                log.error(f'{node_name=}')
                raise


@click.group()
def database():
    """Database interface subcommands."""


@database.command()
@click.option('--phase', required=True, type=int, help='phase to execute')
@click.pass_context
def status(ctx, phase):
    """List tasks for db with actions in phase."""
    query = ctx.obj['QUERYNODES']
    envvars = ctx.obj['ENVVARS']
    log = if_utils.get_logger(service_name='subcommand',
                              node_type='Database')
    fields = 'service,dms,secret,tasks'
    host_ip = envvars.get('CLOUDSQL_MIGRATION_IP')
    out_dir = envvars.get('CLOUDSQL_OUTPUT_DIR', '/tmp')
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, 'db_status.csv')
    log.info('Output file %s', csv_path)
    jp_query = (f'[?type==`Database` '
                f'&& actions.*.phases[?contains(@,`{phase}`)]].name')
    with open(csv_path, 'w') as csv_file:
        err_msg = 'Connection Error'
        writer = csv.writer(csv_file)
        writer.writerow(fields.split(','))
        db_names = jp(jp_query, query.nodes)
        log.info(f'{len(db_names)=}')
        with concurrent.futures.ThreadPoolExecutor() as executor:
            responses_to_dbname = {executor.submit(
                requests.get,
                f'http://{host_ip}:8080/status/{get_service_name(db_name)}'):
                db_name for db_name in db_names}
            for future in concurrent.futures.as_completed(responses_to_dbname):
                db_name = responses_to_dbname[future]
                log.info('request: %s', db_name)
                db = get_service_name(db_name)
                try:
                    response = future.result()
                    row = response.json()
                except requests.exceptions.ConnectionError:
                    row = dict(service=db, state=dict(dms=err_msg))
                row = jp("""[service, state.dms, state.secret,
                             state.tasks[].id, state.tasks[].state,
                             state.tasks[].not_null(ok, ``)
                            ]""", row)
                if row[1] != err_msg:
                    tasks = zip(*row[3:6])
                    row[3:] = [(
                        f'{name.split("/")[0]}:{state} '
                        f'{ok if ok == "" else ("OK" if ok else "FAIL")}')
                        for name, state, ok in tasks]
                writer.writerow(row)


@database.command()
@click.pass_context
def action_table(ctx):
    """List all db x phases actions."""
    query = ctx.obj['QUERYNODES']
    envvars = ctx.obj['ENVVARS']
    log = if_utils.get_logger(service_name='subcommand',
                              node_type='Database')
    action_names = query.get_dbs_actions()
    transl = (('precutover', 'cutover(eof)'),
              ('preswap', 'swap(eof)'))
    rows = defaultdict(list)
    all_dbs = set()
    for phase in range(10):
        for a_name in action_names:
            dbs = query.get_dbs(phase, a_name)
            for db in dbs:
                rows[(db, phase)].append(a_name)
                all_dbs.add(db)
    for actions in rows.values():
        for i, act in enumerate(actions):
            for old, new in transl:
                actions[i] = new if act == old else actions[i]
    out_dir = envvars.get('CLOUDSQL_OUTPUT_DIR', '/tmp')
    out_path = os.path.join(out_dir, 'db_actions.csv')
    log.info('Output: %s', out_path)
    with open(out_path, 'w') as file_out:
        writer = csv.writer(file_out)
        writer.writerow(
            'dbs,phase 1,phase 2,phase 3,phase 4,phase 5,phase 6'.split(','))
        for db in all_dbs:
            for col in range(10):
                if col == 0:
                    row = [db]
                else:
                    row.append(','.join(rows[db, col]))
            writer.writerow(row)


@database.command()
@click.pass_context
def config_meta(ctx):
    """Update CLOUDSQL_MIGRATION_IP in <env>.meta file."""
    log = if_utils.get_logger(service_name='subcommand',
                              node_type='Database')
    from kubernetes import config, client
    import re
    context = ctx.obj['ENVVARS']['K8S_TARGET_CONTEXT']
    log.info('context:%s', context)
    config.load_config(context=context)
    api_instance = client.CoreV1Api()
    api_response = api_instance.list_namespaced_pod(namespace='tmc-iam')
    pod_name = [i.metadata.name
                for i in api_response.items
                if i.metadata.name.startswith('cloudsql-migration')]
    pod_name = pod_name[0]
    log.info('pod_name:%s', pod_name)
    api_response = api_instance.read_namespaced_pod(
        name=pod_name, namespace='tmc-iam')
    pod_ip = api_response.status.pod_ip
    log.info('pod_ip:%s', pod_ip)
    env = ctx.obj['ENVIRONMENT']
    meta_path = os.path.join(ctx.obj['DATAFILES'], 'environments')
    with open(os.path.join(meta_path, env + '.meta'), 'r') as in_conf:
        with open(os.path.join(meta_path, env + '.meta.new'), 'w') as out_conf:
            out_conf.writelines((re.sub(r'CLOUDSQL_MIGRATION_IP=.*',
                                        f'CLOUDSQL_MIGRATION_IP={pod_ip}',
                                        line) for line in in_conf))
    os.rename(os.path.join(meta_path, env + '.meta.new'),
              os.path.join(meta_path, env + '.meta'))
    log.info('%s updated.', os.path.join(meta_path, env + '.meta'))


if __name__ == '__main__':
    cli()
