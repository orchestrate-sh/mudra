import csv
import logging
import sys
import os
import json
import itertools
import time
from pathlib import Path
import concurrent.futures
from mudra import mlog
# from mudra.mlog import config_root_logger, start_thread_logging, stop_thread_logging
from mudra.mlog import start_thread_logging, stop_thread_logging
import threading
import shutil
from pid import PidFile, PidFileError
import subprocess
import signal


import click

import networkx as nx
import matplotlib.pyplot as plt

from dotenv.main import dotenv_values

import sh
from sh import ErrorReturnCode

from mudra import charts
from mudra.manifest import NodeLoader, ProcessLoader
# from mudra.formatters import Click_Formatter
from mudra.mlog import Mlog


class Mudra:
    """Mudra"""
    node_loader = NodeLoader()
    process_loader = ProcessLoader()
    DG = nx.DiGraph()
    nodes = []
    nodes_failed_preflight = []
    skipnodes = []
    processes = []
    loglevel = 'INFO'
    thread_log_path = 'logs/thread_logs'
    node_interfaces = {}
    _data_files_directory = ''
    node_interfaces_directory = 'node_interfaces'
    phase = -1
    phases = 0
    environment = ''
    extravars = ''
    process_single_node = None
    process_multiple_nodes = None
    process_node_filter = None
    process_single_action = None
    preflight = False
    dryrun = False
    chartsonly = False
    drawcharts = False
    force = False
    nodetype = None
    mlog = Mlog()

    def __init__(self):
        """Initialize."""
        # Load node interface script names
        self.load_node_interface_script_names()

    @staticmethod
    def get_base_graph():
        return nx.DiGraph()

    @property
    def data_files_directory(self):
        return self._data_files_directory

    @data_files_directory.setter
    def data_files_directory(self, value):
        self._data_files_directory = value

    def inspect_graph(self):
        """Inspect graph"""
        mlog.log.info("Inspecting graph")
        # Print details to stdout
        mlog.log.info(
            f"Total number of nodes: {self.DG.number_of_nodes()}")
        mlog.log.info(
            f"Total number of edges: {self.DG.number_of_edges()}")

    def signal_handler(self, sig, frame):
        thread_pid = os.getpid()
        subprocess.Popen(
            [f"./killprocesses.sh {'{}'.format(thread_pid)}"], shell=True, executable="/bin/bash").wait()

    def draw_charts(self):
        """Draw charts"""
        mlog.log.info("Drawing charts")
        # Export image
        nx.draw_networkx(self.DG, pos=nx.spring_layout(self.DG))
        plt.savefig("plot.png")
        nodes_selected = {
            k: v for k, v in self.node_loader.nodes.items() if k in self.DG.nodes}
        charts.generate(nodes_selected)

    def load_node_interface_script_names(self):
        """Search node_interfaces/ for a script matching node_type"""
        # List all files in node_interface files
        node_interface_files = os.listdir(self.node_interfaces_directory)
        # Iterate through list of node_interfaces
        for interface_file in node_interface_files:
            # Save filename without extension as key and filename with extension as value
            node_interface_name, node_interface_extension = os.path.splitext(
                interface_file)
            self.node_interfaces[node_interface_name] = node_interface_extension

    def process_node(self, node, cmd, dryrun):
        """Process node"""
        mlog.log.info(f"Executing node: {node.name}")
        # Append `dryrun` to command if dryrun is enabled
        if dryrun:
            cmd = cmd + "dryrun"
        # Check node tracking directories, if node exists then skip node processing for this node (unforced only)
        if os.path.exists(f'logs/executed_nodes/{node.name}-{self.environment}-{self.phase}-{cmd}') and not self.force and not dryrun:
            mlog.log.info(f"Skipping processed node: {node.name}")
            return
        # if os.path.exists(f'logs/failed_preflight/{node.type}_{node.name}'):
        #     mlog.log.info(f"Skipping node because it failed preflight checks: {node.name}")
        #     return
        try:
            # Convert node_data to json for passing to node interface
            node_data = self.prepare_node_data(node).replace('"', '\\"')
            # Execute command against node interface and pass in node data as json
            for line in sh.bash("-c", self.node_interfaces_directory + '/' + node.type + self.node_interfaces[node.type] + ' ' + cmd + ' "' + node_data + '"', _err_to_out=True, _iter=True, _out_bufsize=0):
                print(line, end="")
            # Record node in node tracking directory if not dryrun
            if not dryrun:
                mlog.log.debug(f"Recording node: {node.name}")
                if os.path.exists('logs/executed_nodes'):
                    # Create new file in logs/executed_nodes directory if it doesn't exist
                    open(f'logs/executed_nodes/{node.name}-{self.environment}-{self.phase}-{cmd}', 'a').close()
                else:
                    # Throw exception if node tracking directory does not exist
                    raise Exception(
                        "logs/executed_nodes directory does not exist")
        except ErrorReturnCode as error:
            mlog.log.error("Error:" + error.stderr.decode("utf-8"))
            mlog.log.info("Error:" + error.stdout.decode("utf-8"))
            # If dryrun is enabled, ignore error and continue
            if dryrun:
                mlog.log.info(f"Error: Action failed with dryrun enabled, continuing")
                return
            # If cmd is preflight then add node to self.nodes_failed_preflight and return
            if cmd == 'preflight':
                self.nodes_failed_preflight.append(node)
                # Write node to file
                with open(f'logs/failed_preflight/{node.type}_{node.name}', 'a') as f:
                    f.write(f'{time.strftime("%Y%m%d %H:%M:%S")} {node.name}\n')
                mlog.log.error(f'Error: Node {node.name} failed preflight')
                return
            elif not self.force:
                sys.exit(error.exit_code)

    def execute_process(self, process):
        """Execute process"""
        mlog.log.info(f"Executing process: {process}")
        for process_command in process["actions"]:
            try:
                # Execute command against process
                mlog.log.info(f"Executing command: {process_command}")
                for line in sh.bash("-c", process_command, _err_to_out=True, _iter=True, _out_bufsize=0):
                    print(line, end="")
            except ErrorReturnCode as error:
                mlog.log.error("Error:" + error.stderr.decode("utf-8"))
                mlog.log.info("Error:" + error.stdout.decode("utf-8"))
                sys.exit(error.exit_code)

    def prepare_node_data(self, node):
        """Prepare node data"""
        return json.dumps(vars(node))

    def load_node_meta(self, node):
        """Load node meta"""
        mlog.log.debug(f"Loading node meta: {node.name}")
        # Load node meta
        node_meta_filepath = self.data_files_directory + \
            '/environments/' + self.environment + '/nodes/' + \
            node.file_name.rsplit('.', 1)[0] + '.meta'
        return self.load_dotfile(node_meta_filepath)

    def load_environment_meta(self):
        """Load environment meta"""
        mlog.log.debug(f"Loading environment meta: {self.environment}")
        environment_meta_filepath = self.data_files_directory + \
            '/environments/' + self.environment + '.meta'
        return self.load_dotfile(environment_meta_filepath)

    def load_extravars(self):
        """Load extravars"""
        mlog.log.debug(f"Loading extravars: {self.extravars}")
        # Get extravars string and see if it contains anything
        if self.extravars:
            if "=" not in self.extravars:
                return self.load_dotfile(self.extravars)
            # Parse extravars into dictionary and return it
            extravars_content = dict([x.split('=')
                                     for x in self.extravars.split(' ')])
            mlog.log.debug(f"Extravars content: {extravars_content}")
            return extravars_content
        else:
            return {}

    def load_node_credentials(self, node):
        """Load node credentials"""
        mlog.log.debug(f"Loading node credentials: {node.name}")
        # Load node credentials
        node_creds_filepath = self.data_files_directory + \
            '/environments/' + self.environment + '/nodes/' + \
            node.file_name.rsplit('.', 1)[0] + '.creds'
        return self.load_dotfile(node_creds_filepath)

    def load_environment_credentials(self):
        """Load environment credentials"""
        mlog.log.debug(
            f"Loading environment credentials: {self.environment}")
        environment_creds_filepath = self.data_files_directory + \
            '/environments/' + self.environment + '.creds'
        return self.load_dotfile(environment_creds_filepath)

    def load_dotfile(self, dotfile_path):
        """Load dotfile"""
        mlog.log.debug(f"Loading dotfile: {dotfile_path}")
        if os.path.isfile(dotfile_path):
            dotfile_content = dotenv_values(dotfile_path)
            mlog.log.debug(f"Dotfile content: {dotfile_content}")
            return dotfile_content
        else:
            return {}

    def generate_node_environment(self, node):
        """Generate node environment"""
        mlog.log.debug(f"Generating node environment: {node.name}")
        # Merge node meta data
        if self.load_node_meta(node):
            node.meta = {**node.meta, **self.load_node_meta(node)}
        # mlog.log.debug(f"Node meta: {node.meta}")
        # Load node credentials
        node_credentials = self.load_node_credentials(node)
        # Load environment meta
        environment_meta = self.load_environment_meta()
        # mlog.log.debug(environment_meta)
        # Load extravars
        extravars = self.load_extravars()
        mlog.log.debug(extravars)
        # Load environment credentials
        environment_credentials = self.load_environment_credentials()
        # app.mlog.log.debug(environment_credentials)
        Path(".meta").mkdir(parents=True, exist_ok=True)
        # Generate DOTFILE
        dotfile_content = ""
        # Iterate through node meta
        for k, v in node.meta.items():
            dotfile_content += k + '=' + '"' + str(v) + '"\n'
        # Iterate through node credentials
        for k, v in node_credentials.items():
            dotfile_content += k + '=' + '"' + str(v) + '"\n'
        # Iterate through environment meta
        for k, v in environment_meta.items():
            dotfile_content += k + '=' + '"' + str(v) + '"\n'
        # Iterate through extravars
        for k, v in extravars.items():
            dotfile_content += k + '=' + '"' + str(v) + '"\n'
        # Iterate through environment credentials
        for k, v in environment_credentials.items():
            dotfile_content += k + '=' + '"' + str(v) + '"\n'
        # Add preflight to environment variables
        if self.preflight:
            dotfile_content += 'PREFLIGHT="True"\n'
        # Add dryrun to environment variables
        if self.dryrun:
            dotfile_content += 'DRYRUN="True"\n'
        # Add environment to environment variables
        if self.environment:
            dotfile_content += f'environment="{self.environment}"\n'
        # Create DOTFILE for node (always re-create)
        dotfile = open('.meta/' + node.name +
                       f'-thread{node.thread_id}.env', 'w')
        dotfile.write(dotfile_content)
        dotfile.close()
        return node

    def generate_node_collection(self, graph):
        """Generate node collection"""
        mlog.log.info("Generating node collection")
        # Get nodes with no children.
        nodes_step = set([x for x, y in graph.out_degree() if y == 0])
        all_nodes = nodes_step  # Nodes processed.
        # List of list of nodes to be processed.
        all_nodes_steps = [nodes_step]
        while True:
            # Get parent nodes whose children are already processed.
            # .predecessors=parents .neighbors=children
            nodes_step = set([x for j in nodes_step for x in graph.predecessors(j)
                              if set(graph.neighbors(x)).issubset(all_nodes)])
            if not nodes_step:
                break
            all_nodes = all_nodes.union(nodes_step)
            all_nodes_steps.append(nodes_step)
        mlog.log.debug(all_nodes_steps)
        return all_nodes_steps

    def log_nodes_to_exec(self, all_waves):
        log_path = os.path.join(self.thread_log_path, 'nodes_to_exec.csv')
        exist_flag = os.path.exists(log_path)
        with open(log_path, 'a') as csv_file:
            writer = csv.DictWriter(csv_file,
                                    fieldnames=['timestamp', 'wave', 'type', 'node'])
            if not exist_flag:
                writer.writeheader()
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            for i, wave in enumerate(all_waves):
                for node in sorted(wave):
                    writer.writerow(dict(
                        timestamp=timestamp,
                        wave=i + 1,
                        type=self.node_loader.nodes[node].type,
                        node=node))

    def orchestrate_nodes(self):
        """Orchestrate nodes"""
        mlog.log.info("Orchestrating nodes")
        # Iterate through the graph
        self.nodes = list(
            reversed(list(nx.topological_sort(self.DG))))
        mlog.log.debug(self.nodes)
        # Execute each node interface based on node (type/content)
        # Disable threading logic if maxworkers is set to 1
        if self.maxworkers == 1:
            mlog.log.info("Threading disabled")
            mlog.log.debug("Node order:")
            node_count = 0
            for node in self.nodes:
                node_count += 1
                mlog.log.debug(f"{node_count}. {node}")
            for node in self.nodes:
                # Do orchestration for node
                mlog.log.debug(f"Orchestrating node: {node}")
                self.do_orchestration(node, self.node_loader)
        else:
            mlog.log.info("Threading enabled")
            all_nodes_steps = self.generate_node_collection(self.DG)
            self.log_nodes_to_exec(all_nodes_steps)
            for nodes_name_collection in all_nodes_steps:
                with concurrent.futures.ProcessPoolExecutor(max_workers=self.maxworkers) as executor:
                    list(executor.map(self.do_orchestration, nodes_name_collection,
                                      itertools.repeat(self.node_loader)))
        # Output nodes_failed_preflight list to mlog.log.error
        if self.nodes_failed_preflight:
            mlog.log.error(
                "Nodes failed preflight: {}".format(self.nodes_failed_preflight))

    def do_orchestration(self, node_name, node_loader):
        """Execute node interface"""
        # Start thread logging if multi-threaded
        thread_id = 0
        if self.maxworkers > 1:
            thread_id = threading.get_ident()
        thread_log_handler = start_thread_logging(
            self.phase, thread_id, self.thread_log_path, self.loglevel)
        # Begin orchestration
        mlog.log.debug(f"Evaluating node: {node_name}")
        # Skip node if in skipnodes
        if node_name in self.skipnodes:
            mlog.log.debug(f"Skipping node: {node_name}")
            return
        # Allow processing of single node, if desired
        if self.process_single_node and node_name != self.process_single_node:
            mlog.log.debug(
                f"Skipping node: {node_name} because it is not the desired node")
            return
        elif self.process_multiple_nodes and node_name not in self.process_multiple_nodes:
            mlog.log.debug(
                f"Skipping node: {node_name} because it is not in the desired node list")
            return
        mlog.log.debug(f"Processing node: {node_name}")
        # Get node
        node = node_loader.nodes.get(node_name)
        # Generate node environment
        node.thread_id = thread_id
        node = self.generate_node_environment(node)
        # Output debug information
        mlog.log.debug("Node data: %s" % str(node))
        # If limiting execution by node type, skip nodes that don't match
        if self.nodetype and self.nodetype != node.type:
            mlog.log.debug(
                f"Skipping node: {node_name} because it is not the desired node type")
            return
        mlog.log.debug("Determining node action")
        # If we are doing preflight check, only perform preflight
        if self.preflight:
            action = 'preflight'
            # Execute preflight on node, if not virtual node
            if node.type == 'Virtual':
                mlog.log.info(
                    f"Skipping preflight for virtual node: {node.name}")
                return
            else:
                mlog.log.info(
                    f"Executing preflight for: {node.name}")
            try:
                # Create PID file if start
                with PidFile(f'{node.name}-preflight') as p:
                    mlog.log.debug(p.pidname)
                    self.process_node(node, 'preflight')
            # Node already started/running
            except PidFileError as e:
                mlog.log.info(
                    f"Preflight already running for {node.name}")
            return
        # Allow processing of single action, if desired
        if self.process_single_action:
            action = self.process_single_action
            action_phases = node.actions.get(action, {}).get('phases', [])
            if self.phase not in action_phases and self.phase != -1 and not self.force:
                return
            # Execute node interface based on node type
            try:
                # Create PID file if start
                with PidFile(f'{node.name}-{action}') as p:
                    mlog.log.debug(p.pidname)
                    self.process_node(node, action, self.dryrun)
            # Node already started/running
            except PidFileError as e:
                mlog.log.info(
                    f"{action} already running for {node.name}")
            return
        # Determine this node's actions for this current phase
        for action, phases in node.actions.items():
            mlog.log.debug(action)
            node_phases = []
            for key, value in (
                    itertools.chain.from_iterable(
                        [itertools.product((k, ), v) for k, v in phases.items()])):
                node_phases.append(value)
            # See if this action is in this phase
            if self.phase in node_phases:
                mlog.log.info(f'Sending {action} for phase {self.phase}')
                # Execute node interface based on node type
                try:
                    # Create PID file if start
                    with PidFile(f'{node.name}-{action}') as p:
                        mlog.log.debug(p.pidname)
                        self.process_node(node, action, self.dryrun)
                # Node already started/running
                except PidFileError as e:
                    mlog.log.info(
                        f"{action} already running for {node.name}")
        # Stop thread logging if multi-threaded
        if self.maxworkers > 1:
            stop_thread_logging(thread_log_handler)

    def orchestrate_processes(self):
        """Orchestrate processes"""
        mlog.log.info("Orchestrating processes")
        # Reset processes
        self.processes = []
        self.process_loader.processes = []
        # Load process files
        try:
            mlog.log.info(
                f'Getting processes from {self.data_files_directory + "/processes"}')
            self.process_loader.load(self.data_files_directory + '/processes')
            self.process_loader.load(
                self.data_files_directory + f'/processes/Phase {self.phase}')
        except FileNotFoundError as e:
            mlog.log.info(f'Process directory not found (skipping): {e}')
        # Iterate through processes and execute commands
        self.processes = self.process_loader.processes
        mlog.log.info(f'Processes:{len(self.processes)}')
        if len(self.processes):
            for process in self.processes:
                mlog.log.info
                (process["name"])
                self.execute_process(process)

    def inspect_missing_dependencies(self):
        """Inspect repeated nodes or missed nodes"""
        mlog.log.info("Inspecting missing dependencies")
        return self.node_loader.find_missing_dependencies()

    def inspect_tree(self):
        """Inspect tree"""
        mlog.log.info("Inspecting tree")
        self.node_loader.load(self.data_files_directory + '/nodes',
                              True)
        services = dict([k.split('=') for k in self.args])
        if 'type' in services and 'phase' in services:
            return self.node_loader.get_nodes_by(
                services['type'], phase=services['phase'])
        if 'type' in services and 'services' in services:
            return self.node_loader.inspect_tree(services['type'], services['services'])
        if 'type' in services and 'environment' in services:
            return self.node_loader.get_nodes_by(services['type'], environments=services['environment'])
        if 'type' in services:
            return self.node_loader.get_nodes_by(services['type'])

    def inspect_dependencies(self):
        """Inspect dependencies"""
        mlog.log.info("Inspecting dependencies")
        # Ispect dependencies and isolated conflicts in nodes
        # Load set
        self.node_loader.load(self.data_files_directory + '/nodes',
                              self.inspect)
        if self.inspect_missing_dependencies():
            mlog.log.info("Impossible to generate dependency graph, " +
                          "please fix the previous conflicts")
            sys.exit(0)
        self.node_loader.set_all_environments(
            self.data_files_directory + '/environments')
        # Iterate over available environments
        for env in self.node_loader.all_environments:
            # Add nodes to graph
            self.node_loader.add_nodes_to_graph(self.DG, env)
            # Validate dependencies conflicts
            self.node_loader.validate_conflicts(
                self.DG, self.force, env, inspect=True)
            # Validate isolated nodes
            self.node_loader.validate_graph(
                self.DG, inspect=True, environment=env)
            # Validate cyclic closed dependencies
            self.node_loader.validate_cyclic_dependencies(
                self.DG, env, inspect=True)
            # Set DG to empty graph
            self.DG = app.get_base_graph()
        # sys.exit(0)

    def exec(self):
        """Execute"""
        mlog.log.info("Executing orchestration")
        # Execute phases
        while self.phase <= self.phases:
            mlog.log.info(f'Starting phase: {self.phase}')
            self.orchestrate_nodes()
            mlog.log.info(f'Phase {self.phase} completed.')
            # Execute post-processes
            self.orchestrate_processes()
            # Increment phase
            self.phase += 1

    def setup(self):
        """Setup"""
        mlog.log.info("Setting up")
        # Create thread logger directories
        os.makedirs(self.thread_log_path, exist_ok=True)
        # Determine phases
        if self.force and self.process_single_action:       # Force single action
            # 0 is the preflight and dryrun phase
            self.phase = 0
            self.phases = 0                                 # Force single phase
        elif self.phase == -1:                              # Default to all phases
            self.phases = self.node_loader.find_phases()    # Find phases
            self.phase = 1                                  # Start at phase 1
        elif self.phase == 0:                               # Preflight
            # 0 is the preflight and dryrun phase
            self.phase = 0
            self.phases = 0                                 # Force single phase
        else:                                               # Single phase
            self.phases = self.phase                        # Force single phase
        # Load manifest files
        self.node_loader.load(
            self.data_files_directory + '/nodes', self.inspect)
        self.node_loader.set_all_environments(
            self.data_files_directory + '/environments')
        # Inspect the data
        if self.inspect:
            # Inspect dependencies and isolated conflicts in nodes
            self.node_loader.manifest_missing_actions()
            # Exit after inspecting
            sys.exit(0)
        # Find node parents
        self.node_loader.find_parents(self.environment)
        # Validate if environment is available
        self.node_loader.validate_environment(self.environment)
        # Validate node-graph
        self.node_loader.validate_node_graph()
        # Add nodes to graph
        self.node_loader.add_nodes_to_graph(self.DG, self.environment)
        # Validate cyclic conflicts
        self.node_loader.cyclic_validation()
        # Validate dependencies conflicts
        self.node_loader.validate_conflicts(
            self.DG, self.force, self.environment)
        # Validate isolated nodes
        self.node_loader.validate_graph(
            self.DG, force=self.force, environment=self.environment)
        # Validate cyclic closed dependencies
        self.node_loader.validate_cyclic_dependencies(
            self.DG, self.environment)
        # Inspect graph
        self.inspect_graph()
        # Draw charts
        if self.drawcharts:
            self.draw_charts()
            mlog.log.info('Charts generated')
        if self.chartsonly:
            mlog.log.info('Execution completed due to --chartsonly flag')
            sys.exit(0)


app = Mudra()


@click.command()
@click.option('--phase', default=-1, help='phase to execute')
@click.option('--environment', default='', help='environment to execute against')
@click.option('--datafiles', default='', help='data files location (relative)')
@click.option('--node', default=None, help='process single node, by name')
@click.option('--nodes', default=None, help='process multiple nodes, by comma-separated names')
@click.option('--nodefilter', default=None, help='process multiple nodes, based on filter text')
@click.option('--action', default=None, help='filters a single action on all nodes, by name')
@click.option('--extravars', default=None, help='pass in extra environment variables at runtime')
# @click.option('--extravars', default=None, cls=Click_Formatter, help='pass in extra environment variables at runtime')
@click.option('--preflight', default=False, is_flag=True, help='only execute the preflight action of node-interfaces')
@click.option('--dryrun', default=False, is_flag=True, help='only simulate the actions of node-interfaces')
@click.option('--drawcharts', default=False, is_flag=True, help='generate the charts')
@click.option('--chartsonly', default=False, is_flag=True, help='only generate the charts, do not execute actions')
@click.option('--force', default=False, is_flag=True, help='push through safeguards')
@click.option('--inspect', default=False, is_flag=True, help='validate and inspect the datafiles')
@click.option('--loglevel', default=None, help='log level (Default: INFO')
@click.option('--gettree', default=False, is_flag=True, help="report values from dependency tree walk")
# @click.option('--gettree', is_flag=True, cls=Click_Formatter, help="report values from dependency tree walk")
@click.option('--nodetype', default=None, help='processes only this node type')
@click.option('--maxworkers', default=1, help='Number of workers for parallel execution')
@click.option('--logprojectname', default=None, help='Set cloud logging project name')
@click.option('--threadlogpath', default='logs/thread_logs', help='Where to store thread logs')
@click.option('--restart', default=False, is_flag=True, help='Used to restart the node tracking')
@click.option('--skipnodes', default=None, help='Skip nodes by name (comma-separated list)')
@click.argument("args", nargs=-1)
def cli(phase, environment, datafiles, node, nodes, nodefilter, action, extravars, preflight, dryrun, chartsonly, drawcharts, force, inspect, gettree, loglevel, nodetype, maxworkers, logprojectname, threadlogpath, restart, skipnodes, args):
    # Restart .meta folder
    # if os.path.exists('.meta'):
    #     shutil.rmtree('.meta')
    # Set log level
    if not loglevel:
        loglevel = "INFO"
    app.loglevel = loglevel
    signal.signal(signal.SIGINT, app.signal_handler)
    app.mlog.log.setLevel(app.loglevel)
    logging.getLogger('sh').setLevel(logging.INFO)
    app.mlog.log.info(f'Log level: {app.loglevel}')
    # Log project name
    app.mlog.log.info(f'Log project name: {logprojectname}')
    # Thread log directory
    app.thread_log_path = threadlogpath
    app.mlog.log.info(f'Thread log directory: {app.thread_log_path}')
    # Set data files location
    app.data_files_directory = datafiles or os.getenv('MUDRA_DATAFILES') or 'mock_data_files'
    app.mlog.log.info(f'Data files location: {app.data_files_directory}')
    # Restart node tracking
    if restart:
        app.mlog.log.info('Restarting execution from first node')
        # Delete node tracking directories
        if os.path.exists('logs/executed_nodes'):
            shutil.rmtree('logs/executed_nodes')
        if os.path.exists('logs/failed_preflight'):
            shutil.rmtree('logs/failed_preflight')
    else:
        app.mlog.log.info('Resuming exeuction from last successful node')
    # Ensure node tracking directories exists
    if not os.path.exists('logs/executed_nodes'):
        os.makedirs('logs/executed_nodes')
    if not os.path.exists('logs/failed_preflight'):
        os.makedirs('logs/failed_preflight')
    # Configure skipnodes
    if skipnodes:
        app.skipnodes = skipnodes.split(',')
        app.mlog.log.info(f'Skipping nodes: {app.skipnodes}')
    # Set environment
    app.environment = environment or os.getenv('MUDRA_ENVIRONMENT') or 'local'
    app.mlog.log.info(f'Environment: {app.environment}')
    # Set extravars
    app.extravars = extravars
    app.mlog.log.info(f'Extravars: {app.extravars}')
    # Draw charts
    app.drawcharts = drawcharts
    app.mlog.log.info(f'Drawcharts: {app.drawcharts}')
    # Charts only
    app.chartsonly = chartsonly
    app.mlog.log.info(f'Chartsonly: {app.chartsonly}')
    # Set force
    app.force = force
    app.mlog.log.info(f'Force: {app.force}')
    # Set inspect
    app.inspect = inspect
    app.mlog.log.info(f'Inspect: {app.inspect}')
    # Set max workers
    app.maxworkers = maxworkers
    app.mlog.log.info(f'Maxworkers: {app.maxworkers}')
    # Set gettree
    app.gettree = gettree
    app.args = args
    app.mlog.log.info(f'Gettree: {app.gettree}')
    app.mlog.log.info(f'Args: {app.args}')
    # Set node, if specified
    app.process_single_node = node
    app.mlog.log.info(f'Process single node: {app.process_single_node}')
    # Set nodes, if specified
    if nodes:
        app.process_multiple_nodes = nodes.split(',')
        app.mlog.log.info(f'Process multiple nodes: {app.process_multiple_nodes}')
    # Set nodefilter, if specified
    app.process_node_filter = nodefilter
    app.mlog.log.info(f'Process nodes filter: {app.process_node_filter}')
    # Set action, if specified
    app.process_single_action = action
    app.mlog.log.info(f'Process single action: {app.process_single_action}')
    # Set nodetype
    app.nodetype = nodetype
    if app.gettree:
        app.inspect_tree()
        sys.exit(0)
    if app.inspect:
        # Inspect the data
        app.inspect_dependencies()
    else:
        # Set preflight
        app.preflight = preflight
        app.mlog.log.info(f'Preflight: {app.preflight}')
        # Set phase 0 for preflight
        if app.preflight:
            app.phase = 0   # 0 is the preflight and dryrun phase
        # Force dryrun for chartsonly
        if app.chartsonly:
            app.drawcharts = True
            app.dryrun = True
        else:
            app.dryrun = dryrun
        # Dryrun
        if app.dryrun:
            app.mlog.log.info(f'Dryrun: {app.dryrun}')
            app.phase = 0   # 0 is the preflight and dryrun phase
            app.node_loader.virtualize_missing_dependencies = True
    # Set phase
    app.phase = phase
    # Setup Mudra
    app.setup()
    # Log phase
    app.mlog.log.info(f'Phase: {app.phase}')
    # Execute
    app.exec()


if __name__ == '__main__':
    cli()
