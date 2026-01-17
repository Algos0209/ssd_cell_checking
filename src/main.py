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

from credentials_generator import generate_credentials
from ssh_copy import ssh_copy


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

        combo_cmd = window.command_combo.currentText().strip().lower()
        custom_cmd = window.cmd_prompt.text().strip()
        do_builtin = combo_cmd == 'copy'
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

        from ping_utils import ping_host
        results = [None] * len(host_infos)

        # Worker function for each host - handles all 3 modes
        def worker(idx, info):
            host = info['hostname']
            username = info['username']
            password = info['password']
            row = {'hostname': host, 'pingable': False, 'cmd_result': ''}
            
            # Step 1: Always ping first
            try:
                pingable = ping_host(host)
            except Exception:
                pingable = False
            
            row['pingable'] = pingable
            if not pingable:
                row['cmd_result'] = 'Unreachable'
                return idx, row
            
            # Step 2: Execute built-in command (copy) if requested
            copy_result = None
            if do_builtin:
                try:
                    copy_result = ssh_copy(host, username, password, local_path, remote_path)
                except Exception as e:
                    copy_result = f'Copy failed: {e}'
            
            # Step 3: Execute custom command if requested
            custom_result = None
            if do_custom:
                ssh = None
                try:
                    ssh = paramiko.SSHClient()
                    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    ssh.connect(host, username=username, password=password, timeout=5)
                    cmds = [c.strip() for c in custom_cmd.split('&&') if c.strip()]
                    cmd_results = []
                    for cmd in cmds:
                        stdin, stdout, stderr = ssh.exec_command(cmd)
                        cmd_out = stdout.read().decode(errors='replace').strip()
                        cmd_err = stderr.read().decode(errors='replace').strip()
                        if cmd_err:
                            cmd_results.append(f'ERR: {cmd_err}')
                        else:
                            cmd_results.append(cmd_out)
                    custom_result = '\n'.join(cmd_results)
                except Exception as e:
                    custom_result = f'SSH ERR: {e}'
                finally:
                    if ssh is not None:
                        try:
                            ssh.close()
                        except Exception:
                            pass
            
            # Combine results based on mode
            if do_builtin and do_custom:
                row['cmd_result'] = f'{copy_result}\n---\n{custom_result}'
            elif do_builtin:
                row['cmd_result'] = copy_result
            elif do_custom:
                row['cmd_result'] = custom_result
            
            return idx, row

        # Run all workers in parallel with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=30) as executor:
            futures = [executor.submit(worker, idx, info) for idx, info in enumerate(host_infos)]
            for i, future in enumerate(as_completed(futures), 1):
                idx, row = future.result()
                results[idx] = row
                window.progressBar.setValue(i)

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
        return

    window.execute.clicked.connect(on_execute)

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
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
	main()
