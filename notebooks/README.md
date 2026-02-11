
# sealevel/notebooks directory

- Python project to orchestrate modules within the Framework for Accessing Changes To Sea-level (FACTS).  

## Objectives

- These Notebooks run in Discover jupyter hub:  https://jh-discover.nccs.nasa.gov.  Execute in the order below and if any fail, consult the NOTE below:
1. [Runs select FACTS modules (e.g., fair, lws, and stereodynamics) ](https://github.com/nasa-nccs-hpda/sealevel/blob/main/notebooks/1_fair_facts_v2.ipynb)
2. [Aggregates total sealevel deltas from  #1 output ](https://github.com/nasa-nccs-hpda/sealevel/blob/main/notebooks/2_fair_facts_v2_total.ipynb)
3. [Visualizes total sealevel deltas from #2 output ](https://github.com/nasa-nccs-hpda/sealevel/blob/main/notebooks/3_fair_facts_v2_total_viz.ipynb)

NOTES:

1) For kernel selection, use 'conda env:base' for 3_fair_facts_v2_viz_total, and  'conda env:viz' for the other two.  
2) Depending on the runtime environment where the Notebooks are launched, certain Python packages may reach out to pull in other dependencies.  If running on 
the Discover jupyter hub, the gpu node has no internet access allowed, so these dependencies cannot be resolved.  A workaround is to temporarily convert the Notebook
to a Python application and run it from the command line.  Afterward a successfully run, the Notebook should work also because it can resolve the dependencies. 

A sample session follows:

- gtamkin@GSLAL032412001:/Users/gtamkin$ ssh -XY gtamkin@discover.nccs.nasa.gov
- gtamkin@discover14:/home/gtamkin$ cd /tmp
- gtamkin@discover14:/tmp$ git clone https://github.com/nasa-nccs-hpda/sealevel.git
Cloning into 'sealevel'...
remote: Enumerating objects: 538, done.
remote: Counting objects: 100% (538/538), done.
remote: Compressing objects: 100% (338/338), done.
remote: Total 538 (delta 176), reused 499 (delta 155), pack-reused 0 (from 0)
Receiving objects: 100% (538/538), 16.56 MiB | 39.89 MiB/s, done.
Resolving deltas: 100% (176/176), done.
- gtamkin@discover14:/tmp$ cd sealevel/notebooks/
- gtamkin@discover14:/tmp/sealevel/notebooks$ module load anaconda
activate base
- (base) gtamkin@discover14:/tmp/sealevel/notebooks$ jupyter nbconvert --to python 3_fair_facts_v2_total_viz.ipynb 
[NbConvertApp] Converting notebook 3_fair_facts_v2_total_viz.ipynb to python
[NbConvertApp] Writing 187627 bytes to 3_fair_facts_v2_total_viz.py



# If you see the following error, go back and run the first two notebooks from Jupyter Hub to seed the input directories
(base) gtamkin@discover14:/tmp/sealevel/notebooks$ python 3_fair_facts_v2_total_viz.py 

./data/output/fair:
  (directory doesn't exist)

./data/output/lws:
  (directory doesn't exist)

./data/output/sterodynamics:
  (directory doesn't exist)
Loading output files...
  - Not found: data/output/fair/climate.nc
  - Not found: data/output/fair/gsat.nc
  - Not found: data/output/fair/oceantemp.nc
  - Not found: data/output/fair/ohc.nc
  - Not found: data/output/lws/gslr.nc
  - Not found: data/output/lws/lslr.nc
  - Not found: data/output/sterodynamics/gslr.nc
  - Not found: data/output/sterodynamics/lslr.nc

⚠ No datasets loaded. Please run the workflow first to generate outputs.
================================================================================
VERIFYING SEA LEVEL TOTALS
================================================================================
. . . . .

(base) gtamkin@discover14:/tmp/sealevel/notebooks$ python 3_fair_facts_v2_total_viz.py 

./data/output/fair:
  (directory doesn't exist)

./data/output/lws:
  (directory doesn't exist)

./data/output/sterodynamics:
  (directory doesn't exist)
Loading output files...
  - Not found: data/output/fair/climate.nc
  - Not found: data/output/fair/gsat.nc
  - Not found: data/output/fair/oceantemp.nc
  - Not found: data/output/fair/ohc.nc
  - Not found: data/output/lws/gslr.nc
  - Not found: data/output/lws/lslr.nc
  - Not found: data/output/sterodynamics/gslr.nc
  - Not found: data/output/sterodynamics/lslr.nc

⚠ No datasets loaded. Please run the workflow first to generate outputs.
================================================================================
VERIFYING SEA LEVEL TOTALS
================================================================================

============================================================
VERIFYING LSLR TOTALS
============================================================

Traceback (most recent call last):
  File "/home/gtamkin/.local/lib/python3.11/site-packages/xarray/backends/file_manager.py", line 219, in _acquire_with_cache_info
    file = self._cache[self._key]
           ~~~~~~~~~~~^^^^^^^^^^^
  File "/home/gtamkin/.local/lib/python3.11/site-packages/xarray/backends/lru_cache.py", line 56, in __getitem__
    value = self._cache[key]
            ~~~~~~~~~~~^^^^^
KeyError: [<class 'netCDF4._netCDF4.Dataset'>, ('/tmp/sealevel/notebooks/data/output/totaled_output_all_lslr.nc',), 'r', (('clobber', True), ('diskless', False), ('format', 'NETCDF4'), ('persist', False)), 'f3201492-c53a-4140-9ce6-5d36141b7e1a']



