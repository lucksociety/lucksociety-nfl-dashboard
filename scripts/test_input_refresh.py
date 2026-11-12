import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from datetime import datetime, timezone

spec = importlib.util.spec_from_file_location('refresh', Path(__file__).with_name('update_data.py'))
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)
from season import generated_et

class InputRefreshTests(unittest.TestCase):
    def test_eastern_dst(self):
        self.assertEqual(generated_et(datetime(2026, 11, 12, 20, tzinfo=timezone.utc)), '2026-11-12 15:00')
        self.assertEqual(generated_et(datetime(2026, 7, 12, 20, tzinfo=timezone.utc)), '2026-07-12 16:00')

    def test_failed_rebuild_removes_previous_success_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'refresh.json'
            output.write_text('{"live_download":true}')
            with patch.object(refresh.sys, 'argv', ['update_data.py', '--manifest', str(output)]), patch.object(refresh, 'fetch', side_effect=RuntimeError('source unavailable')):
                with self.assertRaisesRegex(RuntimeError, 'source unavailable'): refresh.main()
            self.assertFalse(output.exists(), 'failed download cannot reuse previous success')

    def test_export_changes_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            original = refresh.ROOT
            refresh.ROOT = directory
            try:
                data = Path(directory) / 'data'; (data / 'weeks').mkdir(parents=True)
                index = data / 'index.json'; week = data / 'weeks/2026_w10.json'
                index.write_text(json.dumps({'generated_et':'old', 'data_through':{'week':9}}))
                week.write_text('{"model":{"beta":[20,1]}}')
                before = refresh.exported_inputs()
                index.write_text(json.dumps({'generated_et':'new', 'data_through':{'week':9}}))
                self.assertEqual(before, refresh.exported_inputs(), 'timestamps do not fake new numerical inputs')
                week.write_text('{"model":{"beta":[23,1]}}')
                self.assertNotEqual(before, refresh.exported_inputs())
                output = Path(directory) / 'out/refresh.json'
                refresh.write_manifest(output, datetime.now(timezone.utc).isoformat(), before, False)
                manifest = json.loads(output.read_text())
                self.assertFalse(manifest['live_download'], 'offline rebuild must not claim fresh sources')
                self.assertTrue(manifest['inputs_changed'])
                self.assertEqual(set(manifest['files']), {'data/index.json','data/weeks/2026_w10.json'})
            finally:
                refresh.ROOT = original

if __name__ == '__main__': unittest.main()
