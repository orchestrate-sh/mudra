"""Call subcommands from interfaces."""

import click
import os
from dotenv.main import dotenv_values
from jpfilter import Query
from mudra.manifest import NodeLoader
from node_interfaces.Database import database
from node_interfaces.Kafka import kafka
from typing import Dict


def load_environment_meta(data_files_directory: str, environment: str
                          ) -> Dict[str, str]:
    environment_meta_filepath = os.path.join(data_files_directory,
                                             'environments',
                                             environment) + '.meta'
    return dotenv_values(environment_meta_filepath)


@click.group(invoke_without_command=True)
@click.option('--environment', default='local', help='environment to execute against')
@click.option('--datafiles', default='mock_data_files', help='data files location (relative)')
@click.pass_context
def interface_subcommands(ctx, datafiles, environment):
    if not ctx.invoked_subcommand:
        print('No invoked interface subcommand.')
        return
    ctx.ensure_object(dict)
    nl = NodeLoader()
    nl.load(os.path.join(datafiles, 'nodes'))
    query = Query(nl, environment)
    ctx.obj['QUERYNODES'] = query
    ctx.obj['ENVVARS'] = load_environment_meta(datafiles, environment)
    ctx.obj['ENVIRONMENT'] = environment
    ctx.obj['DATAFILES'] = datafiles


if __name__ == '__main__':
    interface_subcommands.add_command(database)
    interface_subcommands.add_command(kafka)
    interface_subcommands(obj={})
