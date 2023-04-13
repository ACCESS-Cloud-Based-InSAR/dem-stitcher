from pathlib import Path

import pytest

notebooks = ['Basic_Demo.ipynb',
             'Comparing_DEMs.ipynb',
             'Filling_in_missing_glo-30_tiles_with_glo-90_tiles.ipynb',
             'Merging_DEM_Tiles_into_a_VRT.ipynb'
             ]


@pytest.mark.integration
@pytest.mark.notebook
@pytest.mark.parametrize('notebook_file_name', notebooks)
def test_read_geoid_across_dateline(notebooks_dir,
                                    test_data_dir,
                                    notebook_file_name):

    import papermill as pm

    test_dir = test_data_dir.parent
    out_dir = test_dir / 'out_test_nb'
    out_dir.mkdir(exist_ok=True, parents=True)
    parameters = {}

    if notebook_file_name == 'Basic_Demo.ipynb':
        out_tif_dir = Path(test_dir) / 'out'
        out_tif_dir.mkdir(exist_ok=True, parents=True)
        parameters = dict(out_directory_name=str(out_tif_dir))

    pm.execute_notebook(notebooks_dir / notebook_file_name,
                        output_path=(out_dir / notebook_file_name),
                        parameters=parameters
                        )
