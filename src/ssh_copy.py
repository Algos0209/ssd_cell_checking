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
    ssh = None
    sftp = None
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname, username=username, password=password, timeout=10)
        sftp = ssh.open_sftp()
        if os.path.isfile(local_path):
            # Copy single file
            remote_file = os.path.join(remote_path, os.path.basename(local_path))
            sftp.put(local_path, remote_file)
            result = f'File copied to {remote_file}'
        elif os.path.isdir(local_path):
            # Recursively copy folder
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
        else:
            result = 'Local path does not exist.'
        return result
    except Exception as e:
        return f'Copy failed: {e}'
    finally:
        if sftp is not None:
            try:
                sftp.close()
            except Exception:
                pass
        if ssh is not None:
            try:
                ssh.close()
            except Exception:
                pass
