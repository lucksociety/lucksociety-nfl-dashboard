import importlib.util,json,pathlib,tempfile,unittest,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class ArchiveTests(unittest.TestCase):
    def test_captures_are_market_free(self):
        m=module(ROOT/'scripts/model_learning.py','learning_test')
        rows,_=m.collect_local(ROOT,json.loads((ROOT/'learning/config.json').read_text())['project'])
        for row in rows:
            self.assertEqual(set(row),{'event_id','start','frozen_at','model','probabilities','labels','source','cutoff','key','schema_version','expected_scores'})
            self.assertLess(m.timestamp(row['frozen_at']),m.timestamp(row['start']))

class SeasonTests(unittest.TestCase):
    def test_nfl_year_boundary(self):
        from datetime import datetime
        m=module(ROOT/'model/season.py','nfl_season')
        self.assertEqual(m.current_season(datetime(2027,1,10)),2026)
        self.assertEqual(m.current_season(datetime(2027,8,10)),2026)
        self.assertEqual(m.current_season(datetime(2027,9,10)),2027)
    def test_new_parquet_season_is_discovered(self):
        m=module(ROOT/'model/data.py','nfl_data')
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)
            for name in ('pbp2023.parquet','pbp2027.parquet','pbp2022.parquet','teamgames.parquet'):(p/name).touch()
            self.assertEqual([x.name for x in m.pbp_files(p)],['pbp2023.parquet','pbp2027.parquet'])
