import papermill as pm
from dem_stitcher.datasets import DATASETS
import pytest
from pathlib import Path


@pytest.mark.parametrize("dem_name", DATASETS)
def test_download_dem(dem_name):

    test_directory = Path(__file__).parents[0].absolute()

    out_dir = test_directory/'out'
    out_dir.mkdir(exist_ok=True)

    out_notebook = out_dir/f'{dem_name}.ipynb'

    pm.execute_notebook(test_directory/'test_notebook.ipynb',
                        output_path=out_notebook,
                        parameters=dict(dem_name=dem_name,
                                        test_dir=str(test_dir)
                                        ))
