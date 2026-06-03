import subprocess


cmd = [
    "nvidia-smi",
    "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
    "--format=csv,noheader,nounits",
]

print(subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT))
