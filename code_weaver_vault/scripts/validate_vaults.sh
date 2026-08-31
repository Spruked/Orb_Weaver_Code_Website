#!/bin/bash
# Validate vaults
echo "Validating vaults..."
for vault in vaults/*/; do
  if [ -f "$vault/vault.json" ]; then
    echo "Valid vault: $vault"
  else
    echo "Invalid vault: $vault"
  fi
done