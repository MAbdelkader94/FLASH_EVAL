# HPC job submission

Drop SLURM (`*.sbatch`) or PBS (`*.qsub`) scripts here.
Each step is `python -m src.stepNN ...`, so wrapping is trivial. Example:

```bash
#!/bin/bash
#SBATCH -J flash_eval_step02
#SBATCH -N 1 -n 6
#SBATCH -t 04:00:00
#SBATCH -o logs/step02-%j.out
#SBATCH --mail-user=mohamed-abdelkader@uiowa.edu --mail-type=END,FAIL

cd $SLURM_SUBMIT_DIR
source /opt/anaconda/etc/profile.d/conda.sh
conda activate flash-eval

python -m src.step02_fetch_usgs --workers 6
```
