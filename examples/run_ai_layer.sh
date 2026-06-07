#!/bin/bash
#SBATCH --job-name=tributary_ai
#SBATCH --partition=a100_only
#SBATCH --gres=gpu:1
#SBATCH --mem=64G
#SBATCH --cpus-per-task=8
#SBATCH --time=04:00:00
#SBATCH --output=/mnt/disk2/zeyu/Hackathon/Tributary/logs/ai_layer_%j.out
#SBATCH --error=/mnt/disk2/zeyu/Hackathon/Tributary/logs/ai_layer_%j.err

set -euo pipefail

REPO=/mnt/disk2/zeyu/Hackathon/Tributary
mkdir -p "$REPO/logs"

echo "=========================================="
echo " Tributary AI Layer"
echo " Job: $SLURM_JOB_ID  Node: $SLURMD_NODENAME"
echo " Start: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# Activate vace environment
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate vace

cd "$REPO"

# Run with --resume so a re-submit picks up where the job left off
python examples/run_ai_layer.py \
    --backend qwen \
    --resume

echo ""
echo "Finished: $(date '+%Y-%m-%d %H:%M:%S')"
