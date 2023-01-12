#!/usr/bin/env python

"""App Hook Up.

   Use example:
      python App.py start "{\"name\": \"App 1\"}"

   List commands:
      python App.py --help
"""
import click
import if_utils
import json
import time
import os
import kubernetes
import base64
from dotenv.main import dotenv_values

from if_utils import check_name, SIMULATE_PROCESS_SECONDS


SIM_SECONDS = SIMULATE_PROCESS_SECONDS
SCRIPTS_DIRECTORY = if_utils.EXTERNAL_SCRIPTS_DIR + '/App'
DRUID_SCRIPTS_DIRECTORY = os.path.join('..',
                                       'external_migration_repos',
                                       'druid_repo')
dryrun = False


def __configure_dryrun(nodejson):
    global dryrun
    dryrun = True
    # Load node
    node = json.loads(nodejson)
    name = node['name']
    thread_id = node['thread_id']
    # Write DRYRUN to metadata
    with open(f'.meta/{name}-thread{thread_id}.env', 'a') as node_env:
        node_env.write('DRYRUN=True\n')


def unset_vars(file_name, var_names):
    with open(file_name, 'a') as node_env:
        for var_name in var_names:
            node_env.write(f'unset {var_name}\n')


@click.group()
def cli():
    """Group of commands."""


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def start(ctx, json_string):
    node = json.loads(json_string)
    name = node['name']
    if_utils.execute_bash(
        f'{SCRIPTS_DIRECTORY}/start.sh',
        name,
        SIM_SECONDS,
        node_type='App',
        service_name=name
    )
    ctx.forward(cutover_k8s)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def startdryrun(ctx, json_string):
    # Enable dryrun
    __configure_dryrun(json_string)
    # Forwards to start
    ctx.forward(start)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def waitforapp(ctx, json_string):
    node = json.loads(json_string)
    thread_id = node['thread_id']
    name = node['name']
    node_env_file = f'{name}-thread{thread_id}'
    if_utils.execute_bash(
        f'{SCRIPTS_DIRECTORY}/waitforapp.sh',
        name,
        SIM_SECONDS,
        node_env_file,
        node_type='App',
        service_name=name
    )


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def waitforappdryrun(ctx, json_string):
    # Enable dryrun
    __configure_dryrun(json_string)
    # Forwards to waitforapp
    ctx.forward(waitforapp)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def check(ctx, json_string):
    node = json.loads(json_string)
    name = node['name']
    check_output = if_utils.execute_bash(
        f'{SCRIPTS_DIRECTORY}/check.sh',
        name,
        SIM_SECONDS,
        node_type='App',
        service_name=name
    )
    if "FAIL" in check_output:
        log = if_utils.get_logger(name, node_type='App', node_action='check')
        msg = 'The check script failed'
        log.error(msg)
        raise click.ClickException(msg)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def checkdryrun(ctx, json_string):
    # Enable dryrun
    __configure_dryrun(json_string)
    # Forwards to check
    ctx.forward(check)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def helloworld(ctx, json_string):
    node = json.loads(json_string)
    name = node['name']
    # Create a file foo.txt with the name of the current node
    if_utils.execute_bash(
        f'{SCRIPTS_DIRECTORY}/helloworld.sh',
        name,
        SIM_SECONDS,
        node_type='App',
        service_name=name
    )


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def helloworlddryrun(ctx, json_string):
    # Enable dryrun
    __configure_dryrun(json_string)
    # Forwards to helloworld
    ctx.forward(helloworld)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def cutover_k8s(ctx, json_string):
    node = json.loads(json_string)
    thread_id = node['thread_id']
    name = node['name']
    node_env_file = f'{name}-thread{thread_id}'
    if_utils.execute_bash(
        f'{SCRIPTS_DIRECTORY}/../Cutover/k8s.sh',
        name,
        SIM_SECONDS,
        node_env_file,
        node_type='App',
        service_name=name,
    )


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def cutover_k8sdryrun(ctx, json_string):
    # Enable dryrun
    __configure_dryrun(json_string)
    # Forwards to cutover_k8s
    ctx.forward(cutover_k8s)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def deletesourcepvcs(ctx, json_string):
    node = json.loads(json_string)
    thread_id = node['thread_id']
    name = node['name']
    node_env_file = f'{name}-thread{thread_id}'
    with open(f'.meta/{name}-thread{thread_id}.env', 'a') as node_env:
        node_env.write('DELETE_SOURCE_PVCS=True\n')
    if_utils.execute_bash(
        f'{SCRIPTS_DIRECTORY}/deletepvcs.sh',
        name,
        SIM_SECONDS,
        node_env_file,
        node_type='App',
        service_name=name,
        timeout=60,
        delayoutput=True
    )
    unset_vars(f'.meta/{name}-thread{thread_id}.env',
               ['DELETE_SOURCE_PVCS'])


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def deletesourcepvcsdryrun(ctx, json_string):
    # Enable dryrun
    __configure_dryrun(json_string)
    # Forwards to deletesourcepvcs
    ctx.forward(deletesourcepvcs)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def deletetargetpvcs(ctx, json_string):
    node = json.loads(json_string)
    thread_id = node['thread_id']
    name = node['name']
    node_env_file = f'{name}-thread{thread_id}'
    with open(f'.meta/{name}-thread{thread_id}.env', 'a') as node_env:
        node_env.write('DELETE_TARGET_PVCS=True\n')
    if_utils.execute_bash(
        f'{SCRIPTS_DIRECTORY}/deletepvcs.sh',
        name,
        SIM_SECONDS,
        node_env_file,
        node_type='App',
        service_name=name
    )
    unset_vars(f'.meta/{name}-thread{thread_id}.env',
               ['DELETE_TARGET_PVCS'])


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def deletetargetpvcsdryrun(ctx, json_string):
    # Enable dryrun
    __configure_dryrun(json_string)
    # Forwards to deletetargetpvcs
    ctx.forward(deletetargetpvcs)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def preflight(ctx, json_string):
    node = json.loads(json_string)
    name = node['name']
    thread_id = node['thread_id']
    log = if_utils.get_logger(name, node_type='App', node_action='preflight')
    log.info("preflight")
    with open(f'.meta/{name}-thread{thread_id}.env', 'a') as node_env:
        node_env.write('PREFLIGHT=True\n')
    ctx.forward(cutover_k8s)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def preflightdryrun(ctx, json_string):
    # Enable dryrun
    __configure_dryrun(json_string)
    # Forwards to preflight
    ctx.forward(preflight)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def scaletarget(ctx, json_string):
    node = json.loads(json_string)
    name = node['name']
    thread_id = node['thread_id']
    log = if_utils.get_logger(name, node_type='App', node_action='scaletarget')
    log.info("scaletarget")
    with open(f'.meta/{name}-thread{thread_id}.env', 'a') as node_env:
        node_env.write('K8S_TARGET_ONLY=True\n')
    ctx.forward(cutover_k8s)
    unset_vars(f'.meta/{name}-thread{thread_id}.env',
               ['K8S_TARGET_ONLY'])


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def scaletargetdryrun(ctx, json_string):
    # Enable dryrun
    __configure_dryrun(json_string)
    # Forwards to scaletarget
    ctx.forward(scaletarget)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def scaletargetdown(ctx, json_string):
    node = json.loads(json_string)
    name = node['name']
    thread_id = node['thread_id']
    log = if_utils.get_logger(name, node_type='App',
                              node_action='scaletargetdown')
    log.info("scaletargetdown")
    with open(f'.meta/{name}-thread{thread_id}.env', 'a') as node_env:
        node_env.write('K8S_TARGET_ONLY=True\nK8S_MAX_INSTANCES=0\n')
    ctx.forward(cutover_k8s)
    unset_vars(f'.meta/{name}-thread{thread_id}.env',
               ['K8S_TARGET_ONLY', 'K8S_MAX_INSTANCES'])


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def scaletargetdowndryrun(ctx, json_string):
    # Enable dryrun
    __configure_dryrun(json_string)
    # Forwards to scaletargetdown
    ctx.forward(scaletargetdown)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def scalesource(ctx, json_string):
    node = json.loads(json_string)
    name = node['name']
    thread_id = node['thread_id']
    log = if_utils.get_logger(name, node_type='App', node_action='scalesource')
    log.info("scalesource")
    with open(f'.meta/{name}-thread{thread_id}.env', 'a') as node_env:
        node_env.write('K8S_SOURCE_ONLY=True\n')
    ctx.forward(cutover_k8s)
    unset_vars(f'.meta/{name}-thread{thread_id}.env',
               ['K8S_SOURCE_ONLY'])


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def scalesourcedryrun(ctx, json_string):
    # Enable dryrun
    __configure_dryrun(json_string)
    # Forwards to scalesource
    ctx.forward(scalesource)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def scalesourcedown(ctx, json_string):
    node = json.loads(json_string)
    name = node['name']
    thread_id = node['thread_id']
    log = if_utils.get_logger(name, node_type='App',
                              node_action='scalesourcedown')
    log.info("scalesourcedown")
    with open(f'.meta/{name}-thread{thread_id}.env', 'a') as node_env:
        node_env.write('K8S_SOURCE_ONLY=True\nK8S_MAX_INSTANCES=0\n')
    ctx.forward(cutover_k8s)
    unset_vars(f'.meta/{name}-thread{thread_id}.env',
               ['K8S_SOURCE_ONLY', 'K8S_MAX_INSTANCES'])


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def scalesourcedowndryrun(ctx, json_string):
    # Enable dryrun
    __configure_dryrun(json_string)
    # Forwards to scalesourcedown
    ctx.forward(scalesourcedown)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def rollbacksource(ctx, json_string):
    node = json.loads(json_string)
    name = node['name']
    thread_id = node['thread_id']
    log = if_utils.get_logger(name, node_type='App',
                              node_action='rollbacksource')
    log.info("rollbacksource")
    with open(f'.meta/{name}-thread{thread_id}.env', 'a') as node_env:
        node_env.write('K8S_SOURCE_ONLY=True\nROLLBACK_K8S=True\n')
    ctx.forward(cutover_k8s)
    unset_vars(f'.meta/{name}-thread{thread_id}.env',
               ['K8S_SOURCE_ONLY', 'ROLLBACK_K8S'])


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def rollbacksourcedryrun(ctx, json_string):
    # Enable dryrun
    __configure_dryrun(json_string)
    # Forwards to rollbacksource
    ctx.forward(rollbacksource)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def rollbacktarget(ctx, json_string):
    node = json.loads(json_string)
    name = node['name']
    thread_id = node['thread_id']
    log = if_utils.get_logger(name, node_type='App',
                              node_action='rollbacktarget')
    log.info("rollbacktarget")
    with open(f'.meta/{name}-thread{thread_id}.env', 'a') as node_env:
        node_env.write('K8S_TARGET_ONLY=True\nROLLBACK_K8S=True\n')
    ctx.forward(cutover_k8s)
    unset_vars(f'.meta/{name}-thread{thread_id}.env',
               ['K8S_TARGET_ONLY', 'ROLLBACK_K8S'])


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def rollbacktargetdryrun(ctx, json_string):
    # Enable dryrun
    __configure_dryrun(json_string)
    # Forwards to rollbacktarget
    ctx.forward(rollbacktarget)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def fail(ctx, json_string):
    node = json.loads(json_string)
    name = node['name']
    log = if_utils.get_logger(name, node_type='App', node_action='fail')
    log.info(f'Fail migrating app {name}...')
    time.sleep(SIM_SECONDS)
    log.info('Failed.')
    click.exit(1)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def faildryrun(ctx, json_string):
    # Enable dryrun
    __configure_dryrun(json_string)
    # Forwards to fail
    ctx.forward(fail)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def donothing(ctx, json_string):
    pass


if __name__ == '__main__':
    cli()
