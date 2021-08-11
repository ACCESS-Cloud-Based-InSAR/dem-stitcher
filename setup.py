from distutils.core import setup
from os import path

file_dir = path.abspath(path.dirname(__file__))

# Get the long description from the README file.
with open(path.join(file_dir, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

desc = '''Download and merge DEM tiles
for processing interferograms with ISCE2.'''

setup(name='dem_stitcher',
      version='0.0.0',
      description=desc,
      long_description=long_description,
      long_description_content_type='text/markdown',
      url='https://github.com/aria-jpl/dem_stitcher',
      author='''Charlie Marshak, David Bekaert,
      Michael Denbina, Marc Simard''',
      author_email='charlie.z.marshak@jpl.nasa.gov',
      keywords='dem',
      packages=['dem_stitcher'],
      package_data={"dem_stitcher": ["data/*.geojson.zip", "data/*.tif"]},
      # Required Packages
      # We assume an environment specified by requirements.txt is provided.
      install_requires=[],
      )
