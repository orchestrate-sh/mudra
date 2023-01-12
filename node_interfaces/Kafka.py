#!/usr/bin/env python

"""Kafka Hook Up.

   Use example:
      python Kafka.py start "{\"name\": \"Topic 1\"}"

   List commands:
      python Kafka.py --help
"""
from google.cloud import bigquery
import click
import csv
import if_utils
import io
import json
import os
import prettytable
import shlex
import time
import yaml

from collections import defaultdict
from dataclasses import dataclass, field
from dotenv import load_dotenv, dotenv_values
from if_utils import check_name
from jmespath import search as jp
from prometheus_client import Counter, Gauge, CollectorRegistry, push_to_gateway
from typing import List


FIELDS = ['logging_time', 'topic', 'partition',
          'source_latest_offset', 'target_latest_offset',
          'trailing_by_offsets', 'percent_complete']
FIELDSSHORT = ['logging_time', 'topic', 'part',
               'src_offset', 'tgt_offset',
               'trail', 'complete']


def get_replication_metrics_single_topic2(project, dataset, topic, out_dir):
    """Get the offsets to a flat form."""
    client = bigquery.Client(project=project)
    replication_status_query = """
        SELECT `offset_logging_time` AS `logging_time`, `topic`, `part_num` AS `partition`,
                 IF(`source_datasize` = 0, 0, `source_latest_offset`) AS `source_latest_offset`,
                 IF(`source_datasize` = 0, 0, `target_latest_offset`) AS `target_latest_offset`,
                 IF((`source_datasize` = 0) OR (`target_timestamp` = '1970-01-01 00:00:00 UTC') , 0, `trailing_by_offsets`) AS `trailing_by_offsets`,
                 `percent_complete`
        FROM `{0}.{1}.{2}`
        WHERE `topic` = \"{3}\"
        ORDER BY `percent_complete`;
        """.format(project, dataset, "replication_status_complete_vw", topic)
    datasize_query_job = client.query(replication_status_query)
    datasize_records = [dict(row) for row in datasize_query_job]
    return datasize_records


@click.group()
def cli():
    """Group of commands."""


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def check(ctx, json_string):
    json_obj = json.loads(json_string)
    name = json_obj['name']
    thread_id = json_obj['thread_id']
    ok_trail = int(json_obj['meta'].get('ok_total_trail_offset') or 0)
    log = if_utils.get_logger(
        service_name=name, node_type='Kafka', node_action='check')
    if (not json_obj['parents'] or
       'orphaned-nodes' in json_obj['parents'] and
            1 == len(json_obj['parents'].keys())):
        log.info('Skipping {} from orphaned nodes.'.format(name))
        return
    load_dotenv(f'.meta/{name}-thread{thread_id}.env')
    environment = os.getenv('environment')
    if environment == 'local':
        return
    low_watermark = os.getenv('KAFKA_LOW_WATERMARK') or 100
    low_watermark = int(low_watermark)
    timeout_watermark = int(os.getenv('KAFKA_TIMEOUT') or 60*5)
    high_watermark = int(os.getenv('KAFKA_HIGH_WATERMARK') or 5000)
    project = os.getenv('KAFKA_MM2_PROJECT')
    dataset = os.getenv('KAFKA_MM2_DATASET')
    out_dir = os.getenv('KAFKA_NODE_OUTPUT_DIR') or '/tmp'
    os.makedirs(out_dir, exist_ok=True)
    time_mark = time.time() + timeout_watermark
    ntry = 0
    while time.time() < time_mark:
        ntry += 1
        log.info(f'Query {name}...')
        metrics = get_replication_metrics_single_topic2(
            project, dataset, name, out_dir)
        pp = prettytable.PrettyTable()
        pp.field_names = FIELDSSHORT
        metrics_has_results = True
        if not metrics:
            metrics_has_results = False
            metrics = [dict(zip(FIELDS,
                                ['Not in bq', name, '', 0, 0, 0, 0]))]
        pp.add_rows([row.values() for row in metrics])
        # HERE TABLE log.info(f'\n{pp}')

        out_path_csv1 = os.path.join(out_dir, 'kafka_output.csv')
        log.info(f'Output added into {out_path_csv1}')
        existed = os.path.exists(out_path_csv1)
        with open(out_path_csv1, 'a') as f_output:
            writer = csv.writer(f_output)
            if not existed:
                writer.writerow(['logging_time', 'topic', 'partition',
                                 'source_latest_offset', 'target_latest_offset',
                                 'trailing_by_offsets', 'percent_complete'])
            for row in metrics:
                writer.writerow(
                    list(row.values()))

        total_trailing = 0
        source_latest_offset = 0
        target_latest_offset = 0
        for row in metrics:
            total_trailing += max(int(row['trailing_by_offsets']), 0)
            source_latest_offset += int(row['source_latest_offset'])
            target_latest_offset += min(int(row['source_latest_offset']),
                                        int(row['target_latest_offset']))
            break  # take min percentaje
        log.info(f'Try:{ntry} Offsets:{name} {100.00 if row["source_latest_offset"] == 0 else round(100 *row["target_latest_offset"] / row["source_latest_offset"], 2) }\n'
                 f'Trailing by offsets: {total_trailing} {low_watermark=} {high_watermark=}\n')
        if ok_trail:
            log.warn(f'{ok_trail=}')
        is_preflight = os.getenv('PREFLIGHT') == 'True'
        log.info(f'Preflight: {is_preflight}')
        err_code = 0
        if not metrics_has_results:
            log.error('Error: No results.')
            err_code = 1
        if total_trailing < ok_trail and err_code == 0:
            return
        if high_watermark < total_trailing:
            log.error('Error: Topic is above high watermark.')
            err_code = 1
        if low_watermark < total_trailing and err_code == 0:
            log.warning(
                'Warning: Topic is above low watermark. Waiting 60 secs.')
        if err_code:
            ctx.exit(err_code)
        if low_watermark < total_trailing:
            time.sleep(60)
        else:
            return
    log.error(f'Timeout.')
    ctx.exit(1)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def preflight(ctx, json_string):
    ctx.forward(check)


@cli.command()
@click.argument('json_string', callback=check_name)
@click.pass_context
def noop(ctx, json_string):
    pass


def load_environment_meta(data_files_directory, environment):
    environment_meta_filepath = os.path.join(
        data_files_directory, 'environments', environment + '.meta')
    return dotenv_values(environment_meta_filepath)


@dataclass
class Csv2_row:
    _in_bq: str = '?'
    _in_aws: str = '?'
    _in_gcp: str = '?'
    _team: List[str] = field(default_factory=list)
    _parent: List[str] = field(default_factory=list)

    @property
    def in_bq(self):
        return self._in_bq

    @in_bq.setter
    def in_bq(self, value):
        self._in_bq = 'Y' if value else 'N'

    @property
    def in_aws(self):
        return self._in_aws

    @in_aws.setter
    def in_aws(self, value):
        self._in_aws = 'Y' if value else 'N'

    @property
    def in_gcp(self):
        return self._in_gcp

    @in_gcp.setter
    def in_gcp(self, value):
        self._in_gcp = 'Y' if value else 'N'

    @property
    def team(self):
        return ','.join(self._team)

    @team.setter
    def team(self, value):
        self._team.append(value)

    @property
    def parent(self):
        return ','.join(self._parent)

    @parent.setter
    def parent(self, value):
        self._parent.append(value)


def gen_csv2_from_command(ctx):
    """Create query results to avoid 15 minutes if executed node by node."""
    meta = ctx.obj['ENVVARS']
    project = meta['KAFKA_MM2_PROJECT']
    dataset = meta['KAFKA_MM2_DATASET']
    output_dir = meta.get('KAFKA_NODE_OUTPUT_DIR') or '/tmp'
    os.makedirs(output_dir, exist_ok=True)
    out_path_csv2 = os.path.join(output_dir, 'kafka_topics.csv')
    query = ctx.obj['QUERYNODES']
    log = if_utils.get_logger(service_name='subcommand',
                              node_type='Kafka')
    log.info('BigQuery kafka...')
    bg_client = bigquery.Client(project=project)
    q = """SELECT A.*
           FROM `{project}.{dataset}.mm2_replicated_topics` AS A
           INNER JOIN
           (SELECT topic, max(logging_time) AS logging_time
            FROM `{project}.{dataset}.mm2_replicated_topics`
            GROUP BY topic) AS B
           ON A.topic=B.topic AND A.logging_time=B.logging_time
        """.format(project=project, dataset=dataset)
    bq_result = bg_client.query(q)
    """{'topic': 'workspace-vss-vss-tbkv-peer-metric-table-root-repartition',
        'source_exists': True, 'target_exists': True, 'is_replicated': True,
        'logging_time': datetime.datetime(2021, 11, 4, 22, 47, 12,
                                          tzinfo=datetime.timezone.utc)}"""
    bq_result = {row.topic: dict(row) for row in bq_result}
    log.info(f'Output kafka topics. {out_path_csv2}')
    nodes = query.get_kafkas()
    rows = defaultdict(Csv2_row)
    for node in nodes:
        for product in node['produces'] or []:
            bq_row = bq_result.get(product, {})
            csv2_row = rows[product]
            csv2_row.in_bq = product in bq_result
            csv2_row.in_aws = bq_row.get('source_exists')
            csv2_row.in_gcp = bq_row.get('target_exists')
            csv2_row.team = os.path.basename(os.path.dirname(node['file']))
            csv2_row.parent = node['name']
        for kafka in node['kafka'] or []:
            bq_row = bq_result.get(kafka, {})
            csv2_row = rows[kafka]
            csv2_row.in_bq = kafka in bq_result
            csv2_row.in_aws = bq_row.get('source_exists')
            csv2_row.in_gcp = bq_row.get('target_exists')
            csv2_row.team = os.path.basename(os.path.dirname(node['file']))
            csv2_row.parent = node['name']
    # print(rows)
    # print([dict(row) for row in bq_result][0])
    # return

    with open(out_path_csv2, 'w') as f_output:
        writer = csv.writer(f_output)
        writer.writerow(['topic', 'in_bq',
                         'in_aws', 'in_gcp', 'team', 'parent'])
        writer.writerows([
            [key, rows[key].in_bq,
             rows[key].in_aws, rows[key].in_gcp, rows[key].team,
             rows[key].parent]
            for key in rows])


@click.group()
def kafka():
    """Kafka subcommands."""


@kafka.command()
@click.pass_context
def generate_topic_list(ctx):
    """Generate kafka_topics.csv list."""
    # generate kafka_topics.csv
    gen_csv2_from_command(ctx)


@kafka.command()
@click.option('--time', '_time', default=60, type=int,
              help='Update interval in seconds.')
@click.pass_context
def publish_topic_stats(ctx, _time):
    meta = ctx.obj['ENVVARS']
    project = meta['KAFKA_MM2_PROJECT']
    dataset = meta['KAFKA_MM2_DATASET']
    query = ctx.obj['QUERYNODES']
    log = if_utils.get_logger(service_name='subcommand',
                              node_type='Kafka')
    log.info('publish-topic-stats...')
    bg_client = bigquery.Client(project=project)
    sql = """
      SELECT `offset_logging_time` AS `logging_time`,
        `topic`, `part_num` AS `partition`,
        IF(`source_datasize` = 0, 0, `source_latest_offset`) AS `source_latest_offset`,
        IF(`source_datasize` = 0, 0, `target_latest_offset`) AS `target_latest_offset`,
        IF(`source_datasize` = 0, 0, `trailing_by_offsets`) AS `trailing_by_offsets`,
        `percent_complete`
        FROM `{0}.{1}.{2}`;""".format(
        project, dataset, 'replication_status_complete_vw')
    registry = CollectorRegistry()
    source_offset = Gauge('orchestra_kafka_source_offset', 'source offset',
                          ['topic', 'part_num'], registry=registry)
    target_offset = Gauge('orchestra_kafka_target_offset', 'target offset',
                          ['topic', 'part_num'], registry=registry)
    trailing_offset = Gauge('orchestra_kafka_trailing_offset', 'trailing offset',
                            ['topic', 'part_num'], registry=registry)
    while True:
        mark = time.time() + _time
        bq_result = bg_client.query(sql)
        for row in bq_result:
            source_offset.labels(row.topic, row.partition).set(
                row.source_latest_offset)
            target_offset.labels(row.topic, row.partition).set(
                row.target_latest_offset)
            trailing_offset.labels(row.topic, row.partition).set(
                row.trailing_by_offsets)
        push_to_gateway('localhost:9091', job='orchestration',
                        registry=registry)
        while time.time() < mark:
            time.sleep(10)
            print('.', end='')


@kafka.command()
@click.option('--writedown', default=False, is_flag=True,
              help='Update kafka manifests. Default=dryrun')
@click.pass_context
def addcheck(ctx, writedown):
    """Add a check action to kafka manifests.

    Check kafka node if parent has a start action.
    """
    query = ctx.obj['QUERYNODES']
    log = if_utils.get_logger(service_name='addcheck',
                              node_type='Kafka')
    nodes_phase = list()
    log.info('Gettting start phases from parents...')
    no_actions = set()
    for kafka_node in jp('[?type==`Kafka`]', query.nodes):
        phases = list()
        comments = list()
        for parent_name in kafka_node['parents'].keys():
            phase = [fase
                     for fase in jp(f'[?type==`App` && name==`{parent_name}`]'
                                    '.actions.start.phases[]',  # START action
                                    query.nodes)]
            comments.append(f'# App {parent_name} start on phases {phase}')
            if not phase:
                if not parent_name in no_actions:
                    no_actions.add(parent_name)
                    log.info('App:', parent_name, 'no actions found.')
                continue
            phases.extend(phase)
        if not phases:
            if not kafka_node['name'] in no_actions:
                no_actions.add(kafka_node['name'])
                print('Kafka:', kafka_node['name'], 'no parents actions')
            continue
        nodes_phase.append(dict(file_path=kafka_node['file_name'],
                                phase=min(phases),
                                comments=comments))
    log.info('Checking if a kafka manifest has already actions.')
    for xkafka in nodes_phase:
        with open(xkafka['file_path'], 'r') as k_file:
            ykafka = yaml.load(k_file.read(), Loader=yaml.SafeLoader)
            if 'actions' in ykafka:
                msg = f'{xkafka["file_path"]} has already actions.'
                log.error(msg)
                raise Exception(msg)
    if writedown:
        log.info('Update manifests.')
        for xkafka in nodes_phase:
            action = 'actions:\n  check:\n    phases: [{}]\n'.format(
                xkafka['phase'])
            with open(xkafka['file_path'], 'r') as k_file:
                lines = k_file.read()
            with open(xkafka['file_path'], 'w') as k_file:
                k_file.write(lines)
                if comments := xkafka['comments']:
                    comments.append('')
                k_file.write('\n'.join(comments))
                k_file.write(action)


if __name__ == '__main__':
    cli()
