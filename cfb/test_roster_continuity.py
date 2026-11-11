import copy
import datetime as dt
import pytest
from cfb.roster_continuity import check
from cfb.sources import instant

NOW=instant('2026-11-11T20:00Z')

def inputs():
    game={'home':'1','away':'2','season':2027,'conference_game':False}
    history=[{'id':str(i),'home':'1','away':'2','season':2027,'date':f'2026-11-{i:02d}T00:00Z'}for i in [1,3,5]]
    rosters={tid:{'team':{'id':tid},'season':{'year':2027},'timestamp':NOW.isoformat(),'athletes':[
        {'id':str(int(tid)*100+i),'displayName':'Player '+str(i),'position':{'abbreviation':'G'},'status':{'type':'active'}}for i in range(8)]}for tid in ['1','2']}
    def get(url):
        if '/roster'in url:return rosters[url.split('/teams/')[1].split('/')[0]]
        return {'boxscore':{'players':[{'team':{'id':tid},'statistics':[{'labels':['MIN'],'athletes':[
            {'athlete':{'id':str(int(tid)*100+i),'displayName':'Player '+str(i)},'stats':['25'],'starter':i<5}for i in range(8)]}]}for tid in ['1','2']]}}
    return game,history,rosters,get


def test_continuity_is_not_a_claim_of_verified_health():
    game,h,rosters,get=inputs();r=check(game,h,'https://test',get,NOW,True)
    assert r['state']=='roster_checked';assert r['health_confirmed']is False
    assert r['selection_reserve']>.04
    assert all(x['participants_checked']==8 for x in r['evidence'].values())


@pytest.mark.parametrize('problem',['missing','inactive','injury','stale','season','conference','unknown_context'])
def test_changes_stale_data_and_required_reports_do_not_bypass_guards(problem):
    game,h,rosters,get=inputs();r=rosters['1']
    if problem=='missing':r['athletes']=r['athletes'][1:]+[{'id':'9999','displayName':'Replacement','position':{'abbreviation':'G'}}]
    if problem=='inactive':r['athletes'][0]['status']={'type':'inactive'}
    if problem=='injury':r['athletes'][0]['injuries']=[{'status':'Out'}]
    if problem=='stale':r['timestamp']='2020-01-01T00:00Z'
    if problem=='season':r['season']['year']=2026
    if problem=='conference':game['conference_game']=True
    if problem=='unknown_context':game.pop('conference_game')
    with pytest.raises(ValueError):check(game,h,'https://test',get,NOW,True)
