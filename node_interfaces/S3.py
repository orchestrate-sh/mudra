#!/usr/bin/env python

"""S3 Hook Up.

   Use example:
      python S3.py start "{\"name\": \"planes_db\"}"

   List commands:
      python S3.py --help
"""
import click
import csv
import if_utils
import json
import os
import prettytable
import re

from dotenv import load_dotenv
from if_utils import check_name


SCRIPTS_DIRECTORY = os.path.join('..',
                                 'external_migration_repos',
                                 's3_repo')
SEEK_STATUS_RE = re.compile('STATUS: (?P<status>.*) - '
                            'progress : (?P<progress>.*) - '
                            'pending files : (?P<pending_files>.*) - '
                            'failed : (?P<total_files_failed>.*)')


@click.group()
def cli():
    """Group of commands."""


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def check(ctx, json_string):
    json_obj = json.loads(json_string)
    node_name = json_obj['name']
    thread_id = json_obj['thread_id']
    log = if_utils.get_logger(node_name, 'S3', node_action='check')
    load_dotenv(f'.meta/{node_name}-thread{thread_id}.env')
    environment = os.getenv('environment')
    if environment == 'local':
        return
    csv_file_name = os.getenv('S3_NODE_OUTPUT_DIR', '/tmp')
    os.makedirs(csv_file_name, exist_ok=True)
    csv_file_name = os.path.join(csv_file_name, 's3_output.csv')
    csv_exists = csv_file_name and os.path.exists(csv_file_name)
    env = os.environ.copy()
    env['PIPENV_DOTENV_LOCATION'] = os.path.join(os.getcwd(),
                                                 '.meta',
                                                 node_name + '.env')
    output = if_utils.execute_command('pipenv',
                                      'run', 'python',
                                      'sts.py',
                                      'check_status',
                                      '--bucket', node_name,
                                      cwd=SCRIPTS_DIRECTORY,
                                      env=env,
                                      node_type='S3',
                                      service_name=node_name)
    output.seek(0)
    table = prettytable.PrettyTable()
    table.field_names = ['bucket'] + list(SEEK_STATUS_RE.groupindex)
    status = ''
    result = None
    rows = [[node_name, '-', 'Not found.', '-', '-']]
    messages = []
    for line in output:
        if message_line := line.strip():
            messages.append(message_line)
        if result := SEEK_STATUS_RE.search(line):
            status = result.group('status')
            rows = [[node_name] + list(result.groups())]
            break
    table.add_rows(rows)
    with open(csv_file_name, 'a') as csv_file:
        writer = csv.writer(csv_file)
        if not csv_exists:
            writer.writerow(table.field_names + ['team', 'parent', 'message'])
        rows[0].extend(if_utils.find_team_parents(json_obj))
        if rows[0][2] == 'Not found.':
            rows[0].append('\n'.join(messages[-2:]))
        else:
            rows[0].append('')
        writer.writerows(rows)
    log.info(f'\n{table}')
    if status != 'SUCCESS':
        log.error(f'{node_name} not SUCCESS.')
        ctx.exit(1)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def preflight(ctx, json_string):
    ctx.forward(check)


if __name__ == '__main__':
    cli()
