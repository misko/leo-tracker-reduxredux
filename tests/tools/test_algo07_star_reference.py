from pathlib import Path

from run_algo07_star_reference import watcher_command


def test_reference_uses_production_watchers_and_keeps_budget(tmp_path):
    spec = dict(runtime=str(tmp_path), python='/interpreter', maximum_seconds=1200)
    for number in range(2, 8):
        command = watcher_command(f'ALGO{number:02d}', spec, Path('/private'))
        assert command[command.index('--maximum-seconds')+1] == '1200'
        assert command[command.index('--bulk-root')+1] == '/private'
        module = 'leo.cli.fast_graph_position'+('' if number == 2 else f'_v{number-1}')
        assert command[command.index('-m')+1] == module
        assert '--once' in command
        assert ('--worker-root' in command) == (number >= 4)
        assert ('--minimum-completed-utc-ns' in command) == (number >= 3)
