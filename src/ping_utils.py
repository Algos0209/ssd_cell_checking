import platform
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed


def ping_host(hostname, timeout=1):
    """Ping a single host, return True if pingable, else False."""
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    try:
        result = subprocess.run([
            'ping', param, '1', '-w', str(timeout * 1000), hostname
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode == 0
    except Exception:
        return False