import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('baseline',Path(__file__).with_name('build_availability_baseline.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class BaselineTest(unittest.TestCase):
    def test_strict_prior_week_no_current_game_leak(self):
        games=[dict(game_id=f'2026_{w:02}_KC_BUF',away='KC',home='BUF',gameday=f'2026-11-{w:02}',final={'home':10,'away':20})for w in [8,9,10]]
        weeks=[dict(season=2026,week=w,games=[g])for w,g in zip([8,9,10],games)]
        usage=[dict(game_id=g['game_id'],team='KC',season='2026',game_type='REG',pfr_player_id=str(i),player=f'Player {i}',position='DT',offense_pct='0',defense_pct='.02',st_pct='0')for g in games for i in range(40)]
        injury=[dict(team='KC',season='2026',week='10',game_type='REG',full_name='Future Player',gsis_id='x',report_status='Out',position='WR')]
        output=m.build(weeks,injury,usage)['games'][games[-1]['game_id']]['KC']['games']
        self.assertEqual([g['week']for g in output],[8,9]);self.assertTrue(all(g['coverage']for g in output));self.assertTrue(all(not g['injuries']for g in output))
        changed=m.build(weeks,injury,[r for r in usage if r['game_id']==games[-1]['game_id']])['games'][games[-1]['game_id']]['KC']['games']
        self.assertTrue(all(not g['coverage']for g in changed),'missing previous snap rows cannot establish absence')
if __name__=='__main__':unittest.main()
