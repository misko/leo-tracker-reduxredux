"""First and middle metadata-selected visits; freeze exact timing for controls."""
from pathlib import Path
import shifted_controls

if __name__ == '__main__':
    shifted_controls.HERE = Path(__file__).resolve().parent/'long-overlap'
    shifted_controls.main(selection_policy='long-overlap')
