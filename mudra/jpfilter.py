"""Standardize the node tree structure."""
from jmespath import search as jp
from mudra.components import Node
from mudra.manifest import NodeLoader
from typing import Dict, List


class Query:
    """Main class to perform node tree queries.

    From NodeLoader nodes, ensures default_env exists in property environments.
    Dependencies List[str] are converted to dict with name and envs.
    Property environments change from dict to List[str]."""

    def __init__(self, nl: NodeLoader, default_env: str) -> None:
        self.environment = default_env
        nl.find_parents(default_env)

        # Ensure current env exists.
        for node_name in nl.nodes:
            if nl.nodes[node_name].environments:
                nl.nodes[node_name].environments[self.environment] = (
                    nl.nodes[node_name].environments.get(self.environment,
                                                         False))
            else:
                nl.nodes[node_name].environments[self.environment] = True

        self.nodes = [NodeLoader.json_serial(node)
                      for node in nl.nodes.values()
                      # if node.environments.get(self.default_env)
                      ]
        self._flatten_data(self.nodes)

    def _flatten_data(self, nodes: List[Node]) -> None:
        """Change dependencies items from str to dict."""
        def str_to_dict(items):
            for i, item in enumerate(items):
                if isinstance(item, str):
                    items[i] = dict(name=item,
                                    environments=[self.environment])

        for node in nodes:
            # Change str to dict
            for my_list in node['dependencies'].values():
                str_to_dict(my_list)
            str_to_dict(node['produces'])

            # Change node.environments from {'dev': True, 'sb1': True} to ['dev', sb1']
            if not node['environments']:
                node['environments'][self.environment] = True
            node['environments'] = [key for key in node['environments']
                                    if node['environments']]

    def get_kafkas(self) -> List[Dict[str, List[str]]]:
        """Get kafka node names from Apps.dependencies and produces."""
        query = """
          [?produces[?contains(environments, `{env}`)] ||
           dependencies.Kafka[?contains(environments, `{env}`)]].
          {{name: name,
            produces: produces[?contains(environments, `{env}`)].name,
            kafka: dependencies.Kafka[?contains(environments, `{env}`)].name,
            file: file_name}}
        """.format(env=self.environment)
        return jp(query, self.nodes)

    def get_dbs(self, phase: int, action: str) -> List[str]:
        """Get database node names by phase and action."""
        query = f"""
           [?type==`Database` && actions."{action}".phases[?@==`{phase}`]].
           name"""
        return jp(query, self.nodes)

    def get_dbs_actions(self) -> List[str]:
        """Returns db actions."""
        return set(jp('[?type==`Database`].[actions.keys(@)][][]', self.nodes))


if __name__ == '__main__':
    nl = NodeLoader()
    nl.load('au_data_files_incoming/nodes')
    query = Query(nl, 'dev')
    print('len:', len(query.nodes))
    res = query.get_kafkas()
