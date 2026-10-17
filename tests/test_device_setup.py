from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
import common
from device_setup import selection_config, save_selection


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.first = {'id': 'AABBCCDDEE01', 'name': 'HomePod', 'pair_id': 'one',
                      'address': '192.0.2.10', 'secret': 'must-not-be-saved'}
        self.second = {'id': 'AABBCCDDEE02', 'name': 'HomePod', 'pair_id': 'one'}

    def test_only_explicit_nonsecret_fields_are_persisted(self):
        result = selection_config(self.first, self.second)
        self.assertEqual(result, {'devices': [
            {'id': 'AABBCCDDEE01', 'name': 'HomePod'},
            {'id': 'AABBCCDDEE02', 'name': 'HomePod'}], 'preferred_receiver': ''})

    def test_same_receiver_rejected(self):
        with self.assertRaises(ValueError): selection_config(self.first, self.first)

    def test_different_stereo_pair_rejected(self):
        self.second['pair_id'] = 'two'
        with self.assertRaises(ValueError): selection_config(self.first, self.second)

    def test_verified_preference_preserved_only_for_selected_pair(self):
        self.assertEqual(selection_config(self.first, self.second, 'AA:BB:CC:DD:EE:02')['preferred_receiver'], 'AABBCCDDEE02')
        self.assertEqual(selection_config(self.first, self.second, 'AABBCCDDEE99')['preferred_receiver'], '')

    def test_save_backs_up_existing_config_without_touching_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            common.write_json(folder/'config.json', {'old': True})
            common.write_json(folder/'settings.json', {'volume': 17})
            save_selection(folder, self.first, self.second)
            backups = list(folder.glob('config.backup.*.json'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(common.read_json(backups[0]), {'old': True})
            self.assertEqual(common.read_json(folder/'settings.json'), {'volume': 17})
            old_known, old_preferred = common.KNOWN, common.PREFERRED
            try:common.configure_devices(folder)
            finally:common.KNOWN, common.PREFERRED = old_known, old_preferred


if __name__ == '__main__': unittest.main()
