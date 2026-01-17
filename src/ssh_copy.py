import os

import paramiko


def ssh_copy(hostname, username, password, local_path, remote_path):
    """
    Copy a file or folder to a remote host via SSH using paramiko SFTP.
    :param hostname: str, remote host
    :param username: str, SSH username
    :param password: str, SSH password
    :param local_path: str, local file or folder path
    :param remote_path: str, remote destination path
    :return: str, result message
    """
    print(f"[ssh_copy] Starting copy to {hostname}")
    ssh = None
    sftp = None
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        print(f"[ssh_copy] Connecting to {hostname}...")
        ssh.connect(hostname, username=username, password=password, timeout=10, banner_timeout=10, auth_timeout=10)
        print(f"[ssh_copy] Connected to {hostname}, opening SFTP...")
        sftp = ssh.open_sftp()
        print(f"[ssh_copy] SFTP opened for {hostname}")
        
        # Ensure remote path exists using SSH command instead of SFTP
        print(f"[ssh_copy] Creating remote directory {remote_path} on {hostname} via SSH command")
        try:
            # Use mkdir command with /p flag to create parent directories if needed
            mkdir_cmd = f'mkdir "{remote_path}" 2>nul || cd .'
            print(f"[ssh_copy] Running command: {mkdir_cmd}")
            stdin, stdout, stderr = ssh.exec_command(mkdir_cmd, timeout=5)
            stdout.read()  # Wait for command to complete
            stderr.read()
            print(f"[ssh_copy] Directory creation command completed for {hostname}")
        except Exception as e:
            print(f"[ssh_copy] Failed to create directory via SSH command: {e}")
            # Continue anyway, directory might already exist
        
        print(f"[ssh_copy] Remote directory ensured for {hostname}")
        
        if os.path.isfile(local_path):
            # Copy single file
            print(f"[ssh_copy] Copying single file to {hostname}")
            remote_file = os.path.join(remote_path, os.path.basename(local_path))
            sftp.put(local_path, remote_file)
            result = f'File copied to {remote_file}'
            print(f"[ssh_copy] File copy completed for {hostname}")
        elif os.path.isdir(local_path):
            # Recursively copy folder
            print(f"[ssh_copy] Copying folder to {hostname}")
            def recursive_upload(local_dir, remote_dir):
                try:
                    sftp.mkdir(remote_dir)
                except IOError:
                    pass  # Directory may already exist
                for item in os.listdir(local_dir):
                    local_item = os.path.join(local_dir, item)
                    remote_item = os.path.join(remote_dir, item)
                    if os.path.isdir(local_item):
                        recursive_upload(local_item, remote_item)
                    else:
                        sftp.put(local_item, remote_item)
            recursive_upload(local_path, remote_path)
            result = f'Folder copied to {remote_path}'
            print(f"[ssh_copy] Folder copy completed for {hostname}")
        else:
            result = 'Local path does not exist.'
            print(f"[ssh_copy] Local path does not exist for {hostname}")
        return result
    except Exception as e:
        print(f"[ssh_copy] Exception for {hostname}: {e}")
        return f'Copy failed: {e}'
    finally:
        print(f"[ssh_copy] Cleanup for {hostname}")
        if sftp is not None:
            try:
                sftp.close()
                print(f"[ssh_copy] SFTP closed for {hostname}")
            except Exception as e:
                print(f"[ssh_copy] Error closing SFTP for {hostname}: {e}")
        if ssh is not None:
            try:
                ssh.close()
                print(f"[ssh_copy] SSH closed for {hostname}")
            except Exception as e:
                print(f"[ssh_copy] Error closing SSH for {hostname}: {e}")
