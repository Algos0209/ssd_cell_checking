# Import necessary modules
import sys

# Worker for threaded pinging with progress updates
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import paramiko
from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import QRegExp, QThread, pyqtSignal
from PyQt5.QtGui import (
    QIntValidator,
    QRegExpValidator,
    QStandardItem,
    QStandardItemModel,
)

from src.credentials_generator import generate_credentials


class PingWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(list)

    def __init__(self, host_infos, cmd, parent=None, max_threads=30):
        super().__init__(parent)
        self.host_infos = host_infos  # list of dicts: {hostname, username, password}
        self.cmd = cmd
        self.max_threads = max_threads
        self._is_running = True

    def run(self):
        from src.ping_utils import ping_host
        results = []
        completed = 0
        def ping_and_ssh(info):
            host = info['hostname']
            username = info['username']
            password = info['password']
            row = {'hostname': host, 'pingable': False, 'cmd_result': ''}
            if not self._is_running:
                return row
            try:
                pingable = ping_host(host)
            except Exception:
                pingable = False
            row['pingable'] = pingable
            if pingable:
                try:
                    ssh = paramiko.SSHClient()
                    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    ssh.connect(host, username=username, password=password, timeout=5)
                    stdin, stdout, stderr = ssh.exec_command(self.cmd)
                    cmd_out = stdout.read().decode(errors='replace').strip()
                    cmd_err = stderr.read().decode(errors='replace').strip()
                    ssh.close()
                    if cmd_err:
                        row['cmd_result'] = f'ERR: {cmd_err}'
                    else:
                        row['cmd_result'] = cmd_out
                except Exception as e:
                    row['cmd_result'] = f'SSH ERR: {e}'
            else:
                row['cmd_result'] = 'Unreachable'
            return row

        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            future_to_info = {executor.submit(ping_and_ssh, info): info for info in self.host_infos}
            for future in as_completed(future_to_info):
                if not self._is_running:
                    break
                row = future.result()
                results.append(row)
                completed += 1
                self.progress.emit(completed)
        self.finished.emit(results)

    def stop(self):
        self._is_running = False


def setup_validators(window):
	# Only allow integers in range_from and range_to
	int_validator = QIntValidator()
	window.range_from.setValidator(int_validator)
	window.range_to.setValidator(int_validator)

	# Allow only comma-separated numbers (with optional spaces) in list_edit
	regex = QRegExp(r'\s*-?\d+(\s*,\s*-?\d+)*\s*')
	reg_validator = QRegExpValidator(regex)
	window.list_edit.setValidator(reg_validator)

def handle_radio_buttons(window):
	def update_elements():
		if window.range_radio.isChecked():
			window.range_from.setEnabled(True)
			window.range_to.setEnabled(True)
			window.list_edit.setEnabled(False)
		else:
			window.range_from.setEnabled(False)
			window.range_to.setEnabled(False)
			window.list_edit.setEnabled(True)

	window.range_radio.toggled.connect(update_elements)
	window.list_radio.toggled.connect(update_elements)
	# Initial state
	update_elements()


def handle_execute(window):
    # Connect the export button to export the table to CSV
    def on_export():
        model = window.result_table.model()
        if model is None or model.rowCount() == 0:
            QtWidgets.QMessageBox.information(window, 'Export', 'No data to export.')
            return
        # Prompt for file path
        path, _ = QtWidgets.QFileDialog.getSaveFileName(window, 'Save CSV', '', 'CSV Files (*.csv)')
        if not path:
            return
        # Write to CSV
        with open(path, 'w', encoding='utf-8', newline='') as f:
            import csv
            writer = csv.writer(f)
            # Write headers
            headers = [model.headerData(i, 1) for i in range(model.columnCount())]
            writer.writerow(headers)
            # Write data rows
            for row in range(model.rowCount()):
                rowdata = [model.data(model.index(row, col)) for col in range(model.columnCount())]
                writer.writerow(rowdata)
        QtWidgets.QMessageBox.information(window, 'Export', f'Exported to {path}')
        window.export.clicked.connect(on_export)

    # Connect the clear button to clear the table
    def on_clear():
        empty_model = QStandardItemModel()
        empty_model.setHorizontalHeaderLabels(['hostname', 'pingable', 'cmd_result'])
        window.result_table.setModel(empty_model)
    window.clear.clicked.connect(on_clear)

    def show_error(message, clear_fields=None):
        QtWidgets.QMessageBox.critical(window, 'Input Error', message)
        if clear_fields:
            for field in clear_fields:
                field.clear()

    def on_execute():
        # Clear the result table immediately
        empty_model = QStandardItemModel()
        empty_model.setHorizontalHeaderLabels(['hostname', 'pingable', 'cmd_result'])
        window.result_table.setModel(empty_model)
        host_infos = []
        if window.range_radio.isChecked():
            from_text = window.range_from.text().strip()
            to_text = window.range_to.text().strip()
            clear = []
            if not from_text:
                clear.append(window.range_from)
            if not to_text:
                clear.append(window.range_to)
            if clear:
                show_error('Range fields cannot be empty!', clear)
                return
            start = int(from_text)
            end = int(to_text)
            if start > end:
                show_error('From value must be less than or equal to To value!', [window.range_from, window.range_to])
                return
            for n in range(start, end + 1):
                hostname, username, password = generate_credentials(n)
                host_infos.append({'hostname': hostname, 'username': username, 'password': password})
        elif window.list_radio.isChecked():
            list_text = window.list_edit.text().strip()
            if not list_text:
                show_error('List field cannot be empty!', [window.list_edit])
                return
            items = [item.strip() for item in list_text.split(',') if item.strip()]
            if not items:
                show_error('List must contain at least one number!', [window.list_edit])
                return
            for item in items:
                hostname, username, password = generate_credentials(item)
                host_infos.append({'hostname': hostname, 'username': username, 'password': password})
        else:
            show_error('No radio button selected!')
            return

        # Get command to execute
        cmd = window.cmd_prompt.text().strip()
        if not cmd:
            show_error('Command to execute cannot be empty!', [window.cmd_prompt])
            return

        # Set up progress bar
        window.progressBar.setMinimum(0)
        window.progressBar.setMaximum(len(host_infos))
        window.progressBar.setValue(0)

        # Start ping worker thread
        def update_progress(val):
            window.progressBar.setValue(val)

        def on_finished(results):
            # Sort results: pingable True first, then hostname alphabetically
            df = pd.DataFrame(results)
            df['pingable'] = df['pingable'].astype(bool)
            df = df.sort_values(by=['pingable', 'hostname'], ascending=[False, True])

            # Display results in result_table
            model = QStandardItemModel()
            model.setHorizontalHeaderLabels(['hostname', 'pingable', 'cmd_result'])
            for _, row in df.iterrows():
                hostname_item = QStandardItem(str(row['hostname']))
                pingable_item = QStandardItem('Yes' if row['pingable'] else 'No')
                cmd_result_item = QStandardItem(str(row['cmd_result']))
                model.appendRow([hostname_item, pingable_item, cmd_result_item])
            window.result_table.setModel(model)
            window.progressBar.setValue(len(host_infos))

        window.ping_worker = PingWorker(host_infos, cmd)
        window.ping_worker.progress.connect(update_progress)
        window.ping_worker.finished.connect(on_finished)
        window.ping_worker.start()

    window.execute.clicked.connect(on_execute)

def main():
    app = QtWidgets.QApplication(sys.argv)
    window = uic.loadUi("ui.ui")
    # Set up result_table with headers so they are always visible
    empty_model = QStandardItemModel()
    empty_model.setHorizontalHeaderLabels(['hostname', 'pingable'])
    window.result_table.setModel(empty_model)
    setup_validators(window)
    handle_radio_buttons(window)
    handle_execute(window)
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
	main()
