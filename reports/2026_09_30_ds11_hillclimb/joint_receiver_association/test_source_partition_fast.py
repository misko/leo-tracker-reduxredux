from unittest.mock import patch
import source_partition_fast
from test_source_partition import SourcePartitionTests


class FastSourcePartitionTests(SourcePartitionTests):
    def setUp(self):
        replacement = patch('test_source_partition.partition', source_partition_fast.partition)
        replacement.start()
        self.addCleanup(replacement.stop)
