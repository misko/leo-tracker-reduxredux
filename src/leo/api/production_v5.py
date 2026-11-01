"""ALGO06 composition entrypoint retaining the frozen ALGO05 API factory."""
from leo.api import production
from leo.storage.graph_position_view_v5 import graph_position_view

def main():
    # Replace this composition module's reader factory only, before app creation.
    production.GraphPositionView=graph_position_view
    production.main()

if __name__=='__main__':main()
