import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import common


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name)
        self.old_known, self.old_preferred = common.KNOWN, common.PREFERRED
        self.config = {'devices': [
            {'id': 'AA:BB:CC:DD:EE:01', 'name': 'Left'},
            {'id': 'AABBCCDDEE02', 'name': 'Right'}]}

    def tearDown(self):
        common.KNOWN, common.PREFERRED = self.old_known, self.old_preferred
        self.temporary.cleanup()

    def save(self):
        common.write_json(self.folder/'config.json', self.config)

    def test_explicit_configuration_required(self):
        with self.assertRaises(ValueError):
            common.configure_devices(self.folder)

    def test_colon_ids_normalized_and_default_uses_leader(self):
        self.save(); common.configure_devices(self.folder)
        self.assertEqual(list(common.KNOWN), ['AABBCCDDEE01', 'AABBCCDDEE02'])
        devices = [{'id': k, 'reachable': True, 'leader': k.endswith('02'),
                    'pair_id': 'test-pair'} for k in common.KNOWN]
        self.assertEqual(common.choose_leader(devices)['id'], 'AABBCCDDEE02')

    def test_preferred_receiver_must_be_selected(self):
        self.config['preferred_receiver'] = 'AABBCCDDEE03'; self.save()
        with self.assertRaises(ValueError):common.configure_devices(self.folder)

    def test_preferred_receiver_can_preserve_verified_entry(self):
        self.config['preferred_receiver'] = 'AABBCCDDEE01'; self.save()
        common.configure_devices(self.folder)
        devices = [{'id': k, 'reachable': True, 'leader': True,
                    'pair_id': 'test-pair'} for k in common.KNOWN]
        self.assertEqual(common.choose_leader(devices)['id'], 'AABBCCDDEE01')

    def test_duplicate_invalid_and_missing_ids_rejected(self):
        for value in ('AA:BB:CC:DD:EE:01', 'not-an-id', ''):
            self.config['devices'][1]['id'] = value; self.save()
            with self.assertRaises(ValueError):common.configure_devices(self.folder)

    def test_unselected_cache_is_not_a_target(self):
        self.save(); common.configure_devices(self.folder)
        common.write_json(self.folder/'devices.json', [
            {'id': 'AABBCCDDEE01'}, {'id': 'AABBCCDDEE99'}])
        self.assertEqual(common.initial_devices(self.folder), [{'id': 'AABBCCDDEE01'}])

    def test_different_stereo_groups_rejected(self):
        with self.assertRaises(RuntimeError):
            common.choose_leader([
                {'id': 'AABBCCDDEE01', 'pair_id': 'one', 'reachable': True},
                {'id': 'AABBCCDDEE02', 'pair_id': 'two', 'reachable': True}])

    def test_discovery_only_probes_explicitly_selected_receivers(self):
        from types import SimpleNamespace
        from pyatv.const import Protocol
        self.save()
        def receiver(identity):
            air = SimpleNamespace(properties={'deviceid': identity, 'tsid': 'pair', 'igl': '1'})
            raop = SimpleNamespace(properties={}, port=7000)
            return SimpleNamespace(address='192.0.2.10', get_service=lambda protocol:
                                   air if protocol == Protocol.AirPlay else raop)
        async def probe(record):return dict(record, reachable=True)
        with patch('pyatv.scan', new=AsyncMock(return_value=[
            receiver('AABBCCDDEE01'), receiver('AABBCCDDEE02'), receiver('AABBCCDDEE99')])), \
             patch.object(common, 'probe', side_effect=probe):
            records = asyncio.run(common.discover(self.folder, force=True))
        self.assertEqual({d['id'] for d in records}, {'AABBCCDDEE01', 'AABBCCDDEE02'})


if __name__ == '__main__':unittest.main()
