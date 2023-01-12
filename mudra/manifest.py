"""Load nodes from yaml"""

import os
import click
import yaml
import sys
from yaml import parser
from itertools import chain
from collections import defaultdict
import jmespath
import networkx as nx
from mudra.components import Node

import mudra.mlog as mlog


class ProcessLoader:

    def __init__(self):
        self.processes = list()

    def load(self, input_path):
        """Load processes from yaml files in a directory"""
        mlog.log.debug(f'Discovering processes in {input_path}...')
        for yaml_file_name in [file_name for file_name
                               in os.listdir(input_path)
                               if file_name.lower().endswith(('.yaml', '.yml'))]:
            mlog.log.debug(f'Reading process {yaml_file_name}')
            with open(os.path.join(input_path, yaml_file_name), 'r') as file:
                process = None
                try:
                    process = yaml.load(file.read(),
                                        Loader=yaml.SafeLoader)
                except parser.ParserError as err:
                    print(yaml_file_name, ':', err)
                if process:
                    self.processes.append(process)


class NodeLoader:
    """Load yaml from a given path"""

    def __init__(self):
        """Initialize."""
        self.nodes = dict()  # key:Node's name.
        self.inspect_nodes = defaultdict(list)
        self.virtualize_missing_dependencies = False

    @staticmethod
    def get_base_inspect_nodes():
        """Get base inspect nodes"""
        return defaultdict(list)

    def get_node_names(self):
        """Get a set of nodes names (string)."""
        return set(self.nodes)

    def get_dependency_names(self):
        """Get a set of dependency names (strings)"""
        def g(x): return x if isinstance(x, str) else x["name"]
        return set((g(dependency) for node in self.nodes.values()
                    for dependency
                    in chain.from_iterable(node.dependencies.values())))

    def validate_node_in_environment(self, node_name, environment):
        """Get node environment"""
        try:
            return self.nodes[node_name].environments[environment]
        except KeyError as missing_environment:
            mlog.log.error(
                f"The {missing_environment} environment is not found for node `{node_name}`, please re-run the tool with the `--inspect` parameter to see all issues.")
            sys.exit(1)

    def get_manifest_enviroments(self):
        """Get all environments of the nodes (strings)"""
        mlog.log.debug('Discovering all node environments in node data...')
        return set((environment for node in self.nodes.values()
                    for environment
                    in node.environments.keys()))

    def validate_node_graph(self):
        """Check if all dependencies have corresponding node"""
        mlog.log.info('Validating node graph')
        node_names = self.get_node_names()
        dependencies = self.get_dependency_names()
        if not dependencies < node_names:
            missing_dependencies = dependencies-node_names
            if self.virtualize_missing_dependencies:
                for missing_dependency_name in missing_dependencies:
                    mlog.log.info(
                        f'Adding missing depedency as virtual: \
                            {missing_dependency_name}')
                    self.add_virtual_node(missing_dependency_name)
            else:
                raise click.ClickException(
                    'Node(s) specified as dependency does not exist: {}, please re-run the tool with the `--inspect` parameter to see all issues.'.format(str(missing_dependencies)))

    def cyclic_validation(self, inspect=False):
        """Validate if there are cyclic dependencies"""
        mlog.log.info('Validating cyclic dependencies')
        def g(x): return x if isinstance(x, str) else x["name"]
        def m(node_name): return self.inspect_nodes[node_name][0].file_name
        base_error_message = ''
        for key, node in self.inspect_nodes.items():
            for subnode in node:
                if key in [g(x) for x in
                           chain.from_iterable(subnode.dependencies.values())]:
                    base_error_message += f'#{key}: {m(key)} \n\n'
        error_message = "\n------------Cyclic conflicts---------------\n\n" + \
            base_error_message
        mlog.log.info(error_message)
        if not inspect and base_error_message:
            sys.exit(0)

    def validate_environment(self, in_environment):
        """Validate if environment is available, the available environments explicited
        in manifest and all included in the 'environments' folder"""
        mlog.log.info('Validating environment')
        if in_environment not in self.all_environments:
            mlog.log.error('\n Invalid environment, the valid environments are: ' +
                           f'{str(" & ".join(self.all_environments))}' +
                           '\n Please use another environment or add the environment')
            sys.exit(0)
        return

    def get_nodes_by(self, requested_type, environments=None, phase=None):
        """Get nodes by type, environments and phase"""
        mlog.log.debug(f'Discovering nodes by {requested_type}...')

        def t(requested, list_values):
            try:
                for sub_val in list_values:
                    if requested[0] in sub_val:
                        return True
                return False
            except IndexError:
                pass
        node_list = []
        try:
            phases = [list(x) if ',' not in x else list(x.split(','))
                      for x in phase.split(' ')]
            phases = [[int(y) for y in x] for x in phases]
        except AttributeError:
            for node in chain.from_iterable(self.inspect_nodes.values()):
                if node.type == requested_type:
                    if not environments:
                        node_list.append(f'{node.name}: {node.meta} \n')
                    if environments and environments in node.environments:
                        if node.environments[environments]:
                            node_list.append(f'{node.name}: {node.meta} \n')
            node_list.insert(
                0, f"\n---------------Services type={requested_type}" +
                f" in all phases---------------------\n\n")
        else:
            for node in chain.from_iterable(self.inspect_nodes.values()):
                located_phases = jmespath.search('*.phases', node.actions)
                node.meta["phases"] = located_phases
                for subphase in phases:
                    if (subphase in node.meta["phases"] or t(subphase, node.meta["phases"])) \
                            and node.type == requested_type:
                        if not environments:
                            node_list.append(f'{node.name}: {node.meta} \n')
                        if environments and environments in node.environments:
                            if node.environments[environments]:
                                node_list.append(
                                    f'{node.name}: {node.meta} \n')
                        break
            node_list.insert(
                0, f"\n---------------Services type={requested_type}" +
                f" and phase={phase}---------------------\n\n")
        mlog.log.info(" ".join(node_list))

    def inspect_tree(self, type_required, requested_services):
        """Inspect the tree and get the nodes"""
        mlog.log.info('Inspecting tree')
        initial_required_services = required_services = \
            requested_services.split(',')
        all_nodes = self.inspect_nodes.keys()
        def g(x): return x if isinstance(x, str) else x["name"]

        def j(node_name): return [x.dependencies.values(
        ) for x in self.inspect_nodes[node_name] if x.type != "Virtual"]

        def k(node_name):
            return ['//'+y+'//' if y not in all_nodes else y for y in
                    [g(x) for x in chain.from_iterable(
                        chain.from_iterable(j(node_name)))]] if "//" not in node_name \
                else []

        def t(node_name): return [y for y in k(
            node_name) if y != node_name and li(node_name)]

        def l(node_name):
            return self.inspect_nodes[node_name][0].type != "Virtual" \
                if "//" not in node_name else False

        def li(node_name, type_required="App"):
            try:
                return self.inspect_nodes[node_name][0].type == type_required
            except:
                return False

        def r(dependency_chain, dict_dependencies, type_required):
            other_dependencies = []
            if type_required == "App":
                return f'{dependency_chain[0]}: {dependency_chain}'
            other_dependencies = [dict_dependencies[val]
                                  for val in dependency_chain if val in dict_dependencies]
            return f'{dependency_chain[0]}: {set([x for x in chain.from_iterable(other_dependencies)])}'

        # defaultdict with all apps dependents
        dict_dependencies_app = defaultdict(list)
        dict_dependencies = defaultdict(list)
        while True:
            for node_name in required_services:
                if k(node_name) and l(node_name):
                    for subnode_name in t(node_name):
                        if li(subnode_name, "App"):
                            dict_dependencies_app[node_name].append(
                                subnode_name)
                        elif li(subnode_name, type_required):
                            dict_dependencies[node_name].append(subnode_name)

            newer_services = [x for x in chain.from_iterable(
                dict_dependencies_app.values())]
            old_services = dict_dependencies_app.keys()
            if required_services == set(newer_services) - set(old_services):
                break
            required_services = set(newer_services) - set(old_services)

        # Graph with apps dependencies
        tree_dependencies = nx.DiGraph()
        for key, v in dict_dependencies_app.items():
            for item in v:
                tree_dependencies.add_edge(key, item)
        for key, _ in dict_dependencies.items():
            tree_dependencies.add_node(key)

        # Convert graphs paths in sets
        all_dependencies_requirements = []
        for value in initial_required_services:
            if value in list(tree_dependencies.nodes()):
                T = nx.dfs_tree(tree_dependencies, source=value)
                all_dependencies_requirements.append(list(T.nodes()))

        dependencies_chain = f"\n-------------Required {type_required} ---------------\n\n"
        for dependency_chain in all_dependencies_requirements:
            dependencies_chain += f'#{r(dependency_chain, dict_dependencies, type_required)} \n\n'
        mlog.log.info(dependencies_chain)
        mlog.log.info(
            f"\n-------------Unique {type_required} required----------------\n\n"
            + str(set(chain.from_iterable(dict_dependencies.values()))))
        sys.exit(0)

    def find_missing_dependencies(self):
        """Find missing dependencies"""
        mlog.log.debug('Discovering missing dependencies...')
        nodes = self.inspect_nodes.keys()
        def g(x): return x if isinstance(x, str) else x["name"]

        def h(node_name): return [
            x.file_name for x in self.inspect_nodes[node_name] if
            x.type != "Virtual"]

        def j(node_name): return [x.dependencies.values(
        ) for x in self.inspect_nodes[node_name] if x.type != "Virtual"]

        def k(node_name): return ['//'+y+'//' if y not in nodes
                                  else y for y in [g(x) for x in chain.from_iterable(
                                      chain.from_iterable(j(node_name)))]]
        def l(
            node_name): return self.inspect_nodes[node_name][0].type != "Virtual"

        def m(node_name): return self.inspect_nodes[node_name][0].file_name

        def s(container, elem):
            for item in container:
                if elem in item:
                    return True

        repeated_nodes = [f'#{node_name}: {"  ".join(h(node_name))} \n\n'
                          for node_name in nodes if (len(h(node_name)) > 1
                                                     and l(node_name))]
        # TODO: Is this used?
        dependency_list = {}
        for node_name in nodes:
            try:
                if k(node_name) and l(node_name):
                    dependency_list[node_name] = " ".join(k(node_name))
            except:
                pass
        required_dependencies = [f'#{node_name} ({m(node_name)}):' +
                                 f' {" ".join(k(node_name))} \n\n'
                                 for node_name in nodes
                                 if (s(k(node_name), '//') and l(node_name))]
        conflict_status = repeated_nodes or s(required_dependencies, '//')
        repeated_nodes.insert(
            0, "\n---------------Repeated Nodes---------------------\n\n")
        mlog.log.info(" ".join(repeated_nodes))

        required_dependencies.insert(
            0, "\n---------------Missing Nodes---------------------\n"
            + "Missing nodes are //highlighted// below\n\n")
        mlog.log.info(" ".join(required_dependencies))

        self.cyclic_validation(inspect=True)

        if not conflict_status:
            self.nodes = ({k: v[0] for k, v in self.inspect_nodes.items()})
            self.inspect_nodes = NodeLoader().get_base_inspect_nodes()
        return conflict_status

    def get_subdir_list(self, input_path):
        """Get subdir list"""
        r_list = list()
        for dir_path, dir_names, file_names in os.walk(input_path):
            for file_name in file_names:
                r_list.append(os.path.join(dir_path, file_name))
        return r_list

    def get_wellknown_environments(self, input_path):
        """Get environments included in 'environments' folder"""
        mlog.log.debug(
            'Discovering wellknown environments in %s...', input_path)

        def f(x): return x if "." not in x else x[:x.index(".")]
        return set((f(x) for x in os.listdir(input_path)))

    def set_all_environments(self, input_path):
        """Set all environments"""
        mlog.log.debug('Discovering all environments...')
        wellknown_environments = self.get_wellknown_environments(input_path)
        manifest_environments = self.get_manifest_enviroments()

        all_environments = wellknown_environments | manifest_environments
        self.all_environments = all_environments
        for node in self.nodes.values():
            if node.environments:
                node.environments = {**{k: False for k in all_environments},
                                     **node.environments}
            else:
                node.environments = {k: True for k in all_environments}

    def set_diff_env(self, node):
        # TODO: What does this do?
        """Set environments included in manifest"""
        if "environments" in node:
            node_environments = node["environments"]
            node["environments"] = {k: True for k in node_environments}
            return node
        node["environments"] = {}
        return node

    def load(self, input_path, inspect=False):
        """Load nodes from input_path"""
        mlog.log.debug(f"Loading nodes from: {input_path}...")
        for yaml_file_name in [file_name for file_name
                               in self.get_subdir_list(input_path)
                               if file_name.lower().endswith(('.yaml', '.yml'))]:
            with open(yaml_file_name, 'r') as file:
                node = None
                try:
                    node = yaml.load(file.read(),
                                     Loader=yaml.SafeLoader)
                except parser.ParserError as err:
                    mlog.log.error(yaml_file_name, ':', err)
                if node:
                    # Add file name to node
                    node['file_name'] = yaml_file_name
                    # Add node
                    node = self.set_diff_env(node)
                    self.add_node(node, inspect)
                    # Attempt to add output nodes
                    if 'produces' in node:
                        output_nodes = node['produces']
                        if isinstance(output_nodes, (str, dict)):
                            output_nodes = [output_nodes]
                        for output_node in output_nodes:
                            if isinstance(output_node, str):
                                output_node = dict(name=output_node,
                                                   environments=node['environments'])
                            self.add_virtual_node(output_node['name'],
                                                  output_node['environments'],
                                                  node['file_name'], inspect)

    def find_parents(self, environment):
        """Find parents in selected environment"""
        mlog.log.debug(f"Discovering parents in: {environment}...")
        for node in self.nodes.values():
            try:
                children = (self.nodes[node_name]
                            for node_name in
                            node.find_children_by_env(environment))
                for child in children:
                    child.parents[node.name] = {'file': node.file_name}
            except KeyError:
                pass

    def add_virtual_node(self, name, node_environments={}, file_name=None, inspect=False):
        """Add virtual node"""
        mlog.log.debug(f"Adding virtual node to graph: {name}...")
        virtual_node = {
            'name': name,
            'type': 'Virtual',
            'dependencies': {},
            'file_name': file_name,
            'environments': {k: True for k in node_environments}
        }
        self.add_node(virtual_node, inspect)

    def add_node(self, node, inspect=False):
        """Add node"""
        mlog.log.debug(f"Adding node to graph: {node['name']}...")
        if inspect:
            self.inspect_nodes[node['name']].append(Node(**node))
            return
        if node['name'] in self.nodes:
            if 'Virtual' == node['type']:
                mlog.log.debug(
                    f'Virtual node {node["name"]} already exists...skipping')
                return
            elif 'Virtual' != self.nodes[node['name']].type:
                # Mute traceback
                sys.tracebacklimit = 0
                raise click.ClickException(
                    f"Tried to overwrite real node with duplicate node: {node['name']}. Please re-run the tool with the `--inspect` parameter to see all issues.")
            elif 'Virtual' == self.nodes[node['name']].type:
                mlog.log.debug(
                    f'Virtual node {node["name"]} already exists, overwriting existing node with real node...')
        self.nodes[node['name']] = Node(**node)

    def add_nodes_to_graph(self, graph, environment):
        """Add nodes and edges to the networkx graph."""
        mlog.log.debug(f"Adding nodes to graph: {environment}...")
        for node_name in self.get_node_names():
            if self.validate_node_in_environment(node_name, environment):
                graph.add_node(node_name)
        for node, dependency in ((node.name, dependency)
                                 for node in self.nodes.values()
                                 for dependency
                                 in chain.from_iterable(
                                 node.dependencies.values())):
            if self.validate_node_in_environment(node, environment):
                if isinstance(dependency, dict):
                    if environment in dependency["environments"]:
                        dependency = dependency["name"]
                        conflicts = not self.validate_node_in_environment(dependency,
                                                                          environment)
                        graph.add_edge(node, dependency, conflicts=conflicts)
                else:
                    conflicts = not self.validate_node_in_environment(dependency,
                                                                      environment)
                    graph.add_edge(node, dependency, conflicts=conflicts)

    def validate_conflicts(self, graph, force, environment, inspect=False):
        """Validate conflicts in edges by the edge-attr 'conflicts'"""
        mlog.log.info(
            f"Validating conflicts in graph for environment: {environment}")
        error_message = ''
        remove_nodes = []
        for edges in list(graph.edges()):
            if graph.edges[edges]["conflicts"]:
                remove_nodes.append(edges[1])
                error_message += f'\n Conflict with {"->".join(edges)}'
        if not error_message:
            mlog.log.info(
                f'\n ------------Dependency conflicts in {environment}------------\
                                \n No conflicts \n')
            return
        mlog.log.info(
            f'\n ------------Dependency conflicts in {environment}------------' +
            error_message)
        if inspect:
            return
        if not force:
            mlog.log.info(
                'Use --force to delete nodes with conflicts or isolated')
            sys.exit(0)

        graph.remove_nodes_from(remove_nodes)
        mlog.log.info(f'Nodes removed: {"|".join(remove_nodes)}')

    def validate_graph(self, graph, force=False, inspect=False, environment=None):
        """Identify isolated nodes in the dependency graph"""
        mlog.log.info(f"Validating graph for environment: {environment}")
        isolated_nodes = [node for (node, degree) in graph.degree()
                          if degree == 0]
        if not isolated_nodes:
            mlog.log.info(
                f'\n ------------Isolated conflicts in {environment}------------\
                            \n No conflicts \n')
            return
        mlog.log.error(
            f'\n------------Isolated conflicts in {environment}------------\
                        \n Isolated nodes: {"|".join(isolated_nodes)} \n')
        if inspect:
            return
        if force:
            graph.remove_nodes_from(isolated_nodes)
            mlog.log.info('Removed nodes: {}'.format(
                str(' | '.join(isolated_nodes))))
            return
        mlog.log.info(
            'Isolated or orphaned node(s) found. Please re-run the tool with the `--inspect` parameter to see all issues, or with the `--force` parameter to continue anyway and delete nodes with conflicts.')
        sys.exit(0)

    def find_phases(self):
        """Find phases"""
        mlog.log.debug('Discovering all defined phases from node data...')
        phases = list()
        # Find all possible phases across nodes
        for node in self.nodes.values():
            try:
                phases += jmespath.search('*.phases', node.actions)
            except Exception as e:
                mlog.log.error(e)
        # Collapse nested lists and return max phase, otherwise assume 1 phase
        try:
            return max([item for sublist in phases for item in sublist])
        except ValueError:
            return 1

    @staticmethod
    def json_serial(node):
        # TODO: What does this do?
        """Serialize node to ???"""
        return dict(name=node.name,
                    type=node.type,
                    parents=node.parents,
                    dependencies=node.dependencies,
                    meta=node.meta,
                    file_name=node.file_name,
                    actions=node.actions,
                    produces=node.produces,
                    environments=node.environments)

    def validate_cyclic_dependencies(self, graph, environment, inspect=False):
        """Validate cyclic dependencies in the graph"""
        mlog.log.info(
            f"Discovering cyclic dependencies in graph for environment: {environment}")
        cyclic_closed_conflicts = list(nx.simple_cycles(graph))
        if not cyclic_closed_conflicts:
            mlog.log.info(
                f'\n ------------Cyclic closed conflicts in {environment}------------\
                            \n No conflicts \n')
            return
        cyclic_closed_conflicts = "\n".join(map(str, cyclic_closed_conflicts))
        mlog.log.info(
            f'\n ------------Cyclic closed conflicts in {environment}------------\n' +
            cyclic_closed_conflicts)
        if inspect:
            return
        sys.exit(0)

    def manifest_missing_actions(self):
        """Find missing actions in nodes"""
        mlog.log.info('Discovering missing actions in nodes')
        manifest_missing_actions_all = []
        for node_val in self.nodes.values():
            if not node_val.actions and node_val.type != 'Virtual':
                manifest_missing_actions_all.append(node_val.file_name)
        if not manifest_missing_actions_all:
            mlog.log.info(
                f'\n ------------Manifests missing actions ------------\
                            \n No conflicts \n')
            return
        manifest_missing_actions_all = "\n".join(manifest_missing_actions_all)
        mlog.log.info(
            f'\n ------------Manifests missing actions------------\n \n' +
            manifest_missing_actions_all)
