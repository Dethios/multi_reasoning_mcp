# WSL SSH agent auto-start

This repo includes a small helper script to start `ssh-agent`, set
`SSH_AUTH_SOCK`, and load all private keys from `~/.ssh` while ignoring
non-key files.

## Usage

1. Add this line to your shell startup file (for example, `~/.bashrc`):

```bash
source "$HOME/dev-workspace/projects/multi_reasoning_mcp/scripts/ssh-agent-setup.sh"
```

2. Open a new shell, or run the command above in the current shell.

The script uses `~/.ssh/agent.sock` by default if `SSH_AUTH_SOCK` is not
already set, and it only adds files that look like private keys.

## Windows SSH agent integration (no passphrase prompts)

Use the Windows OpenSSH agent and relay it into WSL so your keys load once
on Windows and are available in WSL.

### 1) Enable the Windows OpenSSH Authentication Agent service

In Windows, enable and start the **OpenSSH Authentication Agent** service.

### 2) Load keys into the Windows agent

From a Windows terminal, add your key to the agent:

```powershell
ssh-add $env:USERPROFILE\.ssh\id_ed25519
```

### 3) Relay the Windows agent into WSL

Set up a relay that exposes a Unix socket in WSL and forwards to the
Windows agent pipe `\\.\pipe\openssh-ssh-agent`. One common approach is
`npiperelay.exe` with `socat`. Ensure both are installed and available on
your PATH in WSL.

Example (run in WSL):

```bash
mkdir -p "$HOME/.ssh"
rm -f "$HOME/.ssh/agent.sock"
: > "$HOME/.ssh/agent.relay"
npiperelay.exe -ei -s //./pipe/openssh-ssh-agent \
  | socat UNIX-LISTEN:"$HOME/.ssh/agent.sock",fork -
```

### 4) Use the relay in WSL

Export the socket path in your shell startup (or rely on the setup script
which will use the socket if it exists):

```bash
export SSH_AUTH_SOCK="$HOME/.ssh/agent.sock"
```
