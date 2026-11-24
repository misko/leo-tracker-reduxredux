"""Research-only projection reuse under the exact confidence trace binding."""

from accepted_confidence_trace import ConfidenceTrace, fingerprint


class ProjectionReuse(ConfidenceTrace):
    """Own one prepared view and a bounded set of its immutable projections."""

    def __init__(self, byte_limit=32*2**20):
        super().__init__()
        self.byte_limit = byte_limit
        self.producer = None
        self.generation = None
        self.planes = {}
        self.held_bytes = 0
        self.hits = 0
        self.original_calls = 0

    def project(self, operation, grid, coordinate):
        generation = tuple(self.current[key] for key in ("epochs", "source_geometry", "prepared_geometry"))
        if operation is not self.producer or generation != self.generation:
            self.producer, self.generation = operation, generation
            self.planes.clear()
            self.held_bytes = 0

        key = fingerprint(tuple(coordinate))

        def evaluate(grid, *coordinate):
            if key in self.planes:
                self.hits += 1
                return self.planes[key]
            result = operation(grid, *coordinate)
            self.original_calls += 1
            size = sum(array.nbytes for array in result)
            if self.held_bytes + size <= self.byte_limit:
                # The pinned projector owns fresh outputs. The confidence
                # calculation only indexes them to make per-track operands.
                planes = tuple(array.view() for array in result)
                for plane in planes:
                    plane.setflags(write=False)
                self.planes[key] = planes
                self.held_bytes += size
            return result

        return super().project(evaluate, grid, coordinate)
