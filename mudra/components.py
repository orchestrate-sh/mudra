"""Nodes classes.

Nodes classes for dependencies and interfaces."""
from itertools import chain


class Node:
    """Graph node."""

    def __init__(self, name, type, dependencies=None, meta=None, file_name='',
                 actions=None, produces=None, environments=None, parents=None):
        """Initialize graph node.

        name: string name of node
        dependencies: string list of nodes.
        type: string, type of service.
        """
        self.name = name
        self.type = type
        self.parents = parents or {}
        self.dependencies = dependencies or {}
        self.meta = meta or {}
        self.file_name = file_name
        self.actions = actions or {}
        self.produces = produces or []
        self.environments = environments or {}

    def __str__(self):
        return str(self.__class__) + ": " + str(self.__dict__)

    def find_children_by_env(self, selected_env):
        children = set()
        for child in chain.from_iterable(self.dependencies.values()):
            # Dependencies item is str
            if isinstance(child, str):
                children.add(child)
                continue
            # Dependencies item is Dict
            assert isinstance(child['environments'], list)
            if selected_env in child['environments']:
                children.add(child['name'])
        for output_node in self.produces:
            # produces item is str
            if isinstance(output_node, str):
                children.add(output_node)
                continue
            # produces item is Dict
            assert isinstance(output_node['environments'], list)
            if selected_env in output_node['environments']:
                children.add(output_node['name'])
        return children
