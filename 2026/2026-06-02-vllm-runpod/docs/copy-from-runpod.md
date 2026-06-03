# Copy `/vllm-project` From RunPod

This historical note documents how the initial project files were copied from a
RunPod pod.

Remote source:

```text
/vllm-project
```

Local target:

```bash
~/tmp/vllm-experiments
```

## Key Point

Do not use the `ssh.runpod.io` Basic SSH gateway for file copy.

The local SSH alias `runpod` pointed at RunPod's Basic SSH gateway:

```ssh-config
Host runpod
    HostName ssh.runpod.io
    User <basic-ssh-user>
    IdentityFile ~/.ssh/runpod
```

That path supported interactive SSH, but it did not support SCP/SFTP in this
environment. RunPod file transfer needed the pod's Full SSH endpoint: public IP
plus the mapped TCP port for SSH.

RunPod docs:

```text
https://docs.runpod.io/pods/configuration/use-ssh
```

## 1. Discover The Full SSH Endpoint

Connect through Basic SSH with a forced PTY and print the RunPod-provided
connection variables:

```bash
ssh -tt runpod <<'EOF'
printf 'RUNPOD_PUBLIC_IP=%s\nRUNPOD_TCP_PORT_22=%s\n' \
  "$RUNPOD_PUBLIC_IP" \
  "$RUNPOD_TCP_PORT_22"
exit
EOF
```

For this pod, the result was:

```text
RUNPOD_PUBLIC_IP=<public-ip>
RUNPOD_TCP_PORT_22=<ssh-port>
```

So the direct SSH endpoint was:

```text
root@<public-ip> -p <ssh-port>
```

## 2. Enable Key-Only Auth On The Direct Endpoint

The direct endpoint initially rejected the local `runpod` key. Add the public
key to the pod through the working Basic SSH session:

```bash
pub="$(cat ~/.ssh/runpod.pub)"

ssh -tt runpod <<EOF
mkdir -p /root/.ssh
chmod 700 /root/.ssh
grep -qxF '$pub' /root/.ssh/authorized_keys 2>/dev/null || \
  echo '$pub' >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
exit
EOF
```

Verify direct key-only SSH:

```bash
ssh -p <ssh-port> \
  -i ~/.ssh/runpod \
  -o StrictHostKeyChecking=no \
  -o PasswordAuthentication=no \
  root@<public-ip> "echo ok"
```

Expected output:

```text
ok
```

## 3. Check What To Copy

List the project files on the pod:

```bash
ssh -p <ssh-port> \
  -i ~/.ssh/runpod \
  -o StrictHostKeyChecking=no \
  -o PasswordAuthentication=no \
  root@<public-ip> \
  "find /vllm-project -maxdepth 1 -type f -printf '%f\n' | sort"
```

Files found:

```text
.gitignore
.python-version
README.md
check_vllm_gpu.py
main.py
pyproject.toml
uv.lock
vllm_tool_agent.py
```

The project also had `.git`, `.venv`, and `__pycache__`. `.venv` was
intentionally not copied because a full recursive copy timed out while
transferring it.

## 4. Copy The Source Files

Run from the local target directory:

```bash
cd ~/tmp/vllm-experiments
```

Copy the source files explicitly:

```bash
scp -P <ssh-port> \
  -i ~/.ssh/runpod \
  -o StrictHostKeyChecking=no \
  -o PasswordAuthentication=no \
  root@<public-ip>:/vllm-project/.gitignore \
  root@<public-ip>:/vllm-project/.python-version \
  root@<public-ip>:/vllm-project/README.md \
  root@<public-ip>:/vllm-project/check_vllm_gpu.py \
  root@<public-ip>:/vllm-project/main.py \
  root@<public-ip>:/vllm-project/pyproject.toml \
  root@<public-ip>:/vllm-project/uv.lock \
  root@<public-ip>:/vllm-project/vllm_tool_agent.py \
  .
```

Copy repository metadata:

```bash
scp -r -P <ssh-port> \
  -i ~/.ssh/runpod \
  -o StrictHostKeyChecking=no \
  -o PasswordAuthentication=no \
  root@<public-ip>:/vllm-project/.git .
```

## 5. Verify Local Result

List local files:

```bash
find . -maxdepth 2 -type f | sort
```

Expected local files after later cleanup:

```text
.gitignore
.python-version
README.md
docs/copy-from-runpod.md
main.py
pyproject.toml
src/check_vllm_gpu.py
src/vllm_tool_agent.py
uv.lock
```

Check Git state:

```bash
git status --short
```

The pod's repository had no commits, and the source files were untracked there.
Local `git status --short` therefore showed those copied files as untracked too.

## Failed Attempts

Plain SCP through the `runpod` alias failed:

```bash
scp -r runpod:/vllm-project/. .
```

Error:

```text
subsystem request failed on channel 0
/usr/bin/scp: Connection closed
```

Legacy SCP mode also did not transfer files through the gateway:

```bash
scp -O -r runpod:/vllm-project/. .
```

Verbose output showed:

```text
Error: Your SSH client doesn't support PTY
```

The fix was to use Full SSH with `scp -P <ssh-port> root@<public-ip>:...`.
