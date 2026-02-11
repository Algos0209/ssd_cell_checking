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

from command_utils import BUILTIN_COMMANDS
from credentials_generator import generate_credentials
from ping_utils import ping_host
from scan_utils import export_scan_to_csv, scan_host


class ExecutionWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(list)

    def __init__(self, host_infos, do_builtin, do_custom, local_path, remote_path, custom_cmd, parent=None):
        super().__init__(parent)
        self.host_infos = host_infos
        self.do_builtin = do_builtin
        self.do_custom = do_custom
        self.local_path = local_path
        self.remote_path = remote_path
        self.custom_cmd = custom_cmd

    def run(self):
        print(f"[LOG] ExecutionWorker started for {len(self.host_infos)} hosts")
        print(f"[LOG] Mode - Builtin: {self.do_builtin}, Custom: {self.do_custom}")
        results = [None] * len(self.host_infos)

        def worker(idx, info):
            host = info['hostname']
            username = info['username']
            password = info['password']
            row = {'hostname': host, 'pingable': False, 'cmd_result': ''}
            print(f"[LOG] [{idx+1}/{len(self.host_infos)}] Starting worker for {host}")
            
            # Step 1: Always ping first
            print(f"[LOG] [{idx+1}] Pinging {host}...")
            try:
                pingable = ping_host(host)
                print(f"[LOG] [{idx+1}] {host} pingable: {pingable}")
            except Exception as e:
                print(f"[LOG] [{idx+1}] Ping failed for {host}: {e}")
                pingable = False
            
            row['pingable'] = pingable
            if not pingable:
                row['cmd_result'] = 'Unreachable'
                print(f"[LOG] [{idx+1}] {host} unreachable, skipping")
                return idx, row
            
            # Step 2: Execute built-in command (copy) if requested
            if self.do_builtin:
                print(f"[LOG] [{idx+1}] Executing built-in {self.builtin_cmd} command for {host}")
                try:
                    command_func = BUILTIN_COMMANDS.get(self.builtin_cmd)
                    if command_func:
                        results = command_func(host, username, password, self.local_path, self.remote_path)
                        print(f"[LOG] [{idx+1}] Built-in {self.builtin_cmd} command completed for {host}")
                    else:
                        results = f'Unknown built-in command: {self.builtin_cmd}'
                        print(f"[LOG] [{idx+1}] Unknown built-in command for {host}")
                except Exception as e:
                    results = f'Execute failed: {e}'
                    print(f"[LOG] [{idx+1}] Execute exception for {host}: {e}")
            
            # Step 3: Execute custom command if requested
            custom_result = None
            if self.do_custom:
                print(f"[LOG] [{idx+1}] Executing custom command for {host}")
                ssh = None
                try:
                    ssh = paramiko.SSHClient()
                    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    ssh.connect(host, username=username, password=password, timeout=5)
                    print(f"[LOG] [{idx+1}] SSH connected to {host}")
                    cmds = [c.strip() for c in self.custom_cmd.split('&&') if c.strip()]
                    cmd_results = []
                    for cmd in cmds:
                        print(f"[LOG] [{idx+1}] Running command on {host}: {cmd}")
                        stdin, stdout, stderr = ssh.exec_command(cmd)
                        cmd_out = stdout.read().decode(errors='replace').strip()
                        cmd_err = stderr.read().decode(errors='replace').strip()
                        if cmd_err:
                            cmd_results.append(f'ERR: {cmd_err}')
                        else:
                            cmd_results.append(cmd_out)
                    custom_result = '\n'.join(cmd_results)
                    print(f"[LOG] [{idx+1}] Custom command completed for {host}")
                except Exception as e:
                    custom_result = f'SSH ERR: {e}'
                    print(f"[LOG] [{idx+1}] SSH exception for {host}: {e}")
                finally:
                    if ssh is not None:
                        try:
                            ssh.close()
                        except Exception:
                            pass
            
            # Combine results based on mode
            if self.do_builtin and self.do_custom:
                row['cmd_result'] = f'{results}\n---\n{custom_result}'
            elif self.do_builtin:
                row['cmd_result'] = results
            elif self.do_custom:
                row['cmd_result'] = custom_result
            
            print(f"[LOG] [{idx+1}] Worker completed for {host}")
            return idx, row

        # Run all workers in parallel with ThreadPoolExecutor
        print(f"[LOG] Starting ThreadPoolExecutor with 30 workers")
        with ThreadPoolExecutor(max_workers=30) as executor:
            futures = [executor.submit(worker, idx, info) for idx, info in enumerate(self.host_infos)]
            print(f"[LOG] Submitted {len(futures)} tasks to executor")
            for i, future in enumerate(as_completed(futures), 1):
                idx, row = future.result()
                results[idx] = row
                print(f"[LOG] Progress: {i}/{len(self.host_infos)} completed")
                self.progress.emit(i)

        print(f"[LOG] All workers completed, emitting finished signal")
        self.finished.emit(results)


class ScanWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(list)

    def __init__(self, host_infos, parent=None):
        super().__init__(parent)
        self.host_infos = host_infos

    def run(self):
        print(f"[LOG] ScanWorker started for {len(self.host_infos)} hosts")
        results = [None] * len(self.host_infos)

        def worker(idx, info):
            host = info['hostname']
            username = info['username']
            password = info['password']
            print(f"[LOG] [{idx+1}/{len(self.host_infos)}] Scanning {host}...")
            
            result = scan_host(host, username, password)
            print(f"[LOG] [{idx+1}] Scan completed for {host}")
            return idx, result

        # Run all workers in parallel with ThreadPoolExecutor
        print(f"[LOG] Starting ThreadPoolExecutor for scan with 30 workers")
        with ThreadPoolExecutor(max_workers=30) as executor:
            futures = [executor.submit(worker, idx, info) for idx, info in enumerate(self.host_infos)]
            print(f"[LOG] Submitted {len(futures)} scan tasks to executor")
            for i, future in enumerate(as_completed(futures), 1):
                idx, result = future.result()
                results[idx] = result
                print(f"[LOG] Scan progress: {i}/{len(self.host_infos)} completed")
                self.progress.emit(i)

        print(f"[LOG] All scan workers completed, emitting finished signal")
        self.finished.emit(results)


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
    # Combo box logic for built-in command 'copy'
    def on_command_changed():
        cmd = window.command_combo.currentText().strip().lower()
        window.path_from_edit.clear()
        window.path_dest_edit.clear()
        window.cmd_prompt.clear()
        if cmd == 'copy':
            window.path_from_edit.show()
            window.path_dest_edit.show()
            window.browse.show()
            window.file_folder.show()
            window.label_7.show()
            window.label_8.show()
        else:
            window.path_from_edit.hide()
            window.path_dest_edit.hide()
            window.browse.hide()
            window.file_folder.hide()
            window.label_7.hide()
            window.label_8.hide()
    window.command_combo.currentIndexChanged.connect(on_command_changed)
    # Initial state
    on_command_changed()

    # Browse button logic
    def on_browse():
        option = window.file_folder.currentText().strip().lower() if hasattr(window, 'file_folder') else 'file'
        if option == 'folder':
            folder = QtWidgets.QFileDialog.getExistingDirectory(window, 'Select Folder')
            if folder:
                window.path_from_edit.setText(folder)
        else:
            file, _ = QtWidgets.QFileDialog.getOpenFileName(window, 'Select File')
            if file:
                window.path_from_edit.setText(file)
    window.browse.clicked.connect(on_browse)

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
        print("[LOG] Execute button clicked")
        # Clear the result table immediately
        empty_model = QStandardItemModel()
        empty_model.setHorizontalHeaderLabels(['hostname', 'pingable', 'cmd_result'])
        window.result_table.setModel(empty_model)
        host_infos = []
        if window.range_radio.isChecked():
            print("[LOG] Range radio selected")
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

        combo_cmd = window.command_combo.currentText().strip().lower()
        custom_cmd = window.cmd_prompt.text().strip()
        do_builtin = combo_cmd in BUILTIN_COMMANDS
        do_custom = bool(custom_cmd)

        # If neither, error
        if not do_builtin and not do_custom:
            show_error('Please provide a built-in command, a custom command, or both!')
            return

        # Validate built-in parameters if needed
        local_path = ''
        remote_path = ''
        if do_builtin:
            local_path = window.path_from_edit.text().strip() if hasattr(window, 'path_from_edit') else ''
            remote_path = window.path_dest_edit.text().strip() if hasattr(window, 'path_dest_edit') else ''
            if not local_path:
                show_error('Source path cannot be empty!', [window.path_from_edit] if hasattr(window, 'path_from_edit') else None)
                return
            if not remote_path:
                remote_path = r'C:\sthi'
                if hasattr(window, 'path_dest_edit'):
                    window.path_dest_edit.setText(remote_path)

        # Set up progress bar
        window.progressBar.setMinimum(0)
        window.progressBar.setMaximum(len(host_infos))
        window.progressBar.setValue(0)

        # Create and start the execution worker thread
        def update_progress(val):
            print(f"[LOG] Progress update: {val}/{len(host_infos)}")
            window.progressBar.setValue(val)

        def on_finished(results):
            print(f"[LOG] Execution finished, displaying {len(results)} results")
            # Display results in result_table
            df = pd.DataFrame(results)
            df = df.sort_values(by=['pingable', 'hostname'], ascending=[False, True])
            model = QStandardItemModel()
            model.setHorizontalHeaderLabels(['hostname', 'pingable', 'cmd_result'])
            for _, row in df.iterrows():
                hostname_item = QStandardItem(str(row['hostname']))
                pingable_item = QStandardItem('Yes' if row['pingable'] else 'No')
                cmd_result_item = QStandardItem(str(row['cmd_result']))
                model.appendRow([hostname_item, pingable_item, cmd_result_item])
            window.result_table.setModel(model)
            header = window.result_table.horizontalHeader()
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
            window.progressBar.setValue(len(host_infos))
            print("[LOG] Results displayed in table")

        print(f"[LOG] Creating ExecutionWorker with {len(host_infos)} hosts")
        window.execution_worker = ExecutionWorker(host_infos, do_builtin, do_custom, local_path, remote_path, custom_cmd)
        window.execution_worker.builtin_cmd = combo_cmd
        window.execution_worker.progress.connect(update_progress)
        window.execution_worker.finished.connect(on_finished)
        print("[LOG] Starting ExecutionWorker thread")
        window.execution_worker.start()
        print("[LOG] ExecutionWorker thread started, returning from on_execute")

    window.execute.clicked.connect(on_execute)


def handle_scan(window):
    def show_error(message, clear_fields=None):
        QtWidgets.QMessageBox.critical(window, 'Input Error', message)
        if clear_fields:
            for field in clear_fields:
                field.clear()

    def on_scan():
        print("[LOG] Scan button clicked")
        # Clear the result table immediately
        empty_model = QStandardItemModel()
        empty_model.setHorizontalHeaderLabels(['hostname', 'pingable', 'scan_result'])
        window.result_table.setModel(empty_model)
        
        host_infos = []
        if window.range_radio.isChecked():
            print("[LOG] Range radio selected for scan")
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

        # Set up progress bar
        window.progressBar.setMinimum(0)
        window.progressBar.setMaximum(len(host_infos))
        window.progressBar.setValue(0)

        # Create and start the scan worker thread
        def update_progress(val):
            print(f"[LOG] Scan progress update: {val}/{len(host_infos)}")
            window.progressBar.setValue(val)

        def on_finished(results):
            print(f"[LOG] Scan finished, displaying {len(results)} results")
            
            # Automatically export to CSV
            csv_path = export_scan_to_csv(results)
            if csv_path:
                print(f"[LOG] Scan results exported to {csv_path}")
                QtWidgets.QMessageBox.information(window, 'Scan Complete', 
                                                 f'Scan complete! Results saved to:\n{csv_path}')
            else:
                print("[LOG] Failed to export scan results to CSV")
                QtWidgets.QMessageBox.warning(window, 'Export Warning', 
                                             'Scan complete but failed to save CSV file.')
            
            # Display results in result_table
            df = pd.DataFrame(results)
            df = df.sort_values(by=['pingable', 'hostname'], ascending=[False, True])
            model = QStandardItemModel()
            model.setHorizontalHeaderLabels(['hostname', 'pingable', 'scan_result'])
            for _, row in df.iterrows():
                hostname_item = QStandardItem(str(row['hostname']))
                pingable_item = QStandardItem('Yes' if row['pingable'] else 'No')
                scan_result_item = QStandardItem(str(row['scan_result']))
                model.appendRow([hostname_item, pingable_item, scan_result_item])
            window.result_table.setModel(model)
            header = window.result_table.horizontalHeader()
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
            window.progressBar.setValue(len(host_infos))
            print("[LOG] Scan results displayed in table")

        print(f"[LOG] Creating ScanWorker with {len(host_infos)} hosts")
        window.scan_worker = ScanWorker(host_infos)
        window.scan_worker.progress.connect(update_progress)
        window.scan_worker.finished.connect(on_finished)
        print("[LOG] Starting ScanWorker thread")
        window.scan_worker.start()
        print("[LOG] ScanWorker thread started, returning from on_scan")

    window.execute_2.clicked.connect(on_scan)


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = uic.loadUi("ui.ui")
    # Set up result_table with headers so they are always visible
    empty_model = QStandardItemModel()
    empty_model.setHorizontalHeaderLabels(['hostname', 'pingable', 'cmd_result'])
    window.result_table.setModel(empty_model)
    header = window.result_table.horizontalHeader()
    header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)  # hostname
    header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)  # pingable
    header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)  # cmd_result
    setup_validators(window)
    handle_radio_buttons(window)
    handle_execute(window)
    handle_scan(window)
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
	main()
