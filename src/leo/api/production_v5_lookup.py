"""ALGO06 API with direct validated lookup for completed results."""
from leo.api import production
from leo.storage.graph_position_lookup_v5 import graph_position_view

def main():
    production.GraphPositionView=graph_position_view
    production.main()

if __name__=='__main__':main()
