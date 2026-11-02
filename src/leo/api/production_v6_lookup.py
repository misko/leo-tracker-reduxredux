"""ALGO07 API composition retaining prior versioned public readers."""

from leo.api import production
from leo.api.graph_position_lookup_v6 import graph_position_view


def main():
    production.GraphPositionView = graph_position_view
    production.main()


if __name__ == "__main__":
    main()
