"""
Scan utilities for pinging and SSH connectivity testing
"""
import csv
from datetime import datetime

import paramiko

from ping_utils import ping_host


def scan_host(hostname, username, password):
    """
    Scan a single host: ping and execute 'echo hello {hostname}' via SSH
    
    Args:
        hostname: The host to scan
        username: SSH username
        password: SSH password
    
    Returns:
        dict: Result containing hostname, username, password, pingable status, and scan result
    """
    result = {
        'hostname': hostname,
        'username': username,
        'password': password,
        'pingable': False,
        'scan_result': ''
    }
    
    # Step 1: Ping the host
    try:
        pingable = ping_host(hostname)
        result['pingable'] = pingable
    except Exception as e:
        result['scan_result'] = f'Ping error: {e}'
        return result
    
    if not pingable:
        result['scan_result'] = 'Unreachable'
        return result
    
    # Step 2: SSH and execute echo command
    ssh = None
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname, username=username, password=password, timeout=5)
        
        # Execute echo command
        cmd = f'echo hello {hostname}'
        stdin, stdout, stderr = ssh.exec_command(cmd)
        output = stdout.read().decode(errors='replace').strip()
        error = stderr.read().decode(errors='replace').strip()
        
        if error:
            result['scan_result'] = f'Error: {error}'
        else:
            result['scan_result'] = output
            
    except Exception as e:
        result['scan_result'] = f'SSH Error: {e}'
    finally:
        if ssh is not None:
            try:
                ssh.close()
            except Exception:
                pass
    
    return result


def export_scan_to_csv(scan_results):
    """
    Automatically export scan results to CSV file with timestamp
    
    Args:
        scan_results: List of dicts with keys: hostname, username, password, pingable, scan_result
    
    Returns:
        str: Filepath of the generated CSV, or None if failed
    """
    try:
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = f'scan_results_{timestamp}.csv'
        
        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            # Write headers
            writer.writerow(['host', 'username', 'password', 'pingable', 'ssh_able'])
            
            # Write data rows
            for result in scan_results:
                host = result.get('hostname', '')
                username = result.get('username', '')
                password = result.get('password', '')
                pingable = 'Yes' if result.get('pingable', False) else 'No'
                
                # Determine if SSH was successful
                scan_result = result.get('scan_result', '')
                ssh_able = 'Yes' if (result.get('pingable', False) and 
                                    scan_result and 
                                    not scan_result.startswith('SSH Error:') and
                                    not scan_result.startswith('Error:') and
                                    scan_result != 'Unreachable') else 'No'
                
                writer.writerow([host, username, password, pingable, ssh_able])
        
        return filepath
    except Exception as e:
        print(f"Error exporting to CSV: {e}")
        return None
