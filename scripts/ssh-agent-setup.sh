#!/usr/bin/env bash
set -euo pipefail

# Minimal ssh-agent bootstrap for WSL shells.
# - Starts ssh-agent if not running
# - Ensures SSH_AUTH_SOCK is set (optionally ~/.ssh/agent.sock)
# - Adds all private keys in ~/.ssh, excluding non-key files

agent_sock="${SSH_AUTH_SOCK:-$HOME/.ssh/agent.sock}"

start_agent() {
  mkdir -p "$HOME/.ssh"
  eval "$(ssh-agent -a "$agent_sock")" >/dev/null
}

if [ -S "$agent_sock" ]; then
  export SSH_AUTH_SOCK="$agent_sock"
  rc=0
  ssh-add -l >/dev/null 2>&1 || rc=$?
  if [ $rc -eq 0 ] || [ $rc -eq 1 ]; then
    if [ "$agent_sock" = "$HOME/.ssh/agent.sock" ] \
      && [ -f "$HOME/.ssh/agent.relay" ]; then
      # Relay socket detected; do not start a local agent or add keys.
      return 0 2>/dev/null || exit 0
    fi
  fi
  if [ $rc -eq 2 ]; then
    rm -f "$agent_sock"
    start_agent
  fi
else
  start_agent
fi

shopt -s nullglob
for key in "$HOME/.ssh"/*; do
  case "$key" in
    *.pub|*/known_hosts|*/config|*/authorized_keys) continue ;;
  esac
  if [ -f "$key" ] && [ ! -L "$key" ]; then
    if ! grep -q "BEGIN OPENSSH PRIVATE KEY" "$key" 2>/dev/null \
      && ! grep -q "BEGIN RSA PRIVATE KEY" "$key" 2>/dev/null \
      && ! grep -q "BEGIN DSA PRIVATE KEY" "$key" 2>/dev/null \
      && ! grep -q "BEGIN EC PRIVATE KEY" "$key" 2>/dev/null; then
      continue
    fi
    ssh-add "$key" >/dev/null || true
  fi
done
