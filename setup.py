from distutils.core import setup
from os import path

file_dir = path.abspath(path.dirname(__file__))

# Get the long description from the README file.
with open(path.join(file_dir, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

desc = 'Download and merge DEM tiles for processing interferograms with ISCE2.'

setup(name='dem_stitcher',
      description=desc,
      use_scm_version=True,
      long_description=long_description,
      long_description_content_type='text/markdown',
      url='https://github.com/ACCESS-Cloud-Based-InSAR/dem_stitcher',
      author='''Charlie Marshak, David Bekaert,
      Michael Denbina, Marc Simard''',
      author_email='charlie.z.marshak@jpl.nasa.gov',
      keywords='dem',
      packages=['dem_stitcher'],
      package_data={"dem_stitcher": ["data/*.geojson.zip", "data/*.tif"]},
      python_requires='~=3.8',
      install_requires=['rasterio',
                        'geopandas',
                        'requests',
                        'tqdm',
                        'boto3'],
      extras_require={
        'develop': [
            'flake8',
            'flake8-import-order',
            'flake8-blind-except',
            'flake8-builtins',
            'pytest',
            'pytest-cov',
            'notebooks',
        ]}
      )
