from ssh_copy import ssh_copy


def execute_copy_command(hostname, username, password, local_path, remote_path):
    return ssh_copy(hostname, username, password, local_path, remote_path)

BUILTIN_COMMANDS = {
    "ssh_copy": execute_copy_command,
}