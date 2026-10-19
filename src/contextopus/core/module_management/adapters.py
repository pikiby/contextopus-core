"""Durable, explicit selection of folder replacements for compatibility adapters."""

import json


class AdapterReplacement:
    def _read_state(self):
        state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        self.adapters.update(module for module, record in state.items()
                             if 'adapter_selection' in record and module not in self.reserved)
        return state

    def _folder_selected(self, module, state=None):
        record = (self.state if state is None else state).get(module, {})
        selection = record.get('adapter_selection')
        # Older Core could install a folder before the legacy executable appeared.
        return selection == 'folder' or (selection is None and bool(record.get('prepared')))

    def _adapter_pending(self, module):
        record = self.state.get(module, {})
        return module in self.adapters and record.get('adapter_selection') == 'pending' and record.get('enabled')

    def _restore_adapter(self, module):
        if module in self.app.registry.compatibility_adapters and not self._folder_selected(module):
            self.app.registry.restore_compatibility_adapter(module)

    def _reconcile_adapters(self):
        for module in self.adapters:
            if module in self.loaded:
                continue
            if self._folder_selected(module):
                self.app.registry.replace_owned(module, [])
                self.app.registry.modules.pop(module, None)
            else:
                self._restore_adapter(module)
            error = self.state.get(module, {}).get('activation_error')
            if error:
                self.errors[module] = error

    def _adapter_failed(self, module, error):
        # _save may raise after its atomic replace. Disk, rather than the failed
        # caller's in-memory flag, decides whether returning to legacy is legal.
        self.state = self._read_state()
        try:
            self.runtime.stop(module)
        except Exception as cleanup_error:
            error.add_note('Candidate cleanup failed: ' + str(cleanup_error))
        record = self.state.setdefault(module, {})
        record['enabled'] = False
        record['activation_error'] = str(error)
        try:
            self._save()
        except Exception as save_error:
            error.add_note('Activation failure state could not be saved: ' + str(save_error))
        finally:
            self.state = self._read_state()
            self._unpublish(module)
            self.errors[module] = str(error)

    def _enable_replacement(self, module):
        try:
            manifest, specs = self._activation(module)
            record = self.state.setdefault(module, {})
            record.pop('activation_error', None)
            if 'service' in manifest and not self.app.resources.services_started:
                record.update(enabled=True, adapter_selection='pending')
                self._save()
                self.errors.pop(module, None)
                self._restore_adapter(module)
                return {'id': module, 'state': 'activation_pending'}
            if 'service' in manifest:
                self.runtime.stop(module)
                self._start_service(module, manifest)
            record.update(enabled=True, adapter_selection='folder')
            self._save()
            self._publish_activation(module, manifest, specs)
            return {'id': module, 'state': 'enabled'}
        except Exception as error:
            self._adapter_failed(module, error)
            raise

    def _disable_replacement(self, module):
        self._directory(module)
        self.state.setdefault(module, {}).update(enabled=False, adapter_selection='folder')
        self.state[module].pop('activation_error', None)
        self._save()
        self.runtime.stop(module)
        self.errors.pop(module, None)
        self._unpublish(module)
        return {'id': module, 'state': 'prepared'}
