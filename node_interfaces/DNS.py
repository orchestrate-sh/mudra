#!/usr/bin/env python

"""DNS Hook Up.

   THIS SCRIPT IS JUST A STUB/EXAMPLE

   Use example:
      python DNS.py start "{\"name\": \"server1.example.com\"}"

   List commands:
      python DNS.py --help
"""
import click
import if_utils
import json
import time

from if_utils import check_name, SIMULATE_PROCESS_SECONDS

SIM_SECONDS = SIMULATE_PROCESS_SECONDS
SCRIPTS_DIRECTORY = if_utils.EXTERNAL_SCRIPTS_DIR + '/DNS'


@click.group()
def cli():
    """Group of commands."""


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def start(ctx, json_string):
    node = json.loads(json_string)
    name = node['name']
    if_utils.execute_bash(SCRIPTS_DIRECTORY +
                          '/start.sh', name, SIM_SECONDS)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def stop(ctx, json_string):
    node = json.loads(json_string)
    name = node['name']
    if_utils.execute_bash(
        SCRIPTS_DIRECTORY + '/stop.sh', name, SIM_SECONDS)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def check(ctx, json_string):
    node = json.loads(json_string)
    name = node['name']
    check_output = if_utils.execute_bash(SCRIPTS_DIRECTORY +
                                         '/check.sh', name, SIM_SECONDS)
    if "FAIL" in check_output:
        raise click.ClickException(check_output)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def preflight(ctx, json_string):
    node = json.loads(json_string)
    name = node['name']
    if_utils.execute_bash(SCRIPTS_DIRECTORY +
                          '/check.sh', name, SIM_SECONDS)


@cli.command()
@click.argument('json_string', callback=check_name)
def migrate(json_string):
    json_obj = json.loads(json_string)
    name = json_obj['name']
    print(f'Migrate {name}...')
    time.sleep(SIM_SECONDS)
    print('Succeeded.')


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def fail(ctx, json_string):
    node = json.loads(json_string)
    name = node['name']
    print(f'Fail migrating DNS {name}...')
    time.sleep(SIM_SECONDS)
    print('Failed.')
    click.exit(1)


if __name__ == '__main__':
    cli()
