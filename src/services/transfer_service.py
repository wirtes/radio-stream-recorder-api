"""File transfer service for uploading recorded files via SCP."""

import os
import subprocess
import logging
from pathlib import Path
from typing import Optional
from src.models.config import ShowConfig


logger = logging.getLogger(__name__)


class TransferService:
    """Service for transferring files to remote locations via SCP."""
    
    def __init__(self, ssh_key_path: str = "/ssh/id_rsa"):
        """Initialize the transfer service.
        
        Args:
            ssh_key_path: Path to the SSH private key for authentication
        """
        self.ssh_key_path = ssh_key_path
        self._validate_ssh_key()
    
    def _validate_ssh_key(self) -> None:
        """Validate SSH key exists and has proper permissions."""
        if not os.path.exists(self.ssh_key_path):
            logger.warning(f"SSH key not found at {self.ssh_key_path}")
            return
        
        # Check SSH key permissions (should be 600)
        key_stat = os.stat(self.ssh_key_path)
        key_perms = oct(key_stat.st_mode)[-3:]
        
        if key_perms != '600':
            logger.warning(f"SSH key permissions are {key_perms}, should be 600")
    
    def transfer_file(self, local_path: str, show_config: ShowConfig, filename: str) -> bool:
        """Transfer file to remote location via SCP.
        
        Args:
            local_path: Path to the local file to transfer
            show_config: Show configuration containing remote directory info
            filename: Name for the file on the remote system
            
        Returns:
            True if transfer successful, False otherwise
        """
        if not os.path.exists(local_path):
            logger.error(f"Local file does not exist: {local_path}")
            return False
        
        # Validate file is readable
        try:
            with open(local_path, 'rb') as f:
                f.read(1)  # Try to read first byte
        except Exception as e:
            logger.error(f"Local file is not readable: {local_path} - {e}")
            return False
        
        try:
            # Build remote path with directory structure
            remote_path = self._build_remote_path(show_config, filename)
            logger.info(f"Transferring {local_path} to {remote_path}")
            
            # Validate remote directory configuration
            if not self._validate_remote_config(show_config):
                logger.error("Invalid remote directory configuration")
                return False
            
            # Create remote directory structure first
            if not self._create_remote_directory(show_config, filename):
                logger.error("Failed to create remote directory structure")
                return False
            
            # Execute SCP transfer with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                if attempt > 0:
                    logger.info(f"Retrying SCP transfer (attempt {attempt + 1}/{max_retries})")
                
                if self._execute_scp_command(local_path, remote_path):
                    logger.info(f"Successfully transferred file to {remote_path}")
                    
                    # Verify transfer if possible
                    if self.verify_transfer(local_path, show_config, filename):
                        logger.info("Transfer verification successful")
                    else:
                        logger.warning("Could not verify transfer, but SCP reported success")
                    
                    return True
                
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2 ** attempt)  # Exponential backoff
            
            logger.error(f"SCP transfer failed after {max_retries} attempts")
            return False
            
        except Exception as e:
            logger.error(f"Error during file transfer: {e}")
            return False
    
    def _validate_remote_config(self, show_config: ShowConfig) -> bool:
        """Validate remote directory configuration.
        
        Args:
            show_config: Show configuration to validate
            
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            remote_dir = show_config.remote_directory
            
            if not remote_dir:
                logger.error("Remote directory is empty")
                return False
            
            # Check if it's a valid SCP format (user@host:/path) or local path
            if '@' in remote_dir and ':' in remote_dir:
                # SCP format validation
                parts = remote_dir.split(':')
                if len(parts) < 2:
                    logger.error(f"Invalid SCP format: {remote_dir}")
                    return False
                
                host_part = parts[0]
                if '@' not in host_part:
                    logger.error(f"Invalid SCP host format: {host_part}")
                    return False
                
                # Check SSH key exists for remote transfers
                if not os.path.exists(self.ssh_key_path):
                    logger.error(f"SSH key required for remote transfer but not found: {self.ssh_key_path}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating remote config: {e}")
            return False
    
    def _build_remote_path(self, show_config: ShowConfig, filename: str) -> str:
        """Build the complete remote path for the file.
        
        Remote directory structure: <remote-directory>/<show>/<Album>/
        Where Album is "<show> <current_year>"
        
        Args:
            show_config: Show configuration
            filename: Target filename
            
        Returns:
            Complete remote path string
        """
        from datetime import datetime
        
        # Get current year for album name
        current_year = datetime.now().year
        album = f"{show_config.show} {current_year}"
        
        # Build path components
        base_remote = show_config.remote_directory.rstrip('/')
        show_dir = show_config.show
        album_dir = album
        
        # Escape spaces in path components for shell safety
        show_dir_escaped = show_dir.replace(' ', '\\ ')
        album_dir_escaped = album_dir.replace(' ', '\\ ')
        filename_escaped = filename.replace(' ', '\\ ')
        
        # Build complete remote path
        remote_path = f"{base_remote}/{show_dir_escaped}/{album_dir_escaped}/{filename_escaped}"
        
        return remote_path
    
    def _create_remote_directory(self, show_config: ShowConfig, filename: str) -> bool:
        """Create the remote directory structure if it doesn't exist.
        
        Args:
            show_config: Show configuration
            filename: Target filename (used to build directory path)
            
        Returns:
            True if directory creation successful or already exists, False otherwise
        """
        try:
            from datetime import datetime
            
            # Build directory path (without filename)
            current_year = datetime.now().year
            album = f"{show_config.show} {current_year}"
            
            base_remote = show_config.remote_directory.rstrip('/')
            
            # Parse remote directory to extract host and path
            if '@' in base_remote and ':' in base_remote:
                # Format: user@host:/path
                host_part = base_remote.split(':')[0]
                path_part = ':'.join(base_remote.split(':')[1:])
                
                # Build the directory structure to create
                show_dir_escaped = show_config.show.replace(' ', '\\ ')
                album_dir_escaped = album.replace(' ', '\\ ')
                target_dir = f"{path_part}/{show_dir_escaped}/{album_dir_escaped}"
                
                # Build SSH command to create directory
                ssh_cmd = self._build_ssh_command(host_part, f"mkdir -p '{target_dir}'")
                
                if ssh_cmd:
                    logger.debug(f"Creating remote directory with command: {' '.join(ssh_cmd)}")
                    result = subprocess.run(
                        ssh_cmd,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    if result.returncode != 0:
                        logger.error(f"Failed to create remote directory: {result.stderr}")
                        return False
                    
                    logger.debug("Remote directory created successfully")
                else:
                    logger.warning("Could not build SSH command for directory creation")
            else:
                # Local path - use regular mkdir
                show_dir = show_config.show
                album_dir = album
                target_dir = os.path.join(base_remote, show_dir, album_dir)
                
                os.makedirs(target_dir, exist_ok=True)
                logger.debug(f"Created local directory: {target_dir}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error creating remote directory: {e}")
            return False
    
    def _build_ssh_command(self, host: str, remote_command: str) -> Optional[list]:
        """Build SSH command for executing remote commands.
        
        Args:
            host: Remote host in format user@hostname
            remote_command: Command to execute on remote host
            
        Returns:
            SSH command as list of arguments, or None if cannot build
        """
        try:
            ssh_cmd = [
                'ssh',
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'UserKnownHostsFile=/dev/null',
                '-o', 'ConnectTimeout=30'
            ]
            
            # Add SSH key if it exists
            if os.path.exists(self.ssh_key_path):
                ssh_cmd.extend(['-i', self.ssh_key_path])
            
            # Add host and command
            ssh_cmd.extend([host, remote_command])
            
            return ssh_cmd
            
        except Exception as e:
            logger.error(f"Error building SSH command: {e}")
            return None
    
    def _execute_scp_command(self, local_path: str, remote_path: str) -> bool:
        """Execute SCP command to transfer the file.
        
        Args:
            local_path: Local file path
            remote_path: Remote destination path
            
        Returns:
            True if SCP command successful, False otherwise
        """
        try:
            # Build SCP command
            scp_cmd = [
                'scp',
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'UserKnownHostsFile=/dev/null',
                '-o', 'ConnectTimeout=30',
                '-o', 'ServerAliveInterval=10',
                '-o', 'ServerAliveCountMax=3'
            ]
            
            # Add SSH key if it exists
            if os.path.exists(self.ssh_key_path):
                scp_cmd.extend(['-i', self.ssh_key_path])
            else:
                logger.warning(f"SSH key not found at {self.ssh_key_path}, attempting without key")
            
            # Add source and destination
            scp_cmd.extend([local_path, remote_path])
            
            logger.debug(f"Executing SCP command: {' '.join(['scp'] + [arg for arg in scp_cmd[1:] if not arg.startswith('/ssh')])}")  # Hide key path in logs
            
            # Execute SCP command
            result = subprocess.run(
                scp_cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout for large files
            )
            
            if result.returncode != 0:
                logger.error(f"SCP command failed with return code {result.returncode}")
                if result.stderr:
                    logger.error(f"SCP stderr: {result.stderr}")
                if result.stdout:
                    logger.debug(f"SCP stdout: {result.stdout}")
                
                # Analyze common error patterns
                self._analyze_scp_error(result.stderr)
                return False
            
            logger.debug("SCP transfer completed successfully")
            if result.stdout:
                logger.debug(f"SCP stdout: {result.stdout}")
            
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("SCP command timed out after 10 minutes")
            return False
        except FileNotFoundError:
            logger.error("SCP command not found - ensure OpenSSH client is installed")
            return False
        except Exception as e:
            logger.error(f"Error executing SCP command: {e}")
            return False
    
    def _analyze_scp_error(self, stderr: str) -> None:
        """Analyze SCP error output and provide helpful error messages.
        
        Args:
            stderr: Standard error output from SCP command
        """
        if not stderr:
            return
        
        stderr_lower = stderr.lower()
        
        if 'permission denied' in stderr_lower:
            if 'publickey' in stderr_lower:
                logger.error("SSH authentication failed - check SSH key permissions and configuration")
            else:
                logger.error("Permission denied - check file/directory permissions on remote host")
        elif 'no such file or directory' in stderr_lower:
            logger.error("Remote path does not exist - directory creation may have failed")
        elif 'connection refused' in stderr_lower:
            logger.error("Connection refused - check if SSH service is running on remote host")
        elif 'host key verification failed' in stderr_lower:
            logger.error("Host key verification failed - this should not happen with StrictHostKeyChecking=no")
        elif 'network is unreachable' in stderr_lower or 'no route to host' in stderr_lower:
            logger.error("Network connectivity issue - check network connection to remote host")
        elif 'connection timed out' in stderr_lower:
            logger.error("Connection timed out - remote host may be unreachable or overloaded")
        else:
            logger.error(f"Unrecognized SCP error pattern: {stderr}")
    
    def get_transfer_status(self, local_path: str) -> dict:
        """Get status information about a file that may need transfer.
        
        Args:
            local_path: Path to local file
            
        Returns:
            Dictionary with file status information
        """
        status = {
            'file_exists': False,
            'file_size': 0,
            'file_readable': False,
            'file_path': local_path
        }
        
        try:
            if os.path.exists(local_path):
                status['file_exists'] = True
                status['file_size'] = os.path.getsize(local_path)
                
                try:
                    with open(local_path, 'rb') as f:
                        f.read(1)
                    status['file_readable'] = True
                except Exception:
                    status['file_readable'] = False
            
        except Exception as e:
            logger.error(f"Error getting file status for {local_path}: {e}")
        
        return status
    
    def transfer_file_with_cleanup(self, local_path: str, show_config: ShowConfig, filename: str) -> dict:
        """Transfer file with comprehensive error handling and cleanup.
        
        This method handles the complete transfer workflow:
        1. Validate local file exists
        2. Create remote directory structure
        3. Transfer file via SCP
        4. Clean up temporary files on success
        5. Retain files on failure for manual recovery
        
        Args:
            local_path: Path to the local file to transfer
            show_config: Show configuration containing remote directory info
            filename: Name for the file on the remote system
            
        Returns:
            Dictionary with transfer result details:
            {
                'success': bool,
                'message': str,
                'remote_path': str or None,
                'local_file_retained': bool
            }
        """
        result = {
            'success': False,
            'message': '',
            'remote_path': None,
            'local_file_retained': True
        }
        
        try:
            # Validate local file exists
            if not os.path.exists(local_path):
                result['message'] = f"Local file does not exist: {local_path}"
                logger.error(result['message'])
                return result
            
            # Get file size for logging
            file_size = os.path.getsize(local_path)
            logger.info(f"Starting transfer of {local_path} ({file_size} bytes)")
            
            # Build remote path
            remote_path = self._build_remote_path(show_config, filename)
            result['remote_path'] = remote_path
            
            # Attempt transfer
            transfer_success = self.transfer_file(local_path, show_config, filename)
            
            if transfer_success:
                # Transfer successful - clean up temporary file
                cleanup_success = self.cleanup_local_file(local_path)
                
                result['success'] = True
                result['local_file_retained'] = not cleanup_success
                
                if cleanup_success:
                    result['message'] = f"File successfully transferred to {remote_path} and local file cleaned up"
                    logger.info(result['message'])
                else:
                    result['message'] = f"File successfully transferred to {remote_path} but local cleanup failed"
                    logger.warning(result['message'])
            else:
                # Transfer failed - retain local file for manual recovery
                result['success'] = False
                result['local_file_retained'] = True
                result['message'] = f"Transfer failed. Local file retained at {local_path} for manual recovery"
                logger.error(result['message'])
            
            return result
            
        except Exception as e:
            result['message'] = f"Unexpected error during transfer: {e}"
            result['local_file_retained'] = True
            logger.error(result['message'])
            return result
    
    def cleanup_local_file(self, local_path: str) -> bool:
        """Clean up local temporary file after successful transfer.
        
        Args:
            local_path: Path to local file to remove
            
        Returns:
            True if cleanup successful, False otherwise
        """
        try:
            if os.path.exists(local_path):
                os.remove(local_path)
                logger.info(f"Cleaned up temporary file: {local_path}")
                return True
            else:
                logger.warning(f"File not found for cleanup: {local_path}")
                return True  # File already gone, consider it success
                
        except Exception as e:
            logger.error(f"Error cleaning up file {local_path}: {e}")
            return False
    
    def verify_transfer(self, local_path: str, show_config: ShowConfig, filename: str) -> bool:
        """Verify that a file was successfully transferred to the remote location.
        
        Args:
            local_path: Original local file path
            show_config: Show configuration
            filename: Remote filename
            
        Returns:
            True if remote file exists and has correct size, False otherwise
        """
        try:
            if not os.path.exists(local_path):
                logger.error(f"Cannot verify transfer - local file missing: {local_path}")
                return False
            
            local_size = os.path.getsize(local_path)
            remote_path = self._build_remote_path(show_config, filename)
            
            # Parse remote path to get host and file path
            base_remote = show_config.remote_directory.rstrip('/')
            
            if '@' in base_remote and ':' in base_remote:
                # Remote SCP path
                host_part = base_remote.split(':')[0]
                
                # Build command to check remote file size
                from datetime import datetime
                current_year = datetime.now().year
                album = f"{show_config.show} {current_year}"
                
                path_part = ':'.join(base_remote.split(':')[1:])
                show_dir_escaped = show_config.show.replace(' ', '\\ ')
                album_dir_escaped = album.replace(' ', '\\ ')
                filename_escaped = filename.replace(' ', '\\ ')
                
                remote_file_path = f"{path_part}/{show_dir_escaped}/{album_dir_escaped}/{filename_escaped}"
                
                # Use SSH to check file size
                ssh_cmd = self._build_ssh_command(host_part, f"stat -c%s '{remote_file_path}' 2>/dev/null || echo 'FILE_NOT_FOUND'")
                
                if ssh_cmd:
                    result = subprocess.run(
                        ssh_cmd,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    if result.returncode == 0:
                        output = result.stdout.strip()
                        if output == 'FILE_NOT_FOUND':
                            logger.error(f"Remote file not found: {remote_file_path}")
                            return False
                        
                        try:
                            remote_size = int(output)
                            if remote_size == local_size:
                                logger.info(f"Transfer verified: remote file size {remote_size} matches local size {local_size}")
                                return True
                            else:
                                logger.error(f"Transfer verification failed: remote size {remote_size} != local size {local_size}")
                                return False
                        except ValueError:
                            logger.error(f"Could not parse remote file size: {output}")
                            return False
                    else:
                        logger.error(f"Failed to check remote file: {result.stderr}")
                        return False
                else:
                    logger.error("Could not build SSH command for verification")
                    return False
            else:
                # Local path - direct file check
                if os.path.exists(remote_path):
                    remote_size = os.path.getsize(remote_path)
                    return remote_size == local_size
                else:
                    return False
                    
        except Exception as e:
            logger.error(f"Error verifying transfer: {e}")
            return False