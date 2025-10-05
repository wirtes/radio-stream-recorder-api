# SSH Key Setup

Place your SSH private key in this directory as `id_rsa` for SCP transfers.

## Setup Instructions

1. Copy your SSH private key to this directory:
   ```bash
   cp ~/.ssh/id_rsa ./ssh/id_rsa
   ```

2. Set proper permissions:
   ```bash
   chmod 600 ./ssh/id_rsa
   ```

3. Ensure the key is accessible to the container user (UID 10001):
   ```bash
   sudo chown 10001:10001 ./ssh/id_rsa
   ```

## Security Notes

- The SSH key should have read-only permissions (600)
- The key is mounted as read-only in the container
- Ensure the remote server accepts this key for the target user