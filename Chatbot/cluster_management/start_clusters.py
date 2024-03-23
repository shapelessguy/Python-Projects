from cluster_utils import *
hours = 3


def resources(pass_w=""):
    node_pool = NodePool("cian_cl", pass_w, nodes=[
        # HpcNode(ports=(5001, 5002, 5003, 5004), allocation_time=60 * hours),
        CaraNode(ports=(5005, 5006, 5007, 5009), allocation_time=60 * hours),
        # CaraNode(ports=(5009, 5010, 5011, 5012), allocation_time=60),
    ])
    return node_pool


def jupyter_notebook():
    node_pool = resources()
    tunneling(node_pool)
    node_pool.jupyter_notebook()


def main():
    node_pool = resources()
    tunneling(node_pool)
    node_pool.initialize(indexes=(0, ))


if __name__ == '__main__':
    # main()
    jupyter_notebook()
